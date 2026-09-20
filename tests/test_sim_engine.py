"""Unit tests for the unified event simulator (scripts/sim_engine.py).

Expected R values are derived by hand from the cost constants
(GEN_SLIP=0.0005, COMM=0.001 per side, E_MULT=X_MULT=2, GAP=0.25)
on synthetic flat price paths, so these tests also pin the cost model.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.sim import sim


FLAT = 100.0


def _flat_path(n: int = 60, price: float = FLAT):
    o = np.full(n, price)
    h = np.full(n, price)
    lo = np.full(n, price)
    c = np.full(n, price)
    return o, h, lo, c


COST = (2 * 0.001 + 0.0005) * FLAT  # 0.25R at 1.0 price-unit risk
PE = 2 * 0.0005 * FLAT  # exit-slip pess adjustment at 1.0 risk


class TestSimLong:
    def test_take_profit_hit(self) -> None:
        o, h, lo, c = _flat_path()
        h[5] = 101.0  # tp=101 touched at bar 5
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48, 1.0)
        assert j == 5
        assert r_opt == pytest.approx(1.0 - COST)
        assert r_pess == pytest.approx(1.0 - COST - PE)

    def test_stop_loss_hit(self) -> None:
        o, h, lo, c = _flat_path()
        lo[3] = 99.0  # sl touched at bar 3
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48, 1.0)
        assert j == 3
        # sl fill with exit slip: (99*0.9995 - 100)/1 - 0.25
        base = (99.0 * 0.9995 - 100.0) - COST
        assert r_opt == pytest.approx(base)
        # pessimistic adds exit slip, gap-through and extra-X penalties
        expected = base - PE - (2 - 1) * 0.0005 * 99.0 - 0.25 * 1.0
        assert r_pess == pytest.approx(expected)

    def test_timeout_exits_at_close(self) -> None:
        o, h, lo, c = _flat_path(n=60)
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48, 1.0)
        assert j == 47  # held == HOLD-1
        # timeout exit pays entry spread on the close fill: px = c*0.9995
        r_timeout = (FLAT * 0.9995 - FLAT) - COST  # -0.30
        assert r_opt == pytest.approx(r_timeout)
        assert r_pess == pytest.approx(r_timeout - PE - 0.0005 * (FLAT * 0.9995))

    def test_both_hit_in_entry_bar_is_stop_first(self) -> None:
        # pessimistic intrabar ordering: stop checked before target
        o, h, lo, c = _flat_path()
        lo[0] = 99.0
        h[0] = 101.0
        r_opt, _r, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48, 1.0)
        assert j == 0
        assert r_opt < 0  # stopped, not target


class TestSimShort:
    def test_take_profit_hit(self) -> None:
        o, h, lo, c = _flat_path()
        lo[4] = 99.0
        r_opt, _r, j = sim(o, h, lo, c, 0, "short", 101.0, 99.0, 48, 1.0)
        assert j == 4
        assert r_opt == pytest.approx(1.0 - COST)

    def test_stop_loss_hit(self) -> None:
        o, h, lo, c = _flat_path()
        h[2] = 101.0
        _r_opt, r_pess, j = sim(o, h, lo, c, 0, "short", 101.0, 99.0, 48, 1.0)
        assert j == 2
        assert r_pess < -1.0  # stop + gap penalty dominates

    def test_zero_risk_is_invalid(self) -> None:
        o, h, lo, c = _flat_path()
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "long", 100.0, 101.0, 48, 1.0)
        assert not np.isfinite(r_opt)
        assert not np.isfinite(r_pess)
        assert j == -1

    def test_entry_bar_shift(self) -> None:
        # entering at a later i0 shifts both fill and horizon
        o, h, lo, c = _flat_path()
        h[10] = 101.0
        r_opt, _r, j = sim(o, h, lo, c, 8, "long", 99.0, 101.0, 48, 1.0)
        assert j == 10
        assert r_opt == pytest.approx(1.0 - COST)


class TestGapThroughStop:
    """D.13g: entry opening beyond the stop is a live SCRATCH (~0),
    never a ~+1R win measured in gap-distance units."""

    def test_long_gap_below_stop_is_scratch(self) -> None:
        o, h, lo, c = _flat_path()
        o[0] = 90.0  # long entry opens far below sl=99 -> stopped at once
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48,
                               1.0, risk_ref=1.0)
        assert j == 0
        # scratch = round-trip costs only, in INTENDED risk units
        assert r_opt == pytest.approx(-(2 * 0.001 + 0.0005) * 90.0)
        assert r_pess <= r_opt
        # the old bug booked this as ~+1R
        assert r_opt < 0

    def test_short_gap_above_stop_is_scratch(self) -> None:
        o, h, lo, c = _flat_path()
        o[0] = 110.0  # short entry opens far above sl=101
        r_opt, r_pess, j = sim(o, h, lo, c, 0, "short", 101.0, 99.0, 48,
                               1.0, risk_ref=1.0)
        assert j == 0
        assert r_opt == pytest.approx(-(2 * 0.001 + 0.0005) * 110.0)
        assert r_pess <= r_opt

    def test_no_risk_ref_uses_gap_distance(self) -> None:
        o, h, lo, c = _flat_path()
        o[0] = 90.0  # |fill - sl| = 9 = the R unit
        r_opt, _r, j = sim(o, h, lo, c, 0, "long", 99.0, 101.0, 48, 1.0)
        assert j == 0
        assert r_opt == pytest.approx(-(2 * 0.001 + 0.0005) * 90.0 / 9.0)
