"""Sanity tests for the frozen z-score signal rules (no gate logic)."""

from __future__ import annotations

import numpy as np

from experiments.zscore.signals import (
    hyb1_signals,
    mom1_signals,
    mr1_signals,
    xsec1_weights,
)


def test_mr1_enters_long_on_extreme_low_z() -> None:
    z = np.array([np.nan, np.nan, 0.0, -2.5, -1.0, 0.0, 2.5, 0.0])
    pos = mr1_signals(z, 2.0, 0.0, True)
    # NaN window: flat; -2.5 -> long; z back to 0 -> exit; +2.5 ->
    # short; z back to exactly 0 -> exit (exit_z=0 inclusive).
    assert list(pos) == [0, 0, 0, 1, 1, 0, -1, 0]


def test_mr1_no_entry_inside_band() -> None:
    rng = np.random.default_rng(7)
    z = rng.uniform(-1.9, 1.9, size=500)
    assert np.all(mr1_signals(z, 2.0, 0.0, True) == 0)


def test_mom1_cross_enters_and_exits() -> None:
    z = np.array([0.0, 1.6, 1.7, 1.4, 0.5, -0.1, -1.6, -1.7])
    pos = mom1_signals(z, 1.5, 0.0)
    # cross up at i=1 -> long; below 0 at i=5 -> exit; cross down at
    # i=6 -> short.
    assert list(pos) == [0, 1, 1, 1, 1, 0, -1, -1]


def test_hyb1_regime_switch() -> None:
    n = 8
    z = np.zeros(n)
    z[1], z[2] = -2.5, -0.2          # MR entry then MR exit
    adx = np.full(n, 15.0)           # range regime
    pos = hyb1_signals(z, adx, 20.0, 25.0, 2.0)
    assert list(pos) == [0, 1, 0, 0, 0, 0, 0, 0]  # MR exit at |z|<=0.5
    # trend regime: z > 1 -> long even without MR trigger
    z2 = np.zeros(n)
    z2[2] = 1.5
    adx2 = np.full(n, 30.0)
    pos2 = hyb1_signals(z2, adx2, 20.0, 25.0, 2.0)
    assert pos2[2] == 1
    # dead zone [20, 25]: holds the current position
    z3 = np.zeros(n)
    adx3 = np.full(n, 22.0)
    pos3 = hyb1_signals(z3, adx3, 20.0, 25.0, 2.0)
    assert np.all(pos3 == 0)


def test_xsec1_signs_fractions_and_invalid_handling() -> None:
    z = np.array([
        [np.nan] * 12,
        [3.0, 2.0, 1.0, 0.0, -1.0, -2.0, -3.0, -4.0, 0.5, -0.5,
         1.5, np.nan],
    ])
    w = xsec1_weights(z, 0.2, 0.2, 1, 10)
    row = w[1]
    assert row[7] > 0                # lowest z -> long (oversold)
    assert row[0] < 0                # highest z -> short (overbought)
    assert np.isnan(row[11]) or row[11] == 0.0   # invalid -> nothing
    longs = row[row > 0]
    shorts = row[row < 0]
    assert len(longs) == 2 and len(shorts) == 2
    assert np.isclose(longs.sum(), 1.0) and np.isclose(shorts.sum(), -1.0)


def test_xsec1_too_few_assets_goes_flat() -> None:
    z = np.array([np.arange(8.0), np.arange(8.0) + 0.5])
    w = xsec1_weights(z, 0.2, 0.2, 1, 10)
    assert np.all(w[1] == 0.0)


def test_signals_deterministic() -> None:
    rng = np.random.default_rng(3)
    z = rng.standard_normal(300)
    a = mr1_signals(z, 2.0, 0.0, True)
    b = mr1_signals(z, 2.0, 0.0, True)
    assert np.array_equal(a, b)
