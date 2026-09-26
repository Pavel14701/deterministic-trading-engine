# -*- coding: utf-8 -*-
"""Unit tests for the delta-hedging engine (synthetic, analytic)."""

import numpy as np

from experiments.options._hedge import delta_hedge
from experiments.options._pricing import bs


DAY = 86_400_000
BASE = 1_700_000_000_000


def _flat(s0=100.0, n=120):
    return [(BASE + i * DAY // 4, s0) for i in range(n)]  # 4 bars/day


def test_entry_is_delta_neutral():
    path = _flat()
    expiry = BASE + 30 * DAY
    res = delta_hedge(path, 80.0, expiry, 50.0, -1.0, is_call=False,
                      band=0.10)
    # entry hedge IS the first rebalance
    assert res["n_rebal"] >= 1
    # analytic check of the marked value on day 0.  The entry hedge
    # trade cancels in the marked value: val0 = cash0_entry - side*mark
    # (post-trade cash), i.e. -side*hc*premium for a single leg.
    ttmy = 30 / 365
    p0 = bs(100.0, 80.0, ttmy, 50.0, False)
    # side=-1: cash0_entry = +p0*(1-hc); val = cash0_entry - mark
    val_expected = p0 * (1 - 0.25) - p0
    d0 = BASE // DAY
    assert abs(res["daily"][d0] - val_expected) < 1e-9
    assert res["premium"] == p0


def test_flat_market_short_otm_put_pnl_is_credit():
    # spot flat at 100, K=80, 30d, vol 50: put expires worthless,
    # delta small enough that hedge never rebalances beyond entry
    path = _flat()
    expiry = BASE + 30 * DAY
    res = delta_hedge(path, 80.0, expiry, 50.0, -1.0, is_call=False,
                      band=0.50)
    p0 = bs(100.0, 80.0, 30 / 365, 50.0, False)
    assert res["n_rebal"] == 1            # entry hedge only
    assert abs(res["pnl"] - p0 * (1 - 0.25)) < 1e-9


def test_long_itm_call_settles_intrinsic():
    # spot flat at 100, K=90: call settles ITM with intrinsic 10
    path = _flat()
    expiry = BASE + 30 * DAY
    res = delta_hedge(path, 90.0, expiry, 50.0, +1.0, is_call=True,
                      band=0.50)
    p0 = bs(100.0, 90.0, 30 / 365, 50.0, True)
    assert res["n_rebal"] == 1
    assert abs(res["pnl"] - (-p0 * 1.25 + 10.0)) < 1e-9


def test_rebalance_threshold():
    # calm path: no rebalances after entry; a 20% jump forces one
    calm = _flat()
    expiry = BASE + 30 * DAY
    r1 = delta_hedge(calm, 100.0, expiry, 50.0, -1.0, is_call=True,
                     band=0.10)
    assert r1["n_rebal"] == 1
    jump = _flat()[:8] + [(BASE + 8 * DAY // 4, 120.0)] + \
        [(BASE + i * DAY // 4, 120.0) for i in range(8, 30)]
    r2 = delta_hedge(jump, 100.0, expiry, 50.0, -1.0, is_call=True,
                     band=0.10)
    assert r2["n_rebal"] >= 2


def test_daily_stream_shape():
    path = _flat()
    expiry = BASE + 30 * DAY
    res = delta_hedge(path, 80.0, expiry, 50.0, -1.0, is_call=False)
    n_days = len({p[0] // DAY for p in path})
    assert len(res["daily"]) == n_days   # one value per calendar day
    vals = [res["daily"][BASE // DAY + i] for i in range(30)]
    assert all(np.isfinite(vals))
