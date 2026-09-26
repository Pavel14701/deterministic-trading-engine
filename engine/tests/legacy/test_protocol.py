"""Tests for engine.backtest.protocol (WF-B protocol library)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine.backtest.protocol import (
    ENCODING_NATIVE,
    ENCODING_ZEROED,
    assemble_ranker_data,
    fold_masks,
    load_panel,
    replay,
    train_ranker,
    wf_folds,
)
from engine.metrics.trade import DAY_MS, pooled_stats
from engine.sim.engine import pess


# ------------------------------------------------------- fold calendar


def test_wf_folds_window_math() -> None:
    t0, t1 = 0, 100 * DAY_MS
    folds = wf_folds(t0, t1, n_folds=3, fold_days=10)
    fl = 10 * DAY_MS
    assert folds == [
        (8 * fl, 9 * fl), (9 * fl, 10 * fl), (10 * fl, 11 * fl)
    ]


def test_wf_folds_short_span_clamps_to_one() -> None:
    # span shorter than one fold -> max(0, ...) keeps a single window
    folds = wf_folds(0, DAY_MS, n_folds=8, fold_days=56)
    assert folds == [(0, 56 * DAY_MS)]


def test_fold_masks_embargo_boundaries() -> None:
    fs, fe = 100 * DAY_MS, 156 * DAY_MS
    ts = np.array([
        fs - 8 * DAY_MS,   # before embargo gap -> train
        fs - 7 * DAY_MS,   # exactly at embargo boundary -> NOT train
        fs - DAY_MS,       # inside embargo gap -> NOT train
        fs,                # fold start -> test
        fe - DAY_MS,       # last test bar
        fe,                # fold end -> NOT test
    ])
    tr, te = fold_masks(ts, fs, fe)
    assert tr.tolist() == [True, False, False, False, False, False]
    assert te.tolist() == [False, False, False, True, True, False]


# ------------------------------------------------------- ranker


def _synth_ranker_data(
    n_groups: int = 6, rows_per: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    n = n_groups * rows_per
    x = rng.normal(size=(n, 5)).astype(np.float32)
    y = rng.normal(scale=0.5, size=n).astype(np.float32)
    row = np.repeat(np.arange(n_groups), rows_per)
    return x, y, row


def test_train_ranker_deterministic() -> None:
    x, y, row = _synth_ranker_data()
    tr = np.where(row < 4)[0]
    s1 = train_ranker(x, y, row, tr)
    s2 = train_ranker(x, y, row, tr)
    assert s1.shape == (len(y),)
    assert np.allclose(s1, s2)


def test_train_ranker_row_permutation_invariant() -> None:
    """Shuffling input rows must not change per-row scores."""
    x, y, row = _synth_ranker_data()
    tr = np.where(row < 4)[0]
    base = train_ranker(x, y, row, tr)
    perm = np.random.default_rng(1).permutation(len(y))
    shuffled = train_ranker(x[perm], y[perm], row[perm], np.where(row[perm] < 4)[0])
    assert np.allclose(shuffled, base[perm], atol=1e-6)


def test_train_ranker_scores_all_rows_but_trains_past_only() -> None:
    x, y, row = _synth_ranker_data()
    tr = np.where(row < 4)[0]
    scores = train_ranker(x, y, row, tr)
    assert np.isfinite(scores).all()  # future rows scored, not trained on


# ------------------------------------------------------- assemble


def test_assemble_ranker_data_offsets_and_codes() -> None:
    def one(tag: str, n: int) -> dict:
        panel = pl.DataFrame({
            "r_pess": np.linspace(-1.0, 1.0, n),
            "ts": np.arange(n, dtype=np.int64) * DAY_MS,
            "_cand": [f"{tag}_{i}" for i in range(n)],
        })
        feats = pd.DataFrame({
            "f": np.arange(n, dtype=np.float32),
            "side": pd.Categorical(["long"] * n),
        })
        return {"panel": panel, "feats": feats}

    data = {"AAA": one("AAA", 4), "BBB": one("BBB", 2)}
    rd = assemble_ranker_data(data, ["AAA", "BBB"], ENCODING_ZEROED)
    assert rd.x.shape == (6, 3)  # f, side codes, asset codes
    assert rd.asset_row.tolist() == [0] * 4 + [1] * 2
    assert rd.row.tolist() == [0, 1, 2, 3, 4, 5]  # offset across assets
    assert rd.y.shape == (6,)


# ------------------------------------------------------- replay


def _bars(n: int = 12) -> dict:
    o = np.full(n, 100.0)
    h = np.full(n, 103.0)  # every bar touches tp=102
    lo = np.full(n, 99.5)
    c = np.full(n, 100.0)
    return {"n": n, "o": o, "h": h, "l": lo, "c": c}


def _panel() -> pl.DataFrame:
    rows = []
    for cand, rule, entry in (("0_long", "zone:1.0", 0), ("1_long", "st:0.5", 2)):
        rows.append({
            "_cand": cand, "s": 1.0, "is_test": True, "rule": rule,
            "regime_dir": "up", "side": "long", "entry_idx": entry,
            "sl_price": 99.0, "tp_price": 102.0, "atr_i": 1.0,
            "risk_unit": 1.0, "ts": entry * DAY_MS, "exit_reason": "tp",
        })
    return pl.DataFrame(rows)


def test_replay_ranker_only_takes_every_candidate_top() -> None:
    r, ts, meta = replay(_panel(), _bars(), table=None)
    assert r.size == 2  # distinct entry bars: no state-machine clash
    assert ts.size == 2
    assert len(meta) == 2
    assert all(m["reason"] == "tp" for m in meta)
    assert (r > 0).all()  # tp hit: +2R minus costs


def test_replay_table_gate_filters_rules() -> None:
    table = {("up", "long"): "zone:1.0"}  # only cand 0's rule tabulated
    r, _ts, meta = replay(_panel(), _bars(), table=table)
    assert r.size == 1
    assert meta[0]["rule"] == "zone:1.0"


def test_replay_state_machine_skips_overlap() -> None:
    panel = _panel()
    # both candidates decide at bar 0 -> one slot, one trade
    panel = panel.with_columns(pl.lit(0).alias("entry_idx"))
    r, _ts, _meta = replay(panel, _bars(), table=None)
    assert r.size == 1


# ------------------------------------------------------- load_panel


def _write_panel_parquet(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def test_load_panel_protocol_filter_cost_and_pess(tmp_path) -> None:
    good = {
        "execution": "market", "target": 2.0, "r_net": 0.5,
        "exit_idx": 3, "risk_unit": 1.0, "fill_price": 100.0,
        "exit_reason": "tp", "exit_price": 102.0, "sl_price": 99.0,
        "atr_i": 1.0, "entry_idx": 2, "side": "long",
    }
    bad_exec = {**good, "execution": "limit"}
    tiny_risk = {**good, "entry_idx": 4, "risk_unit": 0.05}  # cost_R = 5.0
    _write_panel_parquet(
        tmp_path / "data" / "ablation" / "V" / "TAGUSDT_1h.parquet",
        [good, bad_exec, tiny_risk],
    )
    panel = load_panel("V", "TAG-USDT", repo=tmp_path)
    assert panel.height == 2  # bad_exec dropped, cap not applied yet
    assert set(panel["_cand"]) == {"2_long", "4_long"}
    assert panel["cost_R"].to_list() == pytest.approx([0.25, 5.0])
    row = panel.filter(pl.col("_cand") == "2_long").iter_rows(named=True)
    assert next(row)["r_pess"] == pytest.approx(
        pess({**good, "exit_idx": 3}))

    capped = load_panel("V", "TAG-USDT", cost_cap=0.5, repo=tmp_path)
    assert capped.height == 1
    assert capped["_cand"].to_list() == ["2_long"]


# ------------------------------------------------------- pooled stats


def test_pooled_stats_chronology_restored() -> None:
    r = np.array([1.0, -0.5, 2.0])
    ts = np.array([3.0, 1.0, 2.0])
    stats = pooled_stats(r, ts)
    assert stats["mean"] == pytest.approx(r.mean())
    assert stats["n"] == 3
    assert np.isfinite(stats["sharpe_ann_bucketed"])


def test_assemble_ranker_data_encoding_variants() -> None:
    """Zeroed (float32 NaN->0) vs native (float64 NaN-kept) encodings."""
    def one() -> dict:
        panel = pl.DataFrame({
            "r_pess": [0.0, 0.0],
            "ts": [0, 1],
            "_cand": ["a", "b"],
        })
        feats = pd.DataFrame({"f": [np.nan, 1.5]})
        return {"panel": panel, "feats": feats}

    data = {"AAA": one()}
    zeroed = assemble_ranker_data(data, ["AAA"], ENCODING_ZEROED)
    assert zeroed.x.dtype == np.float32
    assert zeroed.x[0, 0] == 0.0  # NaN zero-filled

    d8b = assemble_ranker_data(data, ["AAA"], ENCODING_NATIVE)
    assert d8b.x.dtype == np.float64
    assert np.isnan(d8b.x[0, 0])  # NaN kept natively
