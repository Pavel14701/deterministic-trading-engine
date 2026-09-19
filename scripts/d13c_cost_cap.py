"""D.13c: cost-aware cap and AVSL-off, measured on the WF-B protocol.

D.13b showed the toxic tail (cost_R > 0.15) is pure round-trip cost
drag (ev -0.14R) and AVSL is robustly harmful.  This script measures
both fixes on the real panel (A) and the AVSL-off panel (C), no
rebuild needed:

  grid: variant {A, C} x cost_R cap {none, 0.15, 0.10, 0.075}

The cap filters (candidate, rule) rows whose implied risk_unit is too
small to survive round-trip costs - a live-deployable rule: at signal
time risk_unit is known, so "skip if cost_R > cap" is implementable.

Also reports the D.13 regime-fold breakdown (per-asset means per fold)
and saves runs/d13c_cost_cap.json.
"""

from __future__ import annotations

import json
import sys

from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf import resample_ohlcv  # noqa: E402
from engine.mtf_model import (  # noqa: E402
    bucketed_sharpe,
    build_features,
    candidate_key,
    fit_rule_table,
    per_trade_sharpe,
    trade_curve_stats,
)
from engine.sim import pess, sim  # noqa: E402
from engine.state_machine import run_state_machine  # noqa: E402

TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANT_DIRS = {"A": "A", "C": "C"}
CAPS = (None, 0.15, 0.10, 0.075)
N_FOLDS, FOLD_DAYS, EMBARGO_DAYS = 8, 56, 7
# label-permutation control (D.13e): PERMUTE=0 -> normal run;
# PERMUTE=<seed> -> shuffle r_net before the table fit; test EV must
# collapse to ~0.  Usage: python scripts/d13c_cost_cap.py [PERMUTE]
PERMUTE = int(sys.argv[1]) if len(sys.argv) > 1 else 0
DAY_MS = 86_400_000


def load_asset(d: str, tag: str, cap: float | None):
    """wf_ab-style loader with an extra cost_R <= cap row filter."""
    raw = resample_ohlcv(
        pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet"), "1h"
    )
    o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(raw)
    panel = candidate_key(
        pl.read_parquet(
            REPO / "data" / "ablation" / d / f"{tag.replace('-', '')}_1h.parquet"
        ).filter(
            (pl.col("execution") == "market")
            & (pl.col("target") == 2.0)
            & pl.col("r_net").is_not_nan()
            & (pl.col("exit_idx") >= 0)
            & pl.col("risk_unit").is_not_nan()
        )
    ).with_columns(
        (0.0025 * pl.col("fill_price") / pl.col("risk_unit")).alias("cost_R")
    )
    n0 = panel.height
    if cap is not None:
        panel = panel.filter(pl.col("cost_R") <= cap)
    panel = panel.sort("_cand").with_columns(
        pl.struct(pl.exclude("_cand"))
        .map_elements(pess, return_dtype=pl.Float64)
        .alias("r_pess")
    )
    feats = build_features(panel, ("rule",))
    feats["risk_pct"] = (panel["risk_unit"] / panel["fill_price"]).to_numpy()
    feats["cost_R"] = panel["cost_R"].to_numpy()
    return {"panel": panel, "feats": feats, "n": n, "o": o, "h": h,
            "l": l, "c": c, "rows_raw": n0}


