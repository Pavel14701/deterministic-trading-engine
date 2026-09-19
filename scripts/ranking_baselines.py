"""D.4: cost-aware stop-rule ranking head.
(formerly ``scripts/d4_ranking.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Task: for each candidate, rank the 11 stop rules by their PESSIMISTIC
net R (r_net minus the D.3 cost delta: entry slip x2, SL exit slip x2,
gap 0.25xATR).  The label IS the planning metric, so the ranker is
cost-aware by construction.  Features: the stop-head feature set plus
risk_pct (risk_unit/fill) and pess cost in R - the leverage the
ranking needs.

Baseline: current LGBM stop-head pick.  Criterion: test pess_base EV
> +0.25R (from +0.150R) on the state-machine replay, ratio > 0.5.
"""

from __future__ import annotations

import sys

from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf_model import (  # noqa: E402
    apply_rule_table,
    build_features,
    candidate_key,
    fit_rule_table,
    trade_curve_stats,
)
from engine.state_machine import run_state_machine


GEN_SLIP = 0.0005
GAP = 0.25
E_MULT, X_MULT = 2.0, 2.0


def pess_r(row: dict) -> float:
    risk, fill = row["risk_unit"], row["fill_price"]
    delta = E_MULT * GEN_SLIP * fill / risk
    if row["exit_reason"] == "sl":
        delta += (X_MULT - 1.0) * GEN_SLIP * abs(row["sl_price"]) / risk
        delta += GAP * row["atr_i"] / risk
    elif row["exit_reason"] == "time":
        delta += (X_MULT - 1.0) * GEN_SLIP * abs(row["exit_price"]) / risk
    return row["r_net"] - delta


stop = candidate_key(
    pl.read_parquet(REPO / "data/mtf_dataset/BTCUSDT_1h.parquet").filter(
        (pl.col("execution") == "market")
        & (pl.col("target") == 2.0)
        & pl.col("r_net").is_not_nan()
        & (pl.col("exit_idx") >= 0)
    )
)
stop = (
    stop
    .with_columns(
        pl.struct(pl.exclude("_cand"))
        .map_elements(lambda r: pess_r(r), return_dtype=pl.Float64)
        .alias("r_pess")
    )
    .with_columns(
        (pl.col("risk_unit") / pl.col("fill_price")).alias("risk_pct"),
        (0.0025 * pl.col("fill_price") / pl.col("risk_unit")).alias("cost_R"),
    )
    .sort("_cand")
)
keyed = stop
feats = build_features(stop, ("rule",))
for c in ("risk_pct", "cost_R"):
    feats[c] = stop[c].to_numpy()

cand_arr = stop["_cand"].to_numpy()
splits_row = stop["split"].to_numpy()
tr = splits_row == "train"
sizes_all = stop.group_by("_cand").len().sort("_cand")["len"].to_numpy()
cand_split = (
    stop.group_by("_cand").agg(pl.col("split").first()).sort("_cand")["split"].to_numpy()
)
sizes = sizes_all[cand_split == "train"]
rel = np.clip(np.round((stop["r_pess"].to_numpy() + 2.0) * 2.0), 0, 12).astype(int)

tr = splits_row == "train"
ranker = lgb.LGBMRanker(
    objective="lambdarank",
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=30,
    label_gain=list(range(13)),
    random_state=7,
    verbosity=-1,
)
ranker.fit(
    feats[tr], rel[tr], group=sizes,
    callbacks=[])
print("ranker trained")

stop = stop.with_columns(pl.Series("rank_score", ranker.predict(feats)))
rk_picks = stop.sort(["_cand", "rank_score"]).group_by("_cand").last()

table = fit_rule_table(stop.filter(pl.col("split") == "train"))
tbl = apply_rule_table(candidate_key(stop), table).select("_cand", pl.col("r_net").alias("tbl_r"))
booster = lgb.Booster(model_file=str(REPO / "data/mtf_model/stop_head.txt"))
keyed2 = keyed.with_columns(pl.Series("_p", booster.predict(build_features(stop, ("rule",)))))
sh_picks = keyed2.sort(["_cand", "_p"]).group_by("_cand").last()

meta = stop.select(["_cand", "entry_idx", "side", "r_net", "r_pess", "risk_unit", "fill_price", "sl_price", "atr_i", "exit_reason", "exit_price", "exit_idx", "split"])


def replay(picks: pl.DataFrame, tag: str) -> None:
    p = picks.join(meta, on="_cand", how="semi").sort("entry_idx")
    for s in ("val", "test"):
        sub = p.filter(pl.col("split") == s)
        signals = [
            {"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
             "side": r["side"], "priority": 0.0,
             "r_net": float(r["r_net"]), "exit_idx": int(r["exit_idx"])}
            for r in sub.iter_rows(named=True)
        ]
        taken, _ = run_state_machine(signals)
        rows = {t["cand"] for t in taken}
        td = sub.filter(pl.col("_cand").is_in(list(rows)))
        r_opt = td["r_net"].to_numpy()
        r_pes = td["r_pess"].to_numpy()
        dd = trade_curve_stats(r_opt)["max_dd_r"]
        print(f"{tag:8s} {s:5s} opt={r_opt.mean():+.3f} pess={r_pes.mean():+.3f} "
              f"ratio={r_pes.mean() / r_opt.mean():.2f} n={r_opt.size} dd={dd:.1f}R")


print(f"{'head':8s} {'split':5s} {'EV opt/pess (state machine, BTC 1h consensus-ish)':>10s}")
replay(sh_picks, "stophead")
replay(rk_picks, "ranker")
fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
rk_gated = (
    rk_picks.with_columns(
        fmt.replace_strict(
            [f"{r}|{s}" for (r, s) in table], list(table.values()), default="x"
        ).alias("tbl_rule")
    )
    .filter(pl.col("rule") == pl.col("tbl_rule"))
)
replay(rk_gated, "rk+gate")
