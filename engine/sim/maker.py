"""Maker-entry sims: limit-fill vs market-entry mechanics.

Library part: ``maker_sim`` / ``market_sim`` (signal -> pessimistic R
with limit-fill vs market-entry mechanics).  The maker-entry grid
experiment lives in ``engine.experiments.maker_entry``.

Question: does entering on a limit order placed delta*ATR into the zone
beat the current always-market execution (0.25R round-trip cost)?
Honest mechanics: a better entry price WIDENS the stop distance -> each
win is smaller in R but stop-outs rarer; fills are probabilistic
(missed trades = 0).  Outcome recomputed from the ACTUAL fill price via
a maker variant of the unified sim (same slip/gap penalties, entry fee
reduced to MAKER_FRAC of taker - sensitivity included).

Strategies per gated WF-B signal (n=2891, runs/walk_forward/wf_picks):
  market        - current: enter next-bar open (baseline, r_pess)
  maker-or-skip - limit at fill-delta*ATR, wait W bars, skip if unfilled
  maker-fallback- unfilled after W -> enter market then
Metric: mean pess R per SIGNAL.  Verdict requires maker > market on
per-signal EV, stable across folds.
"""

from __future__ import annotations

import numpy as np

from engine.sim.engine import COMM, E_MULT, GAP, GEN_SLIP, X_MULT


MAKER_FRAC = 0.3          # maker fee = 30% of taker COMM
HOLD = 48


def maker_sim(
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    i0: int,
    side: str,
    sl: float,
    tp: float,
    fill: float,
    atr: float,
    maker_frac: float,
) -> float:
    """sim() with a known limit fill price at bar i0 (position open at i0).

    Gap-through-stop guard (mirrors sim()): if the limit filled beyond
    the stop, the stop order fires immediately at market - a scratch
    net of costs - never a ~+1R win measured in gap-distance units.
    """
    sign = 1.0 if side == "long" else -1.0
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan
    cost_r = ((COMM * (1 + maker_frac) + GEN_SLIP) * fill) / risk
    pe = E_MULT * GEN_SLIP * fill / risk
    if (sign > 0 and fill < sl) or (sign < 0 and fill > sl):
        # filled beyond the stop -> immediate market scratch
        xtr = (X_MULT - 1) * GEN_SLIP * abs(fill) / risk
        return float(-cost_r - pe - xtr)
    last = min(len(c) - 1, i0 + HOLD - 1)
    for held, j in enumerate(range(i0, last + 1)):
        hs = lo[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else lo[j] <= tp
        if hs:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            gap = GAP * atr / risk
            xtr = (X_MULT - 1) * GEN_SLIP * abs(sl) / risk
            return float(r - pe - xtr - gap)
        if ht:
            r = sign * (tp - fill) / risk - cost_r
            return float(r - pe)
        if held == HOLD - 1:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            xtr = (X_MULT - 1) * GEN_SLIP * abs(px) / risk
            return float(r - pe - xtr)
    return np.nan


# market-entry sim (baseline), fill = open of i0 (identical to sim.sim)
def market_sim(
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    i0: int,
    side: str,
    sl: float,
    tp: float,
    atr: float,
) -> float:
    """Baseline always-market entry: fill at the open of bar ``i0``.

    Gap-through-stop guard identical to sim.sim(): a next-bar open
    beyond the stop is an immediate market scratch, never a win.
    """
    sign = 1.0 if side == "long" else -1.0
    fill = o[i0]
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / risk
    pe = E_MULT * GEN_SLIP * fill / risk
    if (sign > 0 and fill < sl) or (sign < 0 and fill > sl):
        # gap through the stop at entry -> immediate market scratch
        xtr = (X_MULT - 1) * GEN_SLIP * abs(fill) / risk
        return float(-cost_r - pe - xtr)
    last = min(len(c) - 1, i0 + HOLD - 1)
    for held, j in enumerate(range(i0, last + 1)):
        hs = lo[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else lo[j] <= tp
        if hs:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            gap = GAP * atr / risk
            xtr = (X_MULT - 1) * GEN_SLIP * abs(sl) / risk
            return float(r - pe - xtr - gap)
        if ht:
            r = sign * (tp - fill) / risk - cost_r
            return float(r - pe)
        if held == HOLD - 1:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            xtr = (X_MULT - 1) * GEN_SLIP * abs(px) / risk
            return float(r - pe - xtr)
    return np.nan

