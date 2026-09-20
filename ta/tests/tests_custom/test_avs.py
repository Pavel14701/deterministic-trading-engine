"""Unit tests for the AVSL/AVS base indicator (Pine donor parity)."""

import numpy as np
import pytest

from ta.src.custom.avs_base import (
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)


class TestPriceVRolling:
    """Synthetic-data tests for the rolling PriceFun term."""

    def test_constant_denominators_rolling_mean(self):
        # price=[1..5], vpr=1, vpc_c=1, len_v=3 -> plain rolling mean /L/100,
        # warm-up: clamped window, denominator stays L.
        price = np.array([1.0, 2, 3, 4, 5])
        vpr = np.ones(5)
        vpc_c = np.ones(5)
        len_v = np.array([3, 3, 3, 3, 3], dtype=np.int32)
        out = _price_v_rolling(price, vpr, len_v, vpc_c)
        assert out[0] == pytest.approx(1 / 3 / 100)
        assert out[1] == pytest.approx((1 + 2) / 3 / 100)
        assert out[2] == pytest.approx((1 + 2 + 3) / 3 / 100)
        assert out[3] == pytest.approx((2 + 3 + 4) / 3 / 100)
        assert out[4] == pytest.approx((3 + 4 + 5) / 3 / 100)

    def test_vpcc_per_window_bar(self):
        # Pine parity: each window bar is divided by ITS OWN bar's VPCc.
        # vpc_c=[2,2,2,4,4], vpr=1, len_v=5, price=[10..50]:
        # out[4] = (10/2 + 20/2 + 30/2 + 40/4 + 50/4) / 5 / 100.
        # With the pre-fix code (current-bar vpc_c[i]=4 for all j) this
        # would be (10+20+30+40+50)/4/5/100 instead.
        price = np.array([10.0, 20, 30, 40, 50])
        vpr = np.ones(5)
        vpc_c = np.array([2.0, 2.0, 2.0, 4.0, 4.0])
        len_v = np.array([5, 5, 5, 5, 5], dtype=np.int32)
        out = _price_v_rolling(price, vpr, len_v, vpc_c)
        expected = (10 / 2 + 20 / 2 + 30 / 2 + 40 / 4 + 50 / 4) / 5 / 100
        assert out[4] == pytest.approx(expected)
        assert out[4] != pytest.approx((10 + 20 + 30 + 40 + 50) / 4 / 5 / 100)

    def test_zero_denominator_ignored(self):
        price = np.array([10.0, 20, 30])
        vpr = np.ones(3)
        vpc_c = np.array([1.0, 0.0, 1.0])
        len_v = np.array([3, 3, 3], dtype=np.int32)
        out = _price_v_rolling(price, vpr, len_v, vpc_c)
        assert out[2] == pytest.approx((10 + 30) / 3 / 100)

    def test_zero_len_returns_price(self):
        price = np.array([7.0, 9.0])
        out = _price_v_rolling(
            price, np.ones(2), np.array([0, 0], dtype=np.int32), np.ones(2)
        )
        assert np.array_equal(out, price)


class TestComputeLenV:
    """Half-up rounding must match Pine's round(), not Python's banker's."""

    def test_half_up_rounding(self):
        # abs(0.5 - 3) = 2.5 -> Pine round = 3, banker's round = 2.
        vpc = np.array([-1.0])
        vpci = np.array([0.5])
        assert _compute_len_v(vpc, vpci)[0] == 3

    def test_vpc_negative_branch(self):
        vpc = np.array([-1.0])
        vpci = np.array([-0.2])  # abs(-0.2-3) = 3.2 -> 3
        assert _compute_len_v(vpc, vpci)[0] == 3

    def test_vpc_positive_branch(self):
        vpc = np.array([1.0])
        vpci = np.array([0.7])  # 0.7 + 3 = 3.7 -> 4
        assert _compute_len_v(vpc, vpci)[0] == 4

    def test_nan_vpci_returns_one(self):
        vpc = np.array([1.0])
        vpci = np.array([np.nan])
        assert _compute_len_v(vpc, vpci)[0] == 1


class TestComputeVpcc:
    def test_clamp_matches_pine(self):
        vpc = np.array([-0.5, -1.5, 0.5, 2.0])
        out = _compute_vpcc(vpc)
        assert np.allclose(out, np.array([-1.0, -1.5, 1.0, 2.0]))
