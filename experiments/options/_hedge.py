# -*- coding: utf-8 -*-
"""Delta-hedging engine for wave-4 options experiments.

Infrastructure only -- no strategy, no prereg here.  Frozen
mechanics (will be referenced by the 1.1 prereg):

- ONE option leg, side +1 long / -1 short, entry premium marked at
  the leg IV (real print-IV per _runner.entry_iv, chosen by the
  caller); transaction haircut HAIRCUT applied on the option trade
  (same convention as _runner/strangle_carry).
- Underlying hedge: Binance 1H close path; target position
  Q = -side * delta(option); rebalance when |Q - Q_target| > band
  (frozen default band 0.10 delta-units); underlying rebalance is
  cost-free (maker/perp assumption, declared).
- Settlement at expiry spot, cash accounting:
    cash0 = -side * premium * (1 + side * hc)      [entry]
    cash  -= s * dQ                                 [hedge trades]
    cash  += side * intrinsic                       [settlement]
    cash  += s_T * Q                                [hedge close]
  pnl = cash_end.  Marked account value (for the daily stream):
  cash + Q*s + side*option_mark(t).
- IV is held constant along the path (declared simplification;
  IV-dynamics marking belongs to the caller / prereg read-out).
"""

from __future__ import annotations


__version__ = "1.0.0"

import numpy as np

from experiments.options._pricing import bs, bs_greeks


MSEC_DAY = 86_400_000
HAIRCUT = 0.25


def delta_hedge(path: list, k: float, expiry: float, iv: float,
                side: float, is_call: bool, band: float = 0.10,
                hc: float = HAIRCUT) -> dict:
    """Run the hedge over path = [(ts_ms, spot), ...] sorted by ts.

    Returns dict(pnl, premium, n_rebal, final_cash, daily={day_id:
    marked account value at last bar of day}).
    """
    ts_arr = np.array([p[0] for p in path], dtype=np.int64)
    s_arr = np.array([p[1] for p in path], dtype=np.float64)
    t0 = int(ts_arr[0])
    ttm0 = max((expiry - t0) / (365 * MSEC_DAY), 1e-9)
    p0 = bs(float(s_arr[0]), k, ttm0, iv, is_call)
    cash = -side * p0 * (1 + side * hc)
    q = 0.0
    n_rebal = 0
    daily: dict[int, float] = {}
    s_last = float(s_arr[0])
    first = True
    for t, s in zip(ts_arr, s_arr):
        s = float(s)
        ttm = max((expiry - int(t)) / (365 * MSEC_DAY), 0.0)
        g = bs_greeks(s, k, ttm, iv, is_call)
        q_tgt = -side * g["delta"]
        if (first or abs(q_tgt - q) > band) and ttm > 0:
            # entry hedge is always established delta-neutral
            cash -= s * (q_tgt - q)
            q = q_tgt
            n_rebal += 1
        first = False
        mark = bs(s, k, ttm, iv, is_call)
        val = cash + q * s + side * mark
        daily[int(t // MSEC_DAY)] = val
        s_last = s
    intrinsic = max(s_last - k, 0.0) if is_call else max(k - s_last, 0.0)
    cash += side * intrinsic
    cash += s_last * q
    return dict(pnl=float(cash), premium=float(p0), n_rebal=n_rebal,
                final_cash=float(cash), daily=daily)
