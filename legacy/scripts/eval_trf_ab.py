"""A/B: consensus gate vs consensus gate + transformer voice (D.2 step 3).

Baseline: trade only candidates where the LGBM stop-head pick equals
the fitted rule-table pick.  Variant: additionally require the
transformer window score ``p_trf`` (P[best rule wins]) to clear a
threshold calibrated on val.  Paired bootstrap of the EV diff on val
and test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.src.mtf_model import (  # noqa: E402
    apply_rule_table,
    build_features,
    candidate_key,
    fit_rule_table,
    paired_bootstrap_diff,
    select_stop_rows,
    trade_curve_stats,
)

RULE_COL = "rule"


def picks_frame(stop: pl.DataFrame, booster: lgb.Booster) -> pl.DataFrame:
    """Per-candidate LGBM pick: (rule, r_net, p, regime, side, split)."""
    feats = build_features(stop, (RULE_COL,))
    p = booster.predict(feats)
    keyed = candidate_key(stop).with_columns(pl.Series("_p", p))
    return (
        keyed.sort(["_cand", "_p"])
        .group_by("_cand")
        .last()
        .sort("entry_idx")
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="D.2: transformer A/B")
    ap.add_argument("--mtf", default="data/mtf_dataset/BTCUSDT_1h.parquet")
    ap.add_argument("--booster", default="data/mtf_model/stop_head.txt")
    ap.add_argument("--probs", default="data/trf_model/probs.npz")
    ap.add_argument("--win", default="data/trf_dataset/BTCUSDT_1h_win.npz")
    args = ap.parse_args()

    stop = select_stop_rows(pl.read_parquet(REPO / args.mtf)).filter(
        pl.col("r_net").is_not_nan()
    )
    booster = lgb.Booster(model_file=str(REPO / args.booster))
    d = picks_frame(stop, booster)

    table = fit_rule_table(stop.filter(pl.col("split") == "train"))
    tbl = apply_rule_table(candidate_key(stop), table).select(
        "_cand", pl.col("r_net").alias("tbl_r")
    )
    d = d.join(tbl, on="_cand", how="left").with_columns(
        pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
        .replace_strict(
            [f"{r}|{s}" for (r, s) in table],
            list(table.values()),
            default=table.get(("unknown", "long"), "zone:1.0"),
        )
        .alias("tbl_rule")
    )
    d = d.with_columns(
        (pl.col("rule") == pl.col("tbl_rule")).alias("consensus")
    )

    # attach transformer probability by (entry_idx, side)
    win = np.load(REPO / args.win, allow_pickle=False)
    pr = np.load(REPO / args.probs, allow_pickle=False)
    key_arr = np.array(
        [f"{i}_{s}" for i, s in zip(win["entry_idx"], win["side"])]
    )
    p_map = dict(zip(key_arr.tolist(), pr["p"].tolist()))
    d = d.with_columns(
        pl.col("_cand")
        .replace_strict(p_map, default=np.nan, return_dtype=pl.Float64)
        .alias("p_trf")
    )

    out: dict = {}
    for s in ("val", "test"):
        dd = d.filter(pl.col("split") == s)
        base = dd.filter(pl.col("consensus"))
        # threshold calibrated on val only
        if s == "val":
            grid = np.arange(0.5, 0.95, 0.05)
            evs = {}
            for t in grid:
                g = base.filter(pl.col("p_trf") >= t)
                evs[round(float(t), 2)] = (
                    float(g["r_net"].mean()) if g.height else float("nan")
                )
            best_t = max(
                (t for t in evs if np.isfinite(evs[t])),
                key=lambda t: evs[t],
                default=0.5,
            )
        gated = base.filter(pl.col("p_trf") >= best_t)
        dropped = base.filter(pl.col("p_trf") < best_t)

        rb = base["r_net"].to_numpy()
        rg = gated["r_net"].to_numpy()
        out[s] = {
            "threshold": float(best_t),
            "val_grid_ev": {str(k): round(v, 3) for k, v in evs.items()}
            if s == "val"
            else None,
            "baseline": {
                "ev": float(rb.mean()),
                "n": int(rb.size),
                **trade_curve_stats(rb),
            },
            "gated": {
                "ev": float(rg.mean()) if rg.size else float("nan"),
                "n": int(rg.size),
                **trade_curve_stats(rg),
            },
            "dropped_ev": float(dropped["r_net"].mean())
            if dropped.height
            else None,
            "dropped_n": int(dropped.height),
        }
        if rg.size and dropped.height:
            # two-sample bootstrap: gated and dropped are disjoint trade
            # sets, so the paired test does not apply; resample each set
            # independently and bootstrap the EV difference
            rng = np.random.default_rng(7)
            diffs = []
            for _ in range(2000):
                g = rng.choice(rg, size=rg.size, replace=True)
                b = rng.choice(dropped["r_net"].to_numpy(), size=dropped.height, replace=True)
                diffs.append(g.mean() - b.mean())
            diffs = np.asarray(diffs)
            out[s]["gated_vs_dropped_diff"] = {
                "diff": round(float(rg.mean() - dropped["r_net"].mean()), 3),
                "lo": round(float(np.quantile(diffs, 0.025)), 3),
                "hi": round(float(np.quantile(diffs, 0.975)), 3),
                "p_le0": round(float((diffs <= 0).mean()), 3),
                "n": int(rg.size),
            }

    import json

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
