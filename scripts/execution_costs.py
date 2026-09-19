"""D.3: optimistic vs pessimistic execution on state-machine trades.
(formerly ``scripts/d3_execution.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Cost model (all deltas in R, applied on top of stored optimistic r):

- entry slippage x2: extra entry slip vs the 0.05% generator default
  (0.5x spread on BTC perp is well inside that);
- SL is a market order: exit slippage x2 plus a gap-through-stop
  buffer of G x ATR (G = 0.25 base case, 0.5 stress);
- TP is a limit fill: no exit cost (partial fills ignored at the
  BTC 1h candidate size - position < 1% of bar volume);
- timeouts / rejections: not modelled (maker variants were already
  rejected in the dataset; machine trades market fills only).

Criterion: EV_pess / EV_opt >= 0.75 (loss <= 25%).
"""

from __future__ import annotations

import sys

from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.mtf_model import (  # noqa: E402
    apply_rule_table,
    build_features,
    candidate_key,
    fit_rule_table,
    trade_curve_stats,
)
from ai.state_machine import run_state_machine


RULE_COL = "rule"
GEN_SLIP = 0.0005

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
    .filter(pl.col("rule") == pl.col("tbl_rule"))
    .sort("entry_idx")
)

EXIT_SLIP_MULT = 2.0
ENTRY_SLIP_MULT = 2.0


def pess_r(row: dict, gap_atr_mult: float) -> float:
    risk = row["risk_unit"]
    fill = row["fill_price"]
    delta = ENTRY_SLIP_MULT * GEN_SLIP * fill / risk  # worse entry
    if row["exit_reason"] == "sl":
        # exit slippage x2 (one GEN_SLIP already inside r) + gap buffer
        delta += (EXIT_SLIP_MULT - 1.0) * GEN_SLIP * abs(row["sl_price"]) / risk
        delta += gap_atr_mult * row["atr_i"] / risk
    elif row["exit_reason"] == "time":
        delta += (EXIT_SLIP_MULT - 1.0) * GEN_SLIP * abs(row["exit_price"]) / risk
    return row["r_net"] - delta


print(f"{'split':6s} {'scenario':12s} {'EV':>7s} {'n':>5s} {'DD':>6s} {'ratio':>6s}")
for s in ("val", "test"):
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
    taken, _ = run_state_machine(signals)
    rows = {t["cand"]: t for t in taken}
    td = sub.filter(pl.col("_cand").is_in(list(rows.keys())))
    r_opt = td["r_net"].to_numpy()
    stat = trade_curve_stats(r_opt)
    print(f"{s:6s} {'optimistic':12s} {r_opt.mean():+7.3f} {r_opt.size:5d} "
          f"{stat['max_dd_r']:6.1f} {'1.00':>6s}")
    for name, gap in (("pess_base", 0.25), ("pess_stress", 0.5)):
        rp = np.array([pess_r(r, gap) for r in td.iter_rows(named=True)])
        st = trade_curve_stats(rp)
        ratio = rp.mean() / r_opt.mean()
        print(f"{s:6s} {name:12s} {rp.mean():+7.3f} {rp.size:5d} "
              f"{st['max_dd_r']:6.1f} {ratio:6.2f}")
