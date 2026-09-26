# -*- coding: utf-8 -*-
"""Unit tests: Black-Scholes greeks against textbook values.

Reference (S=K=100, T=1y, sigma=20%, r=0):
  call price 7.9656, delta 0.53983, gamma 0.01985,
  vega 0.39695 per vol point, theta -0.01088 per day.
"""

import math

import pytest

from experiments.options._pricing import bs, bs_greeks


def test_price_matches_textbook() -> None:
    assert bs(100, 100, 1.0, 20.0, True) == pytest.approx(7.9656, abs=1e-3)
    assert bs(100, 100, 1.0, 20.0, False) == pytest.approx(7.9656, abs=1e-3)


def test_greeks_atm_call_textbook() -> None:
    g = bs_greeks(100, 100, 1.0, 20.0, True)
    assert g["delta"] == pytest.approx(0.53983, abs=1e-4)
    assert g["gamma"] == pytest.approx(0.01985, abs=1e-4)
    assert g["vega"] == pytest.approx(0.39695, abs=1e-4)
    assert g["theta"] == pytest.approx(-0.01088, abs=1e-4)


def test_put_delta_negative_parity() -> None:
    gc = bs_greeks(100, 100, 0.5, 45.0, True)
    gp = bs_greeks(100, 100, 0.5, 45.0, False)
    assert gp["delta"] < 0
    # r=0: put delta = call delta - 1; gammas/vegas equal
    assert gp["delta"] == pytest.approx(gc["delta"] - 1.0, abs=1e-10)
    assert gp["gamma"] == pytest.approx(gc["gamma"], abs=1e-12)
    assert gp["vega"] == pytest.approx(gc["vega"], abs=1e-12)
    # put-call parity on prices
    c = bs(100, 100, 0.5, 45.0, True)
    p = bs(100, 100, 0.5, 45.0, False)
    assert c - p == pytest.approx(0.0, abs=1e-9)


def test_theta_negative_and_expiry_edge() -> None:
    g = bs_greeks(100, 90, 0.25, 30.0, False)
    assert g["theta"] < 0
    deep = bs_greeks(100, 50, 0.25, 30.0, True)
    assert deep["delta"] == pytest.approx(1.0, abs=1e-5)
    assert deep["gamma"] < 1e-4
    expired = bs_greeks(100, 90, 0.0, 30.0, True)
    assert expired["delta"] == 1.0 and expired["gamma"] == 0.0


def test_gamma_peaks_near_atm() -> None:
    g_itm = bs_greeks(100, 70, 1.0, 20.0, True)["gamma"]
    g_atm = bs_greeks(100, 100, 1.0, 20.0, True)["gamma"]
    assert g_atm > g_itm
