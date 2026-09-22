"""WF-B walk-forward protocol as a library (ranker family).

Owns the pieces that used to be copy-pasted across ``wf_ab``,
``ablation``, ``cost_cap`` and ``ranker_only``:

- protocol-panel loading: reference-config row filter (execution /
  target / finite ``r_net``/``exit_idx``/``risk_unit``), candidate
  keys, the round-trip cost as ``cost_R``, optional cost cap and
  the pessimistic-R label;
- the fold calendar: ``N_FOLDS`` x ``FOLD_DAYS``-day windows aligned
  to the panel range, with an ``EMBARGO_DAYS`` past-only train mask;
- the lambdarank ranker (past-only groups, fixed hyper-parameters,
  seed 7) and the multi-asset feature-matrix assembly;
- the gated replay: top-``s`` row per candidate, optional rule-table
  gate, unified sim, position state machine.

Scripts keep only the experiment grid and reporting.  All functions
here are deterministic; re-running a script that uses them must
reproduce its saved JSON bit-for-bit (that property is the
regression test for refactors).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl

from engine.ensemble.combine import EnsembleConfig, EnsembleRanker
from engine.features.mtf import resample_ohlcv
from engine.metrics.trade import DAY_MS
from engine.model.ranker import (
    REFERENCE_EXECUTION,
    REFERENCE_TARGET,
    build_features,
    candidate_key,
)
from engine.sim.engine import pess, sim
from engine.sim.state_machine import run_state_machine


REPO = Path(__file__).resolve().parent.parent.parent

N_FOLDS = 8
FOLD_DAYS = 56
EMBARGO_DAYS = 7
#: hold window (bars) handed to :func:`engine.sim.engine.sim`
SIM_HOLD = 48
#: round-trip cost in price fraction -> cost_R = rate * fill / risk_unit
COST_R_RATE = 0.0025

#: LightGBM feed encodings.  Binning is encoding-sensitive (dtype and
#: NaN handling change the trees - two of 24 wf_ab rankers flipped
#: when retrained on the other family's encoding), so each experiment
#: family pins ONE encoding by reference, never inline literals.
#: Zeroed encoding (current default): float32, NaN/inf zeroed.
ENCODING_ZEROED: dict[str, Any] = {
    "fill_nonfinite": True, "x_dtype": np.float32}
#: Native encoding: float64, NaN kept natively (what a pandas
#: DataFrame feed produced historically).
ENCODING_NATIVE: dict[str, Any] = {
    "fill_nonfinite": False, "x_dtype": np.float64}


def load_asset_bars(tag: str, repo: Path = REPO) -> dict[str, Any]:
    """1h OHLCV arrays for one asset (resampled from 1m raw)."""
    raw = resample_ohlcv(
        pl.read_parquet(repo / f"data/okx/raw_{tag}_1m.parquet"), "1h"
    )
    o, h, lo, c = (
        raw[k].to_numpy() for k in ("open", "high", "low", "close")
    )
    return {"n": len(raw), "o": o, "h": h, "l": lo, "c": c}


def _read_protocol_panel(
    variant_dir: str,
    tag: str,
    repo: Path,
) -> pl.DataFrame:
    """Reference-config rows + ``cost_R`` (no cap, no label yet).

    Reference-config rows only (``execution == market``, ``target ==
    2.0``, finite ``r_net``/``exit_idx``/``risk_unit``); adds
    ``cost_R`` and the pessimistic label ``r_pess``.  ``cost_cap``
    drops rows whose round-trip cost exceeds the cap (deployable at
    signal time: ``risk_unit`` is known then).

    """
    base = (
        repo / "data" / "mtf_dataset"
        if variant_dir == ""
        else repo / "data" / "ablation" / variant_dir
    )
    panel = candidate_key(
        pl.read_parquet(base / f"{tag.replace('-', '')}_1h.parquet").filter(
            (pl.col("execution") == REFERENCE_EXECUTION)
            & (pl.col("target") == REFERENCE_TARGET)
            & pl.col("r_net").is_not_nan()
            & (pl.col("exit_idx") >= 0)
            & pl.col("risk_unit").is_not_nan()
        )
    ).with_columns(
        (COST_R_RATE * pl.col("fill_price") / pl.col("risk_unit"))
        .alias("cost_R")
    )
    return panel


def load_panel(
    variant_dir: str,
    tag: str,
    cost_cap: float | None = None,
    repo: Path = REPO,
) -> pl.DataFrame:
    """Protocol panel for one (variant, asset), sorted by ``_cand``.

    Adds ``cost_R``/``r_pess``; ``cost_cap`` drops rows whose
    round-trip cost exceeds the cap.  ``variant_dir`` is relative to
    ``data/ablation`` (incl. placebo-suffixed dirs); pass ``""`` for
    the main ``data/mtf_dataset`` panel (flat-panel layout).
    """
    panel = _read_protocol_panel(variant_dir, tag, repo)
    if cost_cap is not None:
        panel = panel.filter(pl.col("cost_R") <= cost_cap)
    return panel.sort("_cand").with_columns(
        pl.struct(pl.exclude("_cand"))
        .map_elements(pess, return_dtype=pl.Float64)
        .alias("r_pess")
    )


def load_asset(
    variant_dir: str,
    tag: str,
    cost_cap: float | None = None,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Everything one (variant, asset) needs in the WF loop.

    Returns ``panel`` (with ``cost_R``/``r_pess``), ``feats`` (the
    LightGBM frame + ``risk_pct``/``cost_R``), the 1h bars and
    ``rows_raw`` (panel height before the cap filter, for drag stats).
    """
    d = load_asset_bars(tag, repo)
    rows_raw = _read_protocol_panel(variant_dir, tag, repo).height
    panel = load_panel(variant_dir, tag, cost_cap, repo)
    feats = build_features(panel, ("rule",))
    feats["risk_pct"] = (panel["risk_unit"] / panel["fill_price"]).to_numpy()
    feats["cost_R"] = panel["cost_R"].to_numpy()
    return {"panel": panel, "feats": feats, "rows_raw": rows_raw, **d}


