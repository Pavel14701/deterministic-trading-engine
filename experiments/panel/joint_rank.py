"""Joint cost-aware ranking over (stop rule x TP target) pairs.

The ranker sees ALL (rule, target) rows and picks the best pair per
candidate - TP aggression becomes a ranked dimension, not a
hyper-parameter.  Labels = pess R (taker cost model incl. gap).
Ungated vs rule-table-gated picks are compared on val/test splits.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import polars as pl

from engine.features.mtf import resample_ohlcv
from engine.metrics.trade import trade_curve_stats
from engine.model.ranker import build_features, candidate_key, fit_rule_table
from engine.sim.engine import pess, sim
from engine.sim.state_machine import run_state_machine
from experiments import REPO


def main() -> None:
    """Joint-ranking experiment (ungated vs rule-table-gated)."""
    raw = resample_ohlcv(
        pl.read_parquet(REPO / "data/okx/raw_BTC-USDT_1m.parquet"), "1h"
    )
    o, h, lo, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
    stop = candidate_key(
        pl.read_parquet(REPO / "data/mtf_dataset/BTCUSDT_1h.parquet").filter(
            (pl.col("execution") == "market")
            & pl.col("r_net").is_not_nan()
            & (pl.col("exit_idx") >= 0)
            & pl.col("risk_unit").is_not_nan()
        )
    ).sort("_cand")
    print("panel rows:", stop.height,
          "targets:", sorted(stop["target"].unique().to_list()))
    stop = stop.with_columns(pl.struct(pl.exclude("_cand")).map_elements(
        pess, return_dtype=pl.Float64).alias("r_pess"))
    feats = build_features(stop, ("rule",))
    split_row = stop["split"].to_numpy()
    trm = split_row == "train"
    sizes = stop.group_by("_cand").len().sort("_cand")["len"].to_numpy()
    csp = (stop.group_by("_cand").agg(pl.col("split").first())
           .sort("_cand")["split"].to_numpy())
    rel = np.clip(np.round((stop["r_pess"].to_numpy() + 2) * 2), 0, 12)
    rel = rel.astype(int)
    rk = lgb.LGBMRanker(objective="lambdarank", n_estimators=300,
                        learning_rate=0.05, num_leaves=15,
                        min_child_samples=30, label_gain=list(range(13)),
                        random_state=7, verbosity=-1)
    rk.fit(feats[trm], rel[trm], group=sizes[csp == "train"], callbacks=[])
    stop = stop.with_columns(pl.Series("rs", rk.predict(feats)))
    table = fit_rule_table(stop.filter(pl.col("split") == "train"))
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    for tag, gate in (("joint ungated", False), ("joint +gate", True)):
        picks = (stop.sort(["_cand", "rs"]).group_by("_cand").last()
                 .with_columns(fmt.replace_strict(
                     [f"{r}|{s}" for (r, s) in table],
                     list(table.values()), default="x").alias("tr")))
        if gate:
            picks = picks.filter(pl.col("rule") == pl.col("tr"))
        picks = picks.sort("entry_idx")
        for s in ("val", "test"):
            sig = []
            for r in picks.filter(pl.col("split") == s).iter_rows(named=True):
                i0 = int(r["entry_idx"]) + 1
                if i0 >= raw.height:
                    continue
                ro, rp, jx = sim(o, h, lo, c, i0, r["side"], r["sl_price"],
                                 r["tp_price"], 48, r["atr_i"])
                if not np.isfinite(ro):
                    continue
                sig.append({"cand": r["_cand"],
                            "decision_idx": int(r["entry_idx"]),
                            "side": r["side"], "priority": 0.0,
                            "r_net": float(rp), "r_opt": float(ro),
                            "exit_idx": jx})
            taken, _ = run_state_machine(sig)
            rp_arr = np.array([t["r_net"] for t in taken])
            ro_arr = np.array([t["r_opt"] for t in taken])
            dd = trade_curve_stats(rp_arr)["max_dd_r"]
            print(f"{tag:14s} {s:5s} opt={ro_arr.mean():+.3f} "
                  f"pess={rp_arr.mean():+.3f} "
                  f"ratio={rp_arr.mean() / ro_arr.mean():.2f} "
                  f"n={rp_arr.size} dd={dd:.1f}R")


if __name__ == "__main__":
    main()