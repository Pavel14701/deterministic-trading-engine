"""D.12: maker-entry revisit (pre-registered, measurable criterion).
(formerly ``scripts/d12_maker.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Question: does entering on a limit order placed delta*ATR into the zone
beat the current always-market execution (0.25R round-trip cost)?
Honest mechanics: a better entry price WIDENS the stop distance -> each
win is smaller in R but stop-outs rarer; fills are probabilistic
(missed trades = 0).  Outcome recomputed from the ACTUAL fill price via
a maker variant of the unified sim (same slip/gap penalties, entry fee
reduced to MAKER_FRAC of taker - sensitivity included).

Strategies per gated WF-B signal (n=2891, runs/d8b/wf_picks.parquet):
  market        - current: enter next-bar open (baseline, r_pess)
  maker-or-skip - limit at fill-delta*ATR, wait W bars, skip if unfilled
  maker-fallback- unfilled after W -> enter market then
Metric: mean pess R per SIGNAL.  Verdict requires maker > market on
per-signal EV, stable across folds.
"""

from __future__ import annotations

import json
import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf import resample_ohlcv  # noqa: E402
from scripts.sim_engine import (  # noqa: E402
    COMM,
    E_MULT,
    GAP,
    GEN_SLIP,
    X_MULT,
)


MAKER_FRAC = 0.3          # maker fee = 30% of taker COMM
HOLD = 48
GRID_DELTA = (0.0, 0.1, 0.25, 0.5)     # x ATR into the zone
GRID_WAIT = (1, 4, 12)                 # bars to wait for a fill

PK = pl.read_parquet(REPO / "runs" / "d8b" / "wf_picks.parquet")
print("signals:", PK.height)


def maker_sim(o, h, l, c, i0, side, sl, tp, fill, atr, maker_frac):
    """sim() with a known limit fill price at bar i0 (position open at i0)."""
    sign = 1.0 if side == "long" else -1.0
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan
    cost_r = ((COMM * (1 + maker_frac) + GEN_SLIP) * fill) / risk
    pe = E_MULT * GEN_SLIP * fill / risk
    last = min(len(c) - 1, i0 + HOLD - 1)
    for held, j in enumerate(range(i0, last + 1)):
        hs = l[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else l[j] <= tp
        if hs:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            return r - pe - (X_MULT - 1) * GEN_SLIP * abs(sl) / risk - GAP * atr / risk
        if ht:
            r = sign * (tp - fill) / risk - cost_r
            return r - pe
        if held == HOLD - 1:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            return r - pe - (X_MULT - 1) * GEN_SLIP * abs(px) / risk
    return np.nan


# market-entry sim (baseline), fill = open of i0 (identical to d6.sim)
def market_sim(o, h, l, c, i0, side, sl, tp, atr):
    sign = 1.0 if side == "long" else -1.0
    fill = o[i0]
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / risk
    pe = E_MULT * GEN_SLIP * fill / risk
    last = min(len(c) - 1, i0 + HOLD - 1)
    for held, j in enumerate(range(i0, last + 1)):
        hs = l[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else l[j] <= tp
        if hs:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            return r - pe - (X_MULT - 1) * GEN_SLIP * abs(sl) / risk - GAP * atr / risk
        if ht:
            r = sign * (tp - fill) / risk - cost_r
            return r - pe
        if held == HOLD - 1:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            return r - pe - (X_MULT - 1) * GEN_SLIP * abs(px) / risk
    return np.nan


DATA = {}
for t in sorted(PK["asset"].unique().to_list()):
    raw = resample_ohlcv(pl.read_parquet(REPO / f"data/okx/raw_{t}_1m.parquet"), "1h")
    DATA[t] = {k: raw[k].to_numpy() for k in ("open", "high", "low", "close")}
    DATA[t]["n"] = len(raw)

rows = PK.to_dicts()
base = np.array([market_sim(DATA[r["asset"]]["open"], DATA[r["asset"]]["high"],
                            DATA[r["asset"]]["low"], DATA[r["asset"]]["close"],
                            int(r["entry_idx"]) + 1, r["side"], r["sl_price"],
                            r["tp_price"], r["atr_i"]) for r in rows])
base = base[np.isfinite(base)]
print(f"baseline market-always: mean pess R per signal = {base.mean():+.3f} "
      f"(n={base.size})")

results = {}
for delta in GRID_DELTA:
    for wait in GRID_WAIT:
        contrib, filled_n = [], 0
        for r in rows:
            d = DATA[r["asset"]]
            sign = 1.0 if r["side"] == "long" else -1.0
            i0 = int(r["entry_idx"]) + 1
            limit = r["fill_price"] - sign * delta * r["atr_i"]
            if sign * (limit - r["sl_price"]) <= 0.05 * r["atr_i"]:
                contrib.append(np.nan)
                continue
            fill_bar = None
            for i in range(i0, min(i0 + wait, d["n"])):
                hit = d["low"][i] <= limit if sign > 0 else d["high"][i] >= limit
                if hit:
                    fill_bar = i
                    break
            if fill_bar is not None:
                filled_n += 1
                contrib.append(maker_sim(
                    d["open"], d["high"], d["low"], d["close"], fill_bar,
                    r["side"], r["sl_price"], r["tp_price"], limit,
                    r["atr_i"], MAKER_FRAC))
            else:
                contrib.append(np.nan)  # maker-or-skip: missed signal = 0
        c_ = np.array([x for x in contrib if np.isfinite(x)])
        ev_skip = float(c_.mean() * len(contrib) / len(rows))
        results[f"d{delta}_w{wait}"] = {
            "fill_rate": filled_n / len(rows),
            "mean_given_fill": float(c_.mean()),
            "ev_per_signal_skip": ev_skip}
        print(f"delta={delta:.2f} wait={wait:2d}: fill={filled_n / len(rows):.0%} "
              f"r|fill={c_.mean():+.3f} EV/signal(skip)={ev_skip:+.3f} "
              f"vs market {base.mean():+.3f}", flush=True)

best = max(results.items(), key=lambda kv: kv[1]["ev_per_signal_skip"])
lift = best[1]["ev_per_signal_skip"] - base.mean()
print(f"\nbest maker config: {best[0]} EV/signal={best[1]['ev_per_signal_skip']:+.3f} "
      f"(market {base.mean():+.3f}, lift {lift:+.3f})")
(REPO / "runs").mkdir(exist_ok=True)
(REPO / "runs" / "d12_maker.json").write_text(json.dumps(
    {"baseline_market": float(base.mean()), "n_signals": int(base.size),
     "grid": results, "best": best[0], "lift": float(lift)}, indent=1))
print("saved runs/d12_maker.json")