def wf_folds(
    t0: int,
    t1: int,
    n_folds: int = N_FOLDS,
    fold_days: int = FOLD_DAYS,
) -> list[tuple[int, int]]:
    """Last ``n_folds`` contiguous ``fold_days`` windows over [t0, t1].

    Returns ``(fold_start_ms, fold_end_ms)`` pairs, chronological.
    """
    fl = fold_days * DAY_MS
    return [
        (t0 + w * fl, t0 + (w + 1) * fl)
        for w in range(
            max(0, (t1 - t0) // fl - n_folds + 1), (t1 - t0) // fl + 1
        )
    ][-n_folds:]


def fold_masks(
    ts: np.ndarray,
    fold_start: int,
    fold_end: int,
    embargo_days: int = EMBARGO_DAYS,
) -> tuple[np.ndarray, np.ndarray]:
    """Past-only train mask and test mask for one fold.

    Train = strictly before ``fold_start - embargo`` (the embargo gap
    keeps same-regime neighbours out of the train fit).  Test = the
    fold window itself.  Passing anything wider than this mask into a
    fitter leaks future folds (pinned by a past audit).
    """
    train = ts < fold_start - embargo_days * DAY_MS
    test = (ts >= fold_start) & (ts < fold_end)
    return train, test


@dataclass
class RankerData:
    """Multi-asset flat matrix for :func:`train_ranker`.

    ``row`` is the LightGBM group id (one per candidate, offset across
    assets); ``asset_row`` maps each row back to its asset index.
    """

    x: np.ndarray
    y: np.ndarray
    ts: np.ndarray
    asset_row: np.ndarray
    row: np.ndarray


def assemble_ranker_data(
    data: dict[str, dict[str, Any]],
    tags: list[str],
    encoding: dict[str, Any] = ENCODING_ZEROED,
) -> RankerData:
    """Concatenate per-asset feats/labels into the flat ranker matrix.

    ``data`` maps tag -> the dict from :func:`load_asset`.  Category
    columns become ordinal codes.  Encodings differ per experiment
    family and change LightGBM's binning, so pass one of the module
    presets: ``ENCODING_ZEROED`` (default; float32, NaN/inf zeroed) or
    ``ENCODING_NATIVE`` (float64, NaN kept natively - the pandas
    DataFrame feed wf_ab was fitted with).  Never inline literals.
    """
    feats_all, asset_row_all, ys_all, ts_all = [], [], [], []
    for ai, t in enumerate(tags):
        f = data[t]["feats"].copy()
        f["asset"] = pd.Categorical([t] * len(f))
        feats_all.append(f)
        asset_row_all.append(np.full(len(f), ai))
        ys_all.append(data[t]["panel"]["r_pess"].to_numpy())
        ts_all.append(data[t]["panel"]["ts"].to_numpy())
    x = pd.concat(feats_all, ignore_index=True)
    for col in x.columns:
        if str(x[col].dtype) == "category":
            x[col] = x[col].cat.codes.astype(np.float32)
        elif x[col].dtype == object:
            x[col] = pd.Categorical(x[col]).codes.astype(np.float32)
    x = x.to_numpy().astype(encoding["x_dtype"])
    if encoding["fill_nonfinite"]:
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    row_parts, off = [], 0
    for t in tags:
        cands = data[t]["panel"]["_cand"].unique(maintain_order=True).to_list()
        row_parts.append(
            data[t]["panel"]["_cand"]
            .replace_strict(cands, list(range(len(cands))))
            .to_numpy()
            + off
        )
        off += len(cands)
    return RankerData(
        x=x,
        y=np.concatenate(ys_all).astype(np.float32),
        ts=np.concatenate(ts_all),
        asset_row=np.concatenate(asset_row_all),
        row=np.concatenate(row_parts),
    )


def train_ranker(
    x: np.ndarray, y: np.ndarray, row: np.ndarray, train_ix: np.ndarray
) -> np.ndarray:
    """Fit lambdarank on past-only rows, score every row.

    Relevance = ``clip(round((y + 2) * 2), 0, 12)``; rows are sorted
    into contiguous candidate groups for LightGBM's group API; only
    groups with at least one train row contribute.  Fixed hyper-
    parameters + ``random_state=7``: deterministic across runs.
    """
    rel = np.clip(np.round((y + 2) * 2), 0, 12).astype(int)
    order = np.lexsort((np.arange(len(y)), row))
    inv = np.empty(len(y), np.int64)
    inv[order] = np.arange(len(y))
    fs = x[order]
    rows_o = row[order]
    in_tr = np.isin(np.arange(len(rows_o)), inv[train_ix])
    groups, i = [], 0
    while i < len(rows_o):
        j = i
        while j < len(rows_o) and rows_o[j] == rows_o[i]:
            j += 1
        if in_tr[i]:
            groups.append(j - i)
        i = j
    model = lgb.LGBMRanker(
        objective="lambdarank",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=30,
        label_gain=list(range(13)),
        random_state=7,
        verbosity=-1,
    )
    model.fit(fs[in_tr], rel[order][in_tr], group=groups, callbacks=[])
    return np.asarray(model.predict(fs))


def train_ensemble_ranker(
    x: np.ndarray,
    y: np.ndarray,
    row: np.ndarray,
    ts: np.ndarray,
    train_ix: np.ndarray,
    config: "EnsembleConfig",
) -> np.ndarray:
    """Fit the ensemble on past-only rows, score every row.

    Ensemble twin of :func:`train_ranker`: same contract (past-only
    ``train_ix``, scores for ALL rows in input order), so the replay
    and every experiment grid switch between the two by config alone.
    """
    ens = EnsembleRanker(config)
    ens.fit(x[train_ix], y[train_ix], row[train_ix], ts=ts[train_ix])
    return ens.predict(x)


def replay(
    panel: pl.DataFrame,
    bars: dict[str, Any],
    table: dict[tuple[str, str], str] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Gate one asset-fold panel and simulate the taken trades.

    ``panel`` needs ``s`` (ranker score) and ``is_test`` columns on
    top of the protocol schema.  The top-``s`` row per candidate is
    picked; with ``table`` (``fit_rule_table`` shape: mapping
    ``(regime_dir, side)`` -> rule)
    the pick is kept iff its rule matches the table rule - ``None``
    trades every candidate's top pick (ranker-only gate).  Returns
    ``(pess_r, ts, meta)`` over taken trades only (state machine,
    cooldown 0).
    """
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    top = panel.sort(["_cand", "s"]).group_by("_cand").last()
    if table is not None:
        top = top.with_columns(
            fmt.replace_strict(
                [f"{r}|{s}" for (r, s) in table],
                list(table.values()),
                default="x",
            ).alias("tr")
        ).filter(pl.col("rule") == pl.col("tr"))
    picks = top.sort("entry_idx").filter(pl.col("is_test"))
    sig, meta = [], []
    for r in picks.iter_rows(named=True):
        i0 = int(r["entry_idx"]) + 1
        if i0 >= bars["n"]:
            continue
        ro, rp, jx = sim(
            bars["o"], bars["h"], bars["l"], bars["c"], i0, r["side"],
            r["sl_price"], r["tp_price"], SIM_HOLD, r["atr_i"],
            r["risk_unit"],
        )
        if not np.isfinite(ro):
            continue
        sig.append({
            "cand": r["_cand"],
            "decision_idx": int(r["entry_idx"]),
            "side": r["side"],
            "priority": 0.0,
            "ts": float(r["ts"]),
            "r_net": float(rp),
            "r_opt": float(ro),
            "exit_idx": jx,
        })
        meta.append({
            "reason": r["exit_reason"], "hold": jx - i0,
            "r": float(rp), "rule": r["rule"],
        })
    taken, _ = run_state_machine(sig)
    keep = {x["cand"] for x in taken}
    meta = [
        m for m, s_ in zip(meta, sig, strict=True) if s_["cand"] in keep
    ]
    return (
        np.array([x["r_net"] for x in taken]),
        np.array([x["ts"] for x in taken]),
        meta,
    )

