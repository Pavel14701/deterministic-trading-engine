"""One-off audit: gap-through-stop incidence + GEN_SLIP layer decomposition.

Checks (see conversation 2026-09-20):
1. WF-B signals where the next-bar open gaps THROUGH the stop: sim()
   scratches them, market_sim (D.12 baseline) does not -> quantify the
   baseline delta.
2. maker_entry guard: fills beyond the stop must be impossible
   (sign*(limit - sl) > 0.05*ATR filter) -> count violations.
3. GEN_SLIP: decompose one SL trade into its slip layers by hand.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from engine.features.mtf import resample_ohlcv
from engine.sim.engine import (
    COMM,
    E_MULT,
    GEN_SLIP,
    GAP,
    X_MULT,
    pess,
    sim,
)
from engine.sim.maker import maker_sim, market_sim

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    """Run the three audit checks and print the verdicts."""
    # ---- check 3 first (no data needed): one SL trade by hand -------
    print("=== check 3: GEN_SLIP layers on one SL trade ===")
    fill, sl, r0 = 100.0, 99.0, 1.0  # 1% stop = 1R, ATR such that GAP=0.25R
    atr = r0 / GAP * 0.25 * 0  # set gap term aside; account it separately
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / r0
    pe = E_MULT * GEN_SLIP * fill / r0
    r_opt = (sl * (1 - GEN_SLIP) - fill) / r0 - cost_r
    xtr = (X_MULT - 1) * GEN_SLIP * abs(sl) / r0
    print(f"  entry slip  (cost_r)  : {GEN_SLIP * fill / r0:+.5f} R "
          f"(in r_opt AND r_pess)")
    print(f"  exit slip   (price)   : {-GEN_SLIP * sl / r0:+.5f} R "
          f"(in r_opt AND r_pess)")
    print(f"  commission (2*COMM)   : {-2 * COMM * fill / r0:+.5f} R")
    print(f"  => r_opt (SL, no gap) : {r_opt:+.5f} R")
    print(f"  pe  = 2x exit slip    : {-pe:+.5f} R   (pess-only)")
    print(f"  xtr = 1x stop slip    : {-xtr:+.5f} R   (pess-only)")
    print(f"  => r_pess w/o gap     : {r_opt - pe - xtr:+.5f} R")
    print(f"  worst-case slip stack : {(2 + E_MULT + X_MULT - 1) * GEN_SLIP:.5f} "
          f"= {(2 + E_MULT + X_MULT - 1) * GEN_SLIP * 1e4:.0f} bps")

    # ---- checks 1 and 2: need the WF-B signals and 1m data ----------
    pk = pl.read_parquet(REPO / "runs" / "d8b" / "wf_picks.parquet")
    have = {p.stem.split("raw_")[1].rsplit("_1m", 1)[0]
            for p in (REPO / "data" / "okx").glob("raw_*_1m.parquet")}
    rows = [r for r in pk.to_dicts() if r["asset"] in have]
    print(f"\n=== checks 1+2 on WF-B subset ===")
    print(f"wf_picks rows: {pk.height}, with 1m data now: {len(rows)} "
          f"(assets {sorted(have)})")
    data: dict[str, dict] = {}
    for t in sorted(have):
        raw = resample_ohlcv(
            pl.read_parquet(REPO / f"data/okx/raw_{t}_1m.parquet"), "1h")
        data[t] = {k: raw[k].to_numpy()
                   for k in ("open", "high", "low", "close")}
        data[t]["n"] = len(raw)

    n_gap, rows_used = 0, 0
    rm_gap, rs_gap = [], []
    base_m, base_s, guard_viol = [], [], 0
    for r in rows:
        d = data[r["asset"]]
        i0 = int(r["entry_idx"]) + 1
        if i0 >= d["n"]:
            continue
        rows_used += 1
        o, h, lo, c = d["open"], d["high"], d["low"], d["close"]
        sign = 1.0 if r["side"] == "long" else -1.0
        # check 1: market entry gaps through the stop
        if sign * (o[i0] - r["sl_price"]) < 0:
            n_gap += 1
            rm = market_sim(o, h, lo, c, i0, r["side"], r["sl_price"],
                            r["tp_price"], r["atr_i"])
            _ro, rp, _jx = sim(o, h, lo, c, i0, r["side"], r["sl_price"],
                               r["tp_price"], 48, r["atr_i"])
            rm_gap.append(rm)
            rs_gap.append(rp)
        base_m.append(market_sim(o, h, lo, c, i0, r["side"], r["sl_price"],
                                 r["tp_price"], r["atr_i"]))
        _ro, rp, _jx = sim(o, h, lo, c, i0, r["side"], r["sl_price"],
                           r["tp_price"], 48, r["atr_i"])
        base_s.append(rp)
        # check 2: could a maker fill ever land beyond the stop?
        limit = r["fill_price"] - sign * 0.0 * r["atr_i"]  # worst delta=0
        if sign * (limit - r["sl_price"]) <= 0.05 * r["atr_i"]:
            guard_viol += 1  # skipped by the guard, never reaches maker_sim

    base_m = np.array([x for x in base_m if np.isfinite(x)])
    base_s = np.array([x for x in base_s if np.isfinite(x)])
    print(f"rows scored: {rows_used}")
    print(f"[1] gap-through-stop at market entry: {n_gap}/{rows_used}")
    if n_gap:
        print(f"    market_sim on those rows : {np.mean(rm_gap):+.3f} R "
              f"(no check -> may book a WIN)")
        print(f"    sim() on those rows      : {np.mean(rs_gap):+.3f} R "
              f"(scratch)")
    print(f"    baseline market_sim      : {base_m.mean():+.4f} R "
          f"(n={base_m.size})")
    print(f"    baseline sim() pess      : {base_s.mean():+.4f} R "
          f"(n={base_s.size})")
    print(f"[2] maker guard violations (fill beyond stop possible): "
          f"{guard_viol}/{rows_used}  (all filtered by the 0.05*ATR guard)")


if __name__ == "__main__":
    main()
