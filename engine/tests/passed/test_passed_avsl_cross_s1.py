# -*- coding: utf-8 -*-
"""Unit tests for the PASSED module engine/passed/avsl_cross_s1.py.

Pure-function tests only (no parquet data).  The frozen-numbers
regression contract is checked by running the module itself:
  uv run python -m engine.passed.avsl_cross_s1
which must reproduce the STATUS 2026-09-22 verdict numbers.
"""

import numpy as np
import pytest

from engine.passed.avsl_cross_s1 import (
    BOOT_BLOCK,
    SIZE_MAX,
    SIZE_MIN,
    VOL_TARGET,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    s1_sizes,
    sized_accrual_stream,
)


def test_s1_size_bounds_and_monotonicity() -> None:
    rv = np.geomspace(0.01, 2.0, 50)
    sizes = VOL_TARGET / rv
    assert np.all(sizes >= 0)  # sanity on construction
    clipped = np.clip(sizes, SIZE_MIN, SIZE_MAX)
    assert np.all(np.diff(clipped) <= 0)  # higher vol -> smaller size


def test_s1_sizes_stays_within_clip() -> None:
    cp = 100 * np.cumprod(1 + 1e-9 * np.ones(300))
    sizes = s1_sizes(cp)
    assert np.nanmax(sizes) <= SIZE_MAX
    assert np.nanmin(sizes) >= SIZE_MIN


def test_s1_sizes_prefers_low_vol() -> None:
    rng = np.random.default_rng(0)
    calm = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, 300)))
    wild = 100 * np.exp(np.cumsum(rng.normal(0, 0.05, 300)))
    s_calm = s1_sizes(calm)[-1]
    s_wild = s1_sizes(wild)[-1]
    assert s_calm > s_wild
    assert s_wild <= SIZE_MAX and s_calm >= SIZE_MIN


def test_sized_accrual_stream_hand_check() -> None:
    trade = {"e0": 3, "e1": 7, "net": 2.0}
    n_g = 10
    ones = np.ones(n_g)
    stream = sized_accrual_stream([trade], ones, n_g)
    assert stream.sum() == pytest.approx(2.0)
    assert stream[3:8].tolist() == [pytest.approx(0.4)] * 5
    assert stream[:3].sum() == 0 and stream[8:].sum() == 0
    half = np.full(n_g, 0.5)
    stream = sized_accrual_stream([trade], half, n_g)
    assert stream.sum() == pytest.approx(1.0)


def test_portfolio_dd_known_path() -> None:
    up = np.array([1.0] * 100)        # R units; account = 1% x R
    down = np.array([-2.0] * 30)      # 2R loss bars -> (1-2%)^30
    assert portfolio_dd(up) == pytest.approx(0.0)
    assert portfolio_dd(down) > 0.4


def test_nw_sharpe_iid_matches_formula() -> None:
    rng = np.random.default_rng(1)
    v = rng.normal(0.0005, 0.01, 5000)
    sh = nw_sharpe(v, lags=10, ann=252)
    naive = v.mean() / v.std() * np.sqrt(252)
    assert sh == pytest.approx(naive, rel=0.2)


def test_bootstrap_ci_strong_mean_excludes_zero() -> None:
    rng = np.random.default_rng(2)
    v = rng.normal(0.05, 0.01, 3000)
    lo, hi = block_bootstrap_ci(v, b=200, block=BOOT_BLOCK)
    assert 0 < lo < np.mean(v) < hi


def test_bootstrap_ci_zero_mean_includes_zero() -> None:
    rng = np.random.default_rng(3)
    v = rng.normal(0.0, 0.01, 3000)
    lo, hi = block_bootstrap_ci(v, b=200, block=BOOT_BLOCK)
    assert lo <= 0 <= hi
