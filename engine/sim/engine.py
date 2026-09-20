"""Unified event simulator primitives.

Library part: ``sim`` (one signal -> optimistic/pessimistic R, net of
costs) and ``pess`` (per-row pessimistic R for labeled panel rows).
The cost constants are the validated taker-path model.  The joint
ranking experiment over (stop rule x TP target) pairs lives in
``engine.experiments.joint_rank``.
"""

from __future__ import annotations

from typing import Any

import numpy as np


GEN_SLIP, COMM, GAP, E_MULT, X_MULT = 0.0005, 0.001, 0.25, 2.0, 2.0


def sim(
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    i0: int,
    side: str,
    sl: float,
    tp: float,
    hold: int,
    atr: float,
    risk_ref: float | None = None,
) -> tuple[float, float, int]:
    """Simulate one signal from entry index ``i0``.

    Returns ``(r_opt, r_pess, exit_idx)``: optimistic and pessimistic
    net R (both net of the taker cost model) and the bar index of the
    exit.  NaN pair with ``-1`` = no exit within the hold window.

    ``risk_ref``: intended risk distance (panel ``risk_unit``) used as
    the R denominator.  Defaults to ``|entry fill - sl|``.  It matters
    for the gap-through-stop case: when the entry bar OPENS already
    beyond the stop, live the stop order fires immediately at market -
    a scratch (~0 net of costs) - never a ~+1R win measured in
    gap-distance units (pinned by the ranker-only audit).
    """
    sign = 1.0 if side == "long" else -1.0
    fill = o[i0]
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan, np.nan, -1
    r0 = risk_ref if (risk_ref is not None and risk_ref > 0) else risk
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / r0
    pe = E_MULT * GEN_SLIP * fill / r0
    if (sign > 0 and fill < sl) or (sign < 0 and fill > sl):
        # gap through the stop at entry -> immediate market scratch
        xtr = (X_MULT - 1) * GEN_SLIP * abs(fill) / r0
        return -cost_r, -cost_r - pe - xtr, i0
    last = min(len(c) - 1, i0 + 47)
    for held, j in enumerate(range(i0, last + 1)):
        hs = lo[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else lo[j] <= tp
        if hs:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / r0 - cost_r
            gap = GAP * atr / r0
            xtr = (X_MULT - 1) * GEN_SLIP * abs(sl) / r0
            return r, r - pe - xtr - gap, j
        if ht:
            r = sign * (tp - fill) / r0 - cost_r
            return r, r - pe, j
        if held == 47:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / r0 - cost_r
            xtr = (X_MULT - 1) * GEN_SLIP * abs(px) / r0
            return r, r - pe - xtr, j
    return np.nan, np.nan, -1


def pess(row: dict[str, Any]) -> float:
    """Pessimistic net R of one labeled panel row (taker cost model)."""
    risk, fill = row["risk_unit"], row["fill_price"]
    d = E_MULT * GEN_SLIP * fill / risk
    if row["exit_reason"] == "sl":
        d += (X_MULT - 1) * GEN_SLIP * abs(row["sl_price"]) / risk
        d += GAP * row["atr_i"] / risk
    elif row["exit_reason"] == "time":
        d += (X_MULT - 1) * GEN_SLIP * abs(row["exit_price"]) / risk
    return float(row["r_net"]) - d