def replay(panel, d, train_mask, permute: int = 0):
    """Rule-table gate + unified sim + state machine (wf_ab port).

    ``train_mask`` MUST be strictly past-only (ts < fold start -
    embargo): fitting the table on ``~is_test`` leaks future folds
    into the gate (D.13e audit finding).

    ``permute`` > 0: seed for permuting ``r_net`` across rows - the
    label-permutation control.  The table then picks rules blind, and
    any residual test EV is structural, not information.
    """
    work = panel
    if permute:
        rng = np.random.default_rng(permute)
        work = work.with_columns(
            pl.Series("r_net", rng.permutation(work["r_net"].to_numpy())))
    table = fit_rule_table(work.filter(train_mask))
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    picks = (panel.sort(["_cand", "s"]).group_by("_cand").last()
             .with_columns(fmt.replace_strict(
                 [f"{r}|{s}" for (r, s) in table],
                 list(table.values()), default="x").alias("tr"))
             .filter(pl.col("rule") == pl.col("tr"))
             .sort("entry_idx").filter(pl.col("is_test")))
    sig = []
    for r in picks.iter_rows(named=True):
        i0 = int(r["entry_idx"]) + 1
        if i0 >= d["n"]:
            continue
        ro, rp, jx = sim(d["o"], d["h"], d["l"], d["c"], i0, r["side"],
                         r["sl_price"], r["tp_price"], 48, r["atr_i"])
        if not np.isfinite(ro):
            continue
        sig.append({"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
                    "side": r["side"], "priority": 0.0, "ts": float(r["ts"]),
                    "r_net": float(rp), "r_opt": float(ro), "exit_idx": jx})
    taken, _ = run_state_machine(sig)
    return (np.array([x["r_net"] for x in taken]),
            np.array([x["ts"] for x in taken]))


