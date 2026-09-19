"""D.1: isolated backtest vs state machine replay on real policy picks.

Isolated: every consensus candidate trades (current report EV).
Machine: same signals walked through run_state_machine (one slot,
reverse ignored, cooldown=0).  EV gap = the isolation illusion.
"""

from __future__ import annotations

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
    trade_curve_stats,
)
from ai.src.state_machine import run_state_machine

RULE_COL = "rule"

stop = (
    pl.read_parquet(REPO / "data/mtf_dataset/BTCUSDT_1h.parquet")
    .filter(
        (pl.col("execution") == "market")
        & (pl.col("target") == 2.0)
        & pl.col("r_net").is_not_nan()
        & (pl.col("exit_idx") >= 0)
    )
)
booster = lgb.Booster(model_file=str(REPO / "data/mtf_model/stop_head.txt"))
keyed = candidate_key(stop).with_columns(
    pl.Series("_p", booster.predict(build_features(stop, (RULE_COL,))))
)
picks = keyed.sort(["_cand", "_p"]).group_by("_cand").last()
table = fit_rule_table(stop.filter(pl.col("split") == "train"))
tbl = apply_rule_table(candidate_key(stop), table).select(
    "_cand", pl.col("r_net").alias("tbl_r")
)
picks = (
    picks.join(tbl, on="_cand", how="left")
    .with_columns(
        pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
        .replace_strict(
            [f"{r}|{s}" for (r, s) in table],
            list(table.values()),
            default="zone:1.0",
        )
        .alias("tbl_rule")
    )
    .filter(pl.col("rule") == pl.col("tbl_rule"))  # consensus subset
    .sort("entry_idx")
)

for s in ("train", "val", "test"):
    sub = picks.filter(pl.col("split") == s)
    signals = [
        {
            "cand": r["_cand"],
            "decision_idx": int(r["entry_idx"]),
            "side": r["side"],
            "priority": float(r["_p"]),
            "r_net": float(r["r_net"]),
            "exit_idx": int(r["exit_idx"]),
        }
        for r in sub.iter_rows(named=True)
    ]
    taken, skipped = run_state_machine(
        signals, cooldown=0, allow_reverse=False
    )
    iso = sub["r_net"].to_numpy()
    mac = np.array([t["r_net"] for t in taken])
    reasons = {}
    for x in skipped:
        reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
    print(f"--- {s} ---")
    print(f"isolated : ev={iso.mean():+.3f} n={iso.size} "
          f"dd={trade_curve_stats(iso)['max_dd_r']:.1f}R")
    print(f"machine  : ev={mac.mean():+.3f} n={mac.size} "
          f"dd={trade_curve_stats(mac)['max_dd_r']:.1f}R")
    print(f"skipped  : {reasons}")
    pt = np.mean([t["priority"] for t in taken])
    ps = np.mean([x["priority"] for x in skipped]) if skipped else float("nan")
    print(f"p taken={pt:.3f} skipped={ps:.3f}")
    print(f"EV gap   : {mac.mean() - iso.mean():+.3f} "
          f"({100 * (mac.mean() - iso.mean()) / iso.mean():+.1f}%)")
