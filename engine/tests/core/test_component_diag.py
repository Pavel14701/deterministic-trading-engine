# -*- coding: utf-8 -*-
"""Synthetic-data tests for the component diagnostic metrics.

Validates the frozen measurement functions BEFORE the single real run
(prereg rule: re-runs only for bug fixes).  No real data here.
"""

import numpy as np
import pytest

from experiments.avsl.component_diagnostic.v1_diag import (
    decile_monotone,
    decile_spread,
    hurst_dfa_series,
    mannwhitney_z,
    nw_tstat,
    rolling_nan_z,
    rolling_sum,
    spearman,
    tertile_ev,
)


def test_hurst_white_noise_near_half() -> None:
    rng = np.random.default_rng(7)
    ret = rng.standard_normal(600) * 0.01
    h = hurst_dfa_series(ret, 200)
    v = h[np.isfinite(h)]
    assert len(v) == 401  # bars w-1 .. n-1 (no lookahead)
    assert abs(v.mean() - 0.5) < 0.15


def test_hurst_persistent_series_high() -> None:
    rng = np.random.default_rng(7)
    e = rng.standard_normal(600)
    ret = np.empty(600)
    ret[0] = e[0]
    for i in range(1, 600):  # AR(1) rho=0.5 -> persistent increments
        ret[i] = 0.5 * ret[i - 1] + e[i]
    h = hurst_dfa_series(ret, 200)
    v = h[np.isfinite(h)]
    assert v.mean() > 0.58


def test_spearman_and_tstat() -> None:
    rng = np.random.default_rng(3)
    x = rng.standard_normal(2000)
    y = 0.3 * x + rng.standard_normal(2000)
    ic, n = spearman(x, y)
    t, n2 = nw_tstat(x, y, 3)
    assert n == n2 == 2000
    assert 0.2 < ic < 0.4
    assert t > 5  # strong signal -> large t
    ic0, _ = spearman(x, rng.standard_normal(2000))
    assert abs(ic0) < 0.1


def test_decile_spread_recovers_signal() -> None:
    rng = np.random.default_rng(11)
    c = rng.standard_normal(3000)
    y = 0.001 * c + rng.standard_normal(3000) * 0.002
    sp, lo, hi, n = decile_spread(
        c, y, np.random.default_rng(11))
    assert n == 3000
    assert sp > 0
    assert lo < sp < hi


def test_decile_monotone() -> None:
    rng = np.random.default_rng(5)
    c = rng.standard_normal(2000)
    y = c + rng.standard_normal(2000) * 0.1
    assert decile_monotone(c, y)
    # 'top-vs-rest only': flat middle, jump in the top decile -> fails
    y_top = np.where(c > np.quantile(c, 0.9), 5.0, 0.0) \
        + rng.standard_normal(2000) * 0.1
    assert not decile_monotone(c, y_top)


def test_tertile_ev() -> None:
    c = np.arange(90, dtype=np.float64)
    net = np.where(c < 30, -1.0, np.where(c < 60, 0.0, 1.0))
    evs, ns = tertile_ev(c, net)
    assert evs == [-1.0, 0.0, 1.0]
    assert ns == [30, 30, 30]


def test_mannwhitney_z() -> None:
    rng = np.random.default_rng(9)
    a = rng.standard_normal(500) + 0.5
    b = rng.standard_normal(500)
    z, n1, n2 = mannwhitney_z(a, b)
    assert n1 == n2 == 500
    assert z > 5


def test_rolling_nan_z_and_sum() -> None:
    x = np.full(400, 0.001)
    x[200] = 5.0  # spike -> large z at 200
    z = rolling_nan_z(x, 180, 60)
    assert z[200] > 5
    assert np.isnan(z[100])  # insufficient history
    s = rolling_sum(np.arange(50, dtype=np.float64), 6)
    assert s[6] == pytest.approx(sum(range(7)))
    assert np.isnan(s[4])