def evaluate(d: str, cap: float | None) -> dict:
    """WF-B evaluation of one (variant, cap) cell with fold details."""
    label = f"{d}/cap={cap}"
    print(f"=== evaluating {label} ===", flush=True)
    data = {t: load_asset(d, t, cap) for t in TAGS}

    feats_all, asset_row_all, ys_all, ts_all = [], [], [], []
    for ai, t in enumerate(TAGS):
        f = data[t]["feats"].copy()
        f["asset"] = pd.Categorical([t] * len(f))
        feats_all.append(f)
        asset_row_all.append(np.full(len(f), ai))
        ys_all.append(data[t]["panel"]["r_pess"].to_numpy())
        ts_all.append(data[t]["panel"]["ts"].to_numpy())
    X = pd.concat(feats_all, ignore_index=True)
    for col in X.columns:
        if str(X[col].dtype) == "category":
            X[col] = X[col].cat.codes.astype(np.float32)
        elif X[col].dtype == object:
            X[col] = pd.Categorical(X[col]).codes.astype(np.float32)
    X = np.nan_to_num(X.to_numpy().astype(np.float32),
                      nan=0.0, posinf=0.0, neginf=0.0)
    ASSET_ROW = np.concatenate(asset_row_all)
    Y = np.concatenate(ys_all).astype(np.float32)
    TS = np.concatenate(ts_all)
    row_parts, off = [], 0
    for t in TAGS:
        cands = data[t]["panel"]["_cand"].unique(maintain_order=True).to_list()
        row_parts.append(data[t]["panel"]["_cand"]
                         .replace_strict(cands, list(range(len(cands))))
                         .to_numpy() + off)
        off += len(cands)
    ROW = np.concatenate(row_parts)

    def ranker(tr_ix):
        rel = np.clip(np.round((Y + 2) * 2), 0, 12).astype(int)
        order = np.lexsort((np.arange(len(Y)), ROW))
        inv = np.empty(len(Y), np.int64)
        inv[order] = np.arange(len(Y))
        fs = X[order]
        rows_o = ROW[order]
        in_tr = np.isin(np.arange(len(rows_o)), inv[tr_ix])
        gs, i = [], 0
        while i < len(rows_o):
            j = i
            while j < len(rows_o) and rows_o[j] == rows_o[i]:
                j += 1
            if in_tr[i]:
                gs.append(j - i)
            i = j
        m = lgb.LGBMRanker(objective="lambdarank", n_estimators=300,
                           learning_rate=0.05, num_leaves=15,
                           min_child_samples=30,
                           label_gain=list(range(13)),
                           random_state=7, verbosity=-1)
        m.fit(fs[in_tr], rel[order][in_tr], group=gs, callbacks=[])
        return m.predict(fs)

    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    fl = FOLD_DAYS * DAY_MS
    folds = [(t0 + w * fl, t0 + (w + 1) * fl) for w in
             range(max(0, (t1 - t0) // fl - N_FOLDS + 1),
                   (t1 - t0) // fl + 1)][-N_FOLDS:]

    fold_means, all_r, all_ts, detail = [], [], [], {}
    for fi, (fs_, fe) in enumerate(folds):
        tr = TS < fs_ - EMBARGO_DAYS * DAY_MS
        te = (TS >= fs_) & (TS < fe)
        sc = ranker(np.where(tr)[0])
        per_r, per_ts = {}, {}
        for ai, t in enumerate(TAGS):
            pm = data[t]["panel"].with_columns(
                pl.Series("s", sc[ASSET_ROW == ai]),
                pl.Series("is_test", te[ASSET_ROW == ai]))
            per_r[t], per_ts[t] = replay(pm, data[t],
                                         tr[ASSET_ROW == ai], PERMUTE)
        parts = [x for x in per_r.values() if x.size]
        eb = np.concatenate(parts) if parts else np.array([])
        fold_means.append(float(eb.mean()) if eb.size else float("nan"))
        all_r.append(eb)
        all_ts.append(np.concatenate([per_ts[t] for t in TAGS
                                      if per_r[t].size]))
        detail[fi] = {
            "start": datetime.fromtimestamp(
                fs_ / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "mean": float(eb.mean()) if eb.size else float("nan"),
            "n": int(eb.size),
            **{t: float(per_r[t].mean())
               if per_r[t].size else float("nan") for t in TAGS}}
        print(f"  f{fi} {detail[fi]['start']}: pess={eb.mean():+.3f} "
              f"(n={eb.size})", flush=True)

    pooled = np.concatenate([x for x in all_r if x.size])
    pooled_ts = np.concatenate([x for x in all_ts if x.size])
    order = np.argsort(pooled_ts, kind="stable")
    pooled_chrono = pooled[order]
    stats = trade_curve_stats(pooled_chrono)
    res = {"mean": float(pooled.mean()), "n": int(pooled.size),
           "dd": stats["max_dd_r"],
           "t_stat_naive": stats["t_stat"],
           "sharpe_per_trade": per_trade_sharpe(pooled_chrono),
           "sharpe_ann_bucketed": bucketed_sharpe(pooled_chrono, pooled_ts),
           "folds": fold_means, "fold_detail": detail,
           "rows_raw": sum(data[t]["rows_raw"] for t in TAGS),
           "rows_kept": sum(data[t]["panel"].height for t in TAGS)}
    print(f"  => {label}: pess={res['mean']:+.3f} (n={res['n']}, "
          f"dd={res['dd']:.1f}R, sharpe={res['sharpe_ann_bucketed']:.2f} "
          f"[per-trade {res['sharpe_per_trade']:.2f}], "
          f"rows {res['rows_raw']}->{res['rows_kept']})", flush=True)
    return res


def main() -> None:
    results = {}
    for v, d in VARIANT_DIRS.items():
        for cap in CAPS:
            results[f"{v}|cap={cap}"] = evaluate(d, cap)

    print("\n=== D.13c grid: test pess R (n, dd, panel rows kept) ===",
          flush=True)
    for k, r in results.items():
        print(f"  {k:16s} {r['mean']:+.3f}  (n={r['n']:4d}, "
              f"dd={r['dd']:.1f}R, rows {r['rows_raw']}->{r['rows_kept']})",
              flush=True)
    print("\nfold 2 (regime fold) detail, A|cap=None vs C|cap=0.15:",
          flush=True)
    for k in ("A|cap=None", "C|cap=0.15"):
        d2 = results[k]["fold_detail"][2]
        print(f"  {k}: {d2}", flush=True)

    (REPO / "runs").mkdir(exist_ok=True)
    suffix = f"_perm{PERMUTE}" if PERMUTE else ""
    (REPO / "runs" / f"d13c_cost_cap{suffix}.json").write_text(
        json.dumps(results, indent=1))
    print(f"saved runs/d13c_cost_cap{suffix}.json", flush=True)


if __name__ == "__main__":
    main()
