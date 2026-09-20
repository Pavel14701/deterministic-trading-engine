"""Ablation diagnostics - decompose the D>A effect.

Question: is the placebo/outward-shift improvement cost geometry
(wider stop -> lower cost_R -> higher net EV, the cost mechanism) or
something else (entry timing, selection)?

Panels already carry everything needed: market/2R rows with r_net,
risk_unit, atr_i, mfe/mae_r, rule, family, split.  This script
compares A/B/C/D on that raw material (no gate), then buckets EV by
risk_unit_atr quintile to expose the cost monotonicity, and finally
prints the per-fold D-A deltas from the saved runs jsons.
"""

from __future__ import annotations

import json
import sys

from pathlib import Path

import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

VARIANTS = {"A": "A", "B": "B", "C": "C", "D": "D"}
TAGS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def load_variantpanel(d: str) -> pl.DataFrame:
    dfs = [
        pl.read_parquet(REPO / "data" / "ablation" / d / f"{t}_1h.parquet")
        for t in TAGS
    ]
    df = pl.concat(dfs)
    return df.filter(
        (pl.col("execution") == "market")
        & (pl.col("target") == 2.0)
        & pl.col("r_net").is_not_nan()
        & pl.col("risk_unit").is_not_nan()
    ).with_columns(
        (pl.col("risk_unit") / pl.col("atr_i")).alias("ru_atr"),
        (0.0025 * pl.col("fill_price") / pl.col("risk_unit")).alias("cost_R"),
    )


def main() -> None:
    frames = {}
    print("=== panel level (market, 2R, valid rows, all splits) ===",
          flush=True)
    for v, d in VARIANTS.items():
        m = load_variantpanel(d)
        frames[v] = m
        win = 100.0 * (m["r_net"] > 0).mean()
        print(f"{v}: rows={m.height:6d}  r_net={m['r_net'].mean():+.4f}  "
              f"cost_R={m['cost_R'].mean():.4f}  ru_atr={m['ru_atr'].mean():6.2f}  "
              f"win={win:4.1f}%  mfe_r={m['mfe_r'].mean():+.2f}  "
              f"mae_r={m['mae_r'].mean():+.2f}", flush=True)

    print("\n=== rule mix (share of rows per stop rule) ===", flush=True)
    for v, m in frames.items():
        mix = (m.group_by("rule").len()
               .with_columns((pl.col("len") / m.height * 100)
                             .round(1).alias("pct"))
               .sort("rule"))
        top = ", ".join(f"{r['rule']}={r['pct']}%" for r in mix.to_dicts())
        print(f"{v}: {top}", flush=True)

    print("\n=== EV vs risk_unit_atr quintile (cost-geometry test) ===",
          flush=True)
    for v, m in frames.items():
        mm = m.with_columns(
            pl.col("ru_atr").rank("ordinal").alias("_r"))
        mm = mm.with_columns(
            (pl.col("_r") * 5 // (mm.height + 1)).clip(0, 4).alias("q"))
        piv = (mm.group_by("q").agg(
                pl.col("r_net").mean().round(4).alias("ev"),
                pl.col("cost_R").mean().round(4).alias("cost_R"),
                pl.len().alias("n")).sort("q"))
        row = "  ".join(
            f"q{r['q']}: ev={r['ev']:+.3f} cR={r['cost_R']:.3f} "
            f"n={r['n']}" for r in piv.to_dicts())
        print(f"{v}: {row}", flush=True)

    print("\n=== per-fold D - A deltas (WF, saved runs) ===", flush=True)
    base = json.loads((REPO / "runs" / "ablation.json").read_text())
    a_folds = base["variants"]["A"]["folds"]
    for sfx in ("", "s2", "s3", "s4", "s5"):
        p = REPO / "runs" / f"ablation{sfx}.json"
        if not p.exists():
            continue
        res = json.loads(p.read_text())
        for v in ("B", "D"):
            if v not in res["variants"]:
                continue
            folds = res["variants"][v]["folds"]
            deltas = [b - a for b, a in zip(folds, a_folds)]
            wins = sum(d > 0 for d in deltas)
            print(f"{v}{sfx or '(s1)'} - A per fold: "
                  f"{[f'{d:+.2f}' for d in deltas]}  -> {wins}/8 folds > A",
                  flush=True)

    print("\n=== EV vs risk_unit_atr quintile, TEST split only ===",
          flush=True)
    for v, m in frames.items():
        mt = m.filter(pl.col("split") == "test")
        if mt.is_empty():
            continue
        lo, hi = mt["cost_R"].quantile(0.25), mt["cost_R"].quantile(0.75)
        print(f"{v}: test rows={mt.height}  ev={mt['r_net'].mean():+.4f}  "
              f"cost_R IQR=[{lo:.3f},{hi:.3f}]  "
              f"ev(low-half cost_R)="
              f"{mt.filter(pl.col('cost_R') <= mt['cost_R'].median())['r_net'].mean():+.4f}  "
              f"ev(high-half cost_R)="
              f"{mt.filter(pl.col('cost_R') > mt['cost_R'].median())['r_net'].mean():+.4f}",
              flush=True)


if __name__ == "__main__":
    main()
