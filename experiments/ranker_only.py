"""Ranker-only ablation: drop the rule-table filter.

Earlier ablation showed the informed table is WORSE than a noise table
(honest +0.118R vs table-permuted +0.242R): the train-fitted table
picks zone rules while the ranker's strong picks are st/atr-flavored,
so ``rule == table-rule`` throws away the ranker's best candidates.

This script measures both gates on the same walk-forward ranker per
fold (same WF-B protocol as the cost-cap experiment, past-only train
mask):

  gate=table : rule-table-gated (top-s row kept iff rule == table rule)
  gate=free  : top-s row per candidate, no table filter

Grid: variant {A, C} x cost_R cap {None, 0.15, 0.10, 0.075}.
Saves runs/ranker_only.json.

All protocol mechanics (panel loading, fold calendar, ranker,
replay, pooled stats) live in engine.backtest.protocol - this file is only
the experiment grid and reporting.
"""
from __future__ import annotations

import json
import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    assemble_ranker_data,
    fold_masks,
    load_asset,
    replay,
    train_ranker,
    wf_folds,
)
from engine.metrics.trade import pooled_stats
from engine.model.ranker import fit_rule_table


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANT_DIRS = {"A": "A", "C": "C"}
CAPS = (None, 0.15, 0.10, 0.075)


def evaluate(d: str, cap: float | None) -> dict:
    label = f"{d}/cap={cap}"
    print(f"=== evaluating {label} ===", flush=True)
    data = {t: load_asset(d, t, cap) for t in TAGS}
    rd = assemble_ranker_data(data, TAGS)
    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    folds = wf_folds(t0, t1)

    acc = {"table": {"r": [], "ts": []}, "free": {"r": [], "ts": []}}
    for fi, (fs_, fe) in enumerate(folds):
        tr, te = fold_masks(rd.ts, fs_, fe)
        sc = train_ranker(rd.x, rd.y, rd.row, np.where(tr)[0])
        per = {"table": {}, "free": {}}
        meta_all = {"table": [], "free": []}
        for ai, t in enumerate(TAGS):
            pm = data[t]["panel"].with_columns(
                pl.Series("s", sc[rd.asset_row == ai]),
                pl.Series("is_test", te[rd.asset_row == ai]))
            table = fit_rule_table(pm.filter(tr[rd.asset_row == ai]))
            for gate, tbl in (("table", table), ("free", None)):
                r, ts_, meta = replay(pm, data[t], tbl)
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
        res[gate] = pooled_stats(pooled, pooled_ts)
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

    print("\n=== ranker-only ablation: test pess R ===", flush=True)
    print(f"  {'cell':16s} {'table':>8s} {'free':>8s}  n_free", flush=True)
    for k, r in results.items():
        print(f"  {k:16s} {r['table']['mean']:+8.3f} "
              f"{r['free']['mean']:+8.3f}  {r['free']['n']}", flush=True)

    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "ranker_only.json").write_text(
        json.dumps(results, indent=1))
    print("saved runs/ranker_only.json", flush=True)


if __name__ == "__main__":
    main()
