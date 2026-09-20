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

All protocol mechanics (panel loading, fold calendar, ranker, replay,
pooled stats) live in engine.protocol - this file is only the
experiment grid, the label-permutation control and reporting.
"""

from __future__ import annotations

import json
import sys

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf_model import fit_rule_table  # noqa: E402
from engine.protocol import (  # noqa: E402
    assemble_ranker_data,
    fold_masks,
    load_asset,
    pooled_stats,
    replay,
    train_ranker,
    wf_folds,
)

TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANT_DIRS = {"A": "A", "C": "C"}
CAPS = (None, 0.15, 0.10, 0.075)
# label-permutation control (D.13e): PERMUTE=0 -> normal run;
# PERMUTE=<seed> -> shuffle r_net before the table fit; test EV must
# collapse to ~0.  Usage: python scripts/d13c_cost_cap.py [PERMUTE]
PERMUTE = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def replay_table(panel, bars, train_mask, permute: int = 0):
    """Rule-table gate + replay (wf_ab port).

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
    r, ts, _ = replay(panel, bars, table)
    return r, ts


def evaluate(d: str, cap: float | None) -> dict:
    """WF-B evaluation of one (variant, cap) cell with fold details."""
    label = f"{d}/cap={cap}"
    print(f"=== evaluating {label} ===", flush=True)
    data = {t: load_asset(d, t, cap) for t in TAGS}
    rd = assemble_ranker_data(data, TAGS)
    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    folds = wf_folds(t0, t1)

    fold_means, all_r, all_ts, detail = [], [], [], {}
    for fi, (fs_, fe) in enumerate(folds):
        tr, te = fold_masks(rd.ts, fs_, fe)
        sc = train_ranker(rd.x, rd.y, rd.row, np.where(tr)[0])
        per_r, per_ts = {}, {}
        for ai, t in enumerate(TAGS):
            pm = data[t]["panel"].with_columns(
                pl.Series("s", sc[rd.asset_row == ai]),
                pl.Series("is_test", te[rd.asset_row == ai]))
            per_r[t], per_ts[t] = replay_table(
                pm, data[t], tr[rd.asset_row == ai], PERMUTE)
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
    res = pooled_stats(pooled, pooled_ts)
    res["folds"] = fold_means
    res["fold_detail"] = detail
    res["rows_raw"] = sum(data[t]["rows_raw"] for t in TAGS)
    res["rows_kept"] = sum(data[t]["panel"].height for t in TAGS)
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
