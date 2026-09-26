# -*- coding: utf-8 -*-
"""Эквивалентность engine/core.py (параметрики) <-> frozen-копии
в engine/passed/.  Ядро обязано давать бит-в-бит тот же результат
при дефолтах; это regression-контракт в обе стороны.
"""
from __future__ import annotations

import numpy as np
import pytest

from engine import core
from engine.passed.avsl_cross_s1 import (
    block_bootstrap_ci,
    fast_line,
    nw_sharpe,
    portfolio_dd,
    resample_4h,
    s1_sizes,
    sized_accrual_stream,
)


@pytest.fixture(scope="module")
def synth():
    rng = np.random.default_rng(7)
    n = 1500
    cp = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    lp = cp * (1.0 - np.abs(rng.normal(0, 0.005, n)))
    vol = np.exp(rng.normal(10.0, 1.0, n))
    ts = (np.arange(n, dtype=np.int64) + 100) * 3_600_000  # 1H ms
    hp = cp * (1.0 + np.abs(rng.normal(0, 0.005, n)))
    return dict(ts=ts, hp=hp, lp=lp, cp=cp, vol=vol)


def test_fast_line_bit_exact(synth):
    a = core.fast_line_p(synth["lp"], synth["cp"], synth["vol"])
    b = fast_line(synth["lp"], synth["cp"], synth["vol"])
    np.testing.assert_array_equal(a, b)


def test_fast_line_parametric_differs(synth):
    a = core.fast_line_p(synth["lp"], synth["cp"], synth["vol"],
                         fast=20, slow=100)
    b = core.fast_line_p(synth["lp"], synth["cp"], synth["vol"])
    assert not np.allclose(a, b, equal_nan=True)


def test_resample_bit_exact(synth):
    a = core.resample_bars(synth["ts"], synth["hp"], synth["lp"],
                           synth["cp"], synth["vol"])
    b = resample_4h(synth["ts"], synth["hp"], synth["lp"],
                    synth["cp"], synth["vol"])
    for i, (x, y) in enumerate(zip(a, b)):
        if i == 0:  # ts: целочисленное поле — бит-в-бит
            np.testing.assert_array_equal(x, y)
        else:
            # поларсовский group_by-sum параллелен: порядок суммирования
            # float не гарантирован -> допускаем последний бит
            np.testing.assert_allclose(x, y, rtol=1e-12, atol=0)



def test_s1_sizes_bit_exact(synth):
    a = core.s1_sizes_p(synth["cp"])
    b = s1_sizes(synth["cp"])
    np.testing.assert_array_equal(a, b)


def test_s1_sizes_parametric_differs(synth):
    a = core.s1_sizes_p(synth["cp"], vol_target=0.40)
    b = core.s1_sizes_p(synth["cp"])
    assert not np.allclose(a, b)


def test_nw_sharpe_bit_exact(synth):
    rng = np.random.default_rng(3)
    v = rng.normal(0.001, 0.01, 3000)
    assert core.nw_sharpe_p(v) == nw_sharpe(v)
    assert core.nw_sharpe_p(v, lags=50) == nw_sharpe(v, lags=50)


def test_bootstrap_bit_exact(synth):
    rng = np.random.default_rng(5)
    v = rng.normal(0.001, 0.01, 6000)
    assert core.block_bootstrap_ci_p(v) == block_bootstrap_ci(v)


def test_portfolio_dd_bit_exact(synth):
    rng = np.random.default_rng(9)
    v = rng.normal(0.0005, 0.002, 8000)
    assert core.portfolio_dd_p(v) == portfolio_dd(v)


def test_accrual_stream_bit_exact(synth):
    rng = np.random.default_rng(11)
    trades = [
        {"e0": int(e0), "e1": int(e0) + int(rng.integers(5, 60)),
         "net": float(rng.normal(0.1, 0.5))}
        for e0 in rng.integers(0, 1000, 40)
    ]
    sizes = core.s1_sizes_p(synth["cp"])
    a = core.sized_accrual_stream_p(trades, sizes, 1500)
    b = sized_accrual_stream(trades, sizes, 1500)
    np.testing.assert_array_equal(a, b)
