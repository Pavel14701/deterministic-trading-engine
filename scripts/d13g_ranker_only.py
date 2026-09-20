"""D.13g: ranker-only ablation - drop the rule-table filter.

D.13f showed the informed table is WORSE than a noise table
(honest +0.118R vs table-permuted +0.242R): the train-fitted table
picks zone rules while the ranker's strong picks are st/atr-flavored,
so ``rule == table-rule`` throws away the ranker's best candidates.

This script measures both gates on the same walk-forward ranker per
fold (same WF-B protocol as d13c, past-only train mask):

  gate=table : d13c behavior (top-s row kept iff rule == table rule)
  gate=free  : top-s row per candidate, no table filter

Grid: variant {A, C} x cost_R cap {None, 0.15, 0.10, 0.075}.
Saves runs/d13g_ranker_only.json.
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
DAY_MS = 86_400_000


def load_asset(d: str, tag: str, cap: float | None):
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
            "l": l, "c": c}


def replay(panel, d, table, use_table: bool):
    """Gate + unified sim + state machine for one asset-fold.

    ``use_table=True``: d13c gate - the candidate's top-``s`` row is
    kept iff its rule equals the table rule for its (regime_dir, side).
    ``use_table=False``: ranker-only - the top-``s`` row of every
    candidate is traded (no table filter).
    """
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    top = panel.sort(["_cand", "s"]).group_by("_cand").last()
    if use_table:
        top = top.with_columns(fmt.replace_strict(
            [f"{r}|{s}" for (r, s) in table],
            list(table.values()), default="x").alias("tr")
        ).filter(pl.col("rule") == pl.col("tr"))
    picks = top.sort("entry_idx").filter(pl.col("is_test"))
    sig, meta = [], []
    for r in picks.iter_rows(named=True):
        i0 = int(r["entry_idx"]) + 1
        if i0 >= d["n"]:
            continue
        ro, rp, jx = sim(d["o"], d["h"], d["l"], d["c"], i0, r["side"],
                         r["sl_price"], r["tp_price"], 48, r["atr_i"], r["risk_unit"])
        if not np.isfinite(ro):
            continue
        sig.append({"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
                    "side": r["side"], "priority": 0.0, "ts": float(r["ts"]),
                    "r_net": float(rp), "r_opt": float(ro), "exit_idx": jx})
        meta.append({"reason": r["exit_reason"], "hold": jx - i0,
                     "r": float(rp), "rule": r["rule"]})
    taken, _ = run_state_machine(sig)
    keep = {x["cand"] for x in taken}
    meta = [m for m, s_ in zip(meta, sig) if s_["cand"] in keep]
    return (np.array([x["r_net"] for x in taken]),
            np.array([x["ts"] for x in taken]), meta)


def evaluate(d: str, cap: float | None) -> dict:
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

    acc = {"table": {"r": [], "ts": []}, "free": {"r": [], "ts": []}}
    for fi, (fs_, fe) in enumerate(folds):
        tr = TS < fs_ - EMBARGO_DAYS * DAY_MS
        te = (TS >= fs_) & (TS < fe)
        sc = ranker(np.where(tr)[0])
        per = {"table": {}, "free": {}}
        meta_all = {"table": [], "free": []}
        for ai, t in enumerate(TAGS):
            pm = data[t]["panel"].with_columns(
                pl.Series("s", sc[ASSET_ROW == ai]),
                pl.Series("is_test", te[ASSET_ROW == ai]))
            table = fit_rule_table(pm.filter(tr[ASSET_ROW == ai]))
            for gate, ut in (("table", True), ("free", False)):
                r, ts_, meta = replay(pm, data[t], table, ut)
                per[gate][t] = r
                acc[gate]["r"].append(r)
                acc[gate]["ts"].append(ts_)
                meta_all[gate].extend(meta)
        line = f"  f{fi}: "
        for gate in ("table", "free"):
            eb = np.concatenate([x for x in per[gate].values() if x.size])
            line += (f"{gate}={eb.mean():+.3f}(n={eb.size}) " if eb.size
                     else f"{gate}=n/a ")
        print(line, flush=True)

    for gate in ("table", "free"):
        m = pl.DataFrame(meta_all[gate])
        if not m.height:
            continue
        win = m.filter(pl.col("r") > 0).height
        mix = (m.group_by("reason").agg(pl.len().alias("n"))
               .sort("n", descending=True))
        mixs = ", ".join(f"{x['reason']}={x['n'] / m.height:.2f}"
                         for x in mix.iter_rows(named=True))
        h01 = m.filter(pl.col("hold") <= 1)
        tot = m["r"].sum()
        r01 = (h01["r"].sum() / tot) if tot else 0.0
        m01 = h01["r"].mean() if h01.height else float("nan")
        print(f"  [{gate}] trades n={m.height} win={win / m.height:.2f} "
              f"hold med={m['hold'].median():.0f}  mix: {mixs}")
        print(f"        hold<=1: n={h01.height} ({h01.height / m.height:.2f})"
              f"  mean r={m01:+.3f}"
              f"  EV share={r01:+.2f}", flush=True)

    res = {}
    for gate in ("table", "free"):
        pooled = np.concatenate([x for x in acc[gate]["r"] if x.size])
        pooled_ts = np.concatenate([x for x in acc[gate]["ts"] if x.size])
        order = np.argsort(pooled_ts, kind="stable")
        chrono = pooled[order]
        stats = trade_curve_stats(chrono)
        res[gate] = {"mean": float(pooled.mean()), "n": int(pooled.size),
                     "dd": stats["max_dd_r"],
                     "t_stat_naive": stats["t_stat"],
                     "sharpe_per_trade": per_trade_sharpe(chrono),
                     "sharpe_ann_bucketed": bucketed_sharpe(chrono, pooled_ts)}
        g = res[gate]
        print(f"  => {label} [{gate:5s}]: pess={g['mean']:+.3f} "
              f"(n={g['n']}, dd={g['dd']:.1f}R, "
              f"sharpe={g['sharpe_ann_bucketed']:.2f})", flush=True)
    res["rows_kept"] = sum(data[t]["panel"].height for t in TAGS)
    return res


def main() -> None:
    results = {}
    for v, d in VARIANT_DIRS.items():
        for cap in CAPS:
            results[f"{v}|cap={cap}"] = evaluate(d, cap)

    print("\n=== D.13g ranker-only ablation: test pess R ===", flush=True)
    print(f"  {'cell':16s} {'table':>8s} {'free':>8s}  n_free", flush=True)
    for k, r in results.items():
        print(f"  {k:16s} {r['table']['mean']:+8.3f} "
              f"{r['free']['mean']:+8.3f}  {r['free']['n']}", flush=True)

    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "d13g_ranker_only.json").write_text(
        json.dumps(results, indent=1))
    print("saved runs/d13g_ranker_only.json", flush=True)


if __name__ == "__main__":
    main()

