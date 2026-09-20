"""Unit tests for the maker-entry simulator (scripts/maker_entry.py).

Pins the two effects the maker-entry study measured: fee saving on the entry
side and (for a limit inside the zone) a wider stop distance.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.sim.maker import maker_sim, market_sim


def _flat_path(n: int = 60, price: float = 100.0):
    o = np.full(n, price)
    h = np.full(n, price)
    lo = np.full(n, price)
    c = np.full(n, price)
    return o, h, lo, c


def _zone_path(n: int = 60):
    """Long setup: entry zone 100, dip to the limit at bar 2, TP later."""
    o = np.full(n, 100.0)
    h = np.full(n, 100.0)
    lo = np.full(n, 100.0)
    c = np.full(n, 100.0)
    lo[2] = 99.5  # dips into the limit (delta=0.5 ATR, ATR=1)
    h[10] = 102.0  # touches tp=102
    return o, h, lo, c


class TestMarketSim:
    def test_baseline_matches_cost_model(self) -> None:
        o, h, lo, c = _zone_path()
        r = market_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 1.0)
        # tp=102, fill=100, risk=1 -> 2R gross minus 0.25R cost minus pe
        assert r == pytest.approx(2.0 - 0.25 - 0.1)

    def test_short_tp_hit(self) -> None:
        o, h, lo, c = _zone_path()
        # tp=99.5 is touched by the dip at bar 2 (lo[2]=99.5)
        r = market_sim(o, h, lo, c, 0, "short", 101.0, 99.5, 1.0)
        assert r == pytest.approx((100.0 - 99.5) - 0.25 - 0.1)


class TestMakerSim:
    def test_better_price_keeps_wider_risk(self) -> None:
        o, h, lo, c = _zone_path()
        # limit at 99.5 fills at bar 2; sl 99 -> risk widens 1.0 -> 0.5? no:
        # limit 99.5, sl 99.0 -> risk = 0.5 (HALVED), tp unchanged at 102.
        r = maker_sim(o, h, lo, c, 2, "long", 99.0, 102.0, 99.5, 1.0, 0.3)
        gross = (102.0 - 99.5) / 0.5  # 5R gross (diluted risk)
        cost = (0.001 + 0.0003 + 0.0005) * 99.5 / 0.5
        pe = 2 * 0.0005 * 99.5 / 0.5
        assert r == pytest.approx(gross - cost - pe)

    def test_maker_fee_smaller_than_taker(self) -> None:
        # same geometry, maker entry fee 30% of taker -> strictly better R
        o, h, lo, c = _zone_path()
        r_maker = maker_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 100.0, 1.0, 0.3)
        r_market = market_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 1.0)
        assert r_maker == pytest.approx(r_market + 0.7 * 0.001 * 100.0)

    def test_timeout_when_nothing_touched(self) -> None:
        o, h, lo, c = _flat_path()
        # entry "filled" at 100 but neither sl nor tp touched -> timeout
        r = maker_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 100.0, 1.0, 0.3)
        # timeout: close-fill slip (-0.05) + maker cost 0.18 + pe 0.1
        #          + extra-X penalty 0.0005*99.95
        assert r == pytest.approx(-0.05 - 0.18 - 0.1 - 0.0005 * 99.95)

    def test_invalid_risk_returns_nan(self) -> None:
        o, h, lo, c = _zone_path()
        assert np.isnan(maker_sim(o, h, lo, c, 0, "long", 99.5, 102.0, 99.5, 1.0, 0.3))

    def test_gap_through_stop_is_a_scratch_not_a_win(self) -> None:
        # limit filled BELOW the stop (long): stop fires immediately at
        # market -> scratch net of costs, never a +R win in gap units
        o, h, lo, c = _zone_path()
        o[:] = 98.0  # fill 98 < sl 99
        r = maker_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 98.0, 1.0, 0.3)
        cost = (0.0013 + 0.0005) * 98.0
        pe = 2 * 0.0005 * 98.0
        xtr = 0.0005 * 98.0
        assert r == pytest.approx(-cost - pe - xtr)
        assert r < 0


class TestMarketSimGap:
    def test_gap_through_stop_is_a_scratch_not_a_win(self) -> None:
        # next-bar open beyond the stop -> immediate market scratch
        o, h, lo, c = _zone_path()
        o[0] = 98.0  # market fill 98 < sl 99
        r = market_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 1.0)
        cost = (0.002 + 0.0005) * 98.0
        pe = 2 * 0.0005 * 98.0
        xtr = 0.0005 * 98.0
        assert r == pytest.approx(-cost - pe - xtr)
        assert r < 0

    def test_gap_matches_sim_semantics(self) -> None:
        from engine.sim.engine import sim

        o, h, lo, c = _zone_path()
        o[:] = 98.0
        _ro, rp, jx = sim(o, h, lo, c, 0, "long", 99.0, 102.0, 48, 1.0)
        rm = market_sim(o, h, lo, c, 0, "long", 99.0, 102.0, 1.0)
        assert rm == pytest.approx(rp)
        assert jx == 0
