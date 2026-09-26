# -*- coding: utf-8 -*-
"""Promotion prereg P3: exit-rule regression tests for the
reverse-cross walker (synthetic arrays, no data dependency)."""
from __future__ import annotations

import inspect

import numpy as np
import pytest

from engine.passed import avsl_trailing_s1 as mod

TAKER_FEE = mod.TAKER_FEE if hasattr(mod, "TAKER_FEE") else 0.0005


def _env_from(cp, line):
    """Build a walker env from close + AVSL line paths; high/low
    default to close +- 0.5 (no intrabar touches) unless overridden
    in the test."""
    cp = np.asarray(cp, dtype=float)
    line = np.asarray(line, dtype=float)
    n = len(cp)
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = np.arange(n, dtype=np.int64) * 12 + 1000  # arbitrary buckets
    return {
        "hp": cp + 0.5, "lp": cp - 0.5, "cp": cp,
        "line": line, "atr": np.full(n, 1.0),
        "up": up, "dn": dn, "cross_idx": cross_idx,
        "b": b, "g0": int(b[0]), "n_bars": n,
    }


def _set_hl(env, k, high=None, low=None):
    if high is not None:
        env["hp"][k] = high
    if low is not None:
        env["lp"][k] = low


# ---- stop semantics --------------------------------------------------------

def test_stop_wins_intrabar_long():
    # entry long at t=5 (cp=100, line=98 -> risk 2, stop 98);
    # opposite cross at k=8 BUT low pierces stop at k=6: stop wins.
    cp = [95, 96, 97, 98, 99, 100, 97, 96, 101, 102, 103]
    line = [99] * 6 + [96] * 5          # cross up at 5, cross dn at 8
    env = _env_from(cp, line)
    _set_hl(env, 6, low=97.9)           # pierces stop 98
    tr = mod.trade_revcross(env, 5, True)
    assert tr is not None
    assert tr["e1"] == 6
    assert tr["net"] == pytest.approx(-1.0 - 2 * 0.0005 * 100 / 2)


def test_stop_wins_intrabar_short():
    # entry short at t=5 (cp=100, line=102 -> risk 2, stop 102);
    # high pierces stop at k=7 despite later reversal.
    cp = [105, 104, 103, 102, 101, 100, 101, 104, 99, 98, 97]
    line = [101] * 6 + [104] * 5        # cross dn at 5, cross up at 8
    env = _env_from(cp, line)
    _set_hl(env, 7, high=102.1)
    tr = mod.trade_revcross(env, 5, False)
    assert tr["e1"] == 7
    assert tr["net"] == pytest.approx(-1.0 - 2 * 0.0005 * 100 / 2)


# ---- reverse-cross semantics ----------------------------------------------

def test_exit_at_opposite_cross_close_long():
    # entry long at t=5 (up cross: 98<99, 100>96); atr=3 -> risk 6,
    # stop 94.  Opposite dn cross at k=8 (95.5<96); low 95.0 stays
    # above stop, so exit is AT THE CLOSE of bar 8.
    cp = [90, 91, 92, 93, 98, 100, 103, 105, 95.5, 95, 94]
    line = [99] * 5 + [96] * 6
    env = _env_from(cp, line)
    env["atr"][:] = 3.0
    assert list(env["cross_idx"]) == [5, 8]
    tr = mod.trade_revcross(env, 5, True)
    assert tr is not None and tr["e1"] == 8
    exp = (95.5 - 100) / 6 - 0.001 * 100 / 6
    assert tr["net"] == pytest.approx(exp)


def test_exit_at_opposite_cross_close_short():
    # entry short at t=5 (dn cross); atr=3 -> risk 6, stop 106.
    # Opposite up cross at k=8 (105.4>104); high 105.9 stays below
    # stop, so exit is AT THE CLOSE of bar 8.
    cp = [110, 109, 108, 107, 102, 100, 102, 103, 105.4, 106, 107]
    line = [101] * 5 + [104] * 6
    env = _env_from(cp, line)
    env["atr"][:] = 3.0
    assert list(env["cross_idx"]) == [5, 8]
    tr = mod.trade_revcross(env, 5, False)
    assert tr is not None and tr["e1"] == 8
    exp = -(105.4 - 100) / 6 - 0.001 * 100 / 6
    assert tr["net"] == pytest.approx(exp)


# ---- horizon clamp + mark-to-market ----------------------------------------

def test_horizon_clamp_mark_to_market():
    # up cross at t=6 only; price never crosses back (line=100,
    # cp>=100) -> no opposite cross exists, so the trade runs to
    # the FINAL data bar (evidence-trail walker semantics).
    n = mod.HORIZON + 20
    cp = np.r_[np.full(5, 99.0), [98.0, 100.5],
               np.linspace(100, 150, n - 7)]
    line = np.r_[np.full(6, 99.0), np.full(n - 6, 100.0)]
    env = _env_from(cp, line)
    assert env["cross_idx"].size == 1 and env["cross_idx"][0] == 6
    tr = mod.trade_revcross(env, 6, True)
    assert tr is not None
    assert tr["e1"] == n - 1
    exp = (cp[n - 1] - 100.5) / 2 - 0.001 * 100.5 / 2
    assert tr["net"] == pytest.approx(exp)


def test_horizon_cap_when_cross_exists():
    # opposite cross exists but LATER than t + HORIZON -> the
    # horizon caps the exit: e1 == t + HORIZON.
    n = mod.HORIZON + 100
    cp = np.r_[np.full(5, 99.0), [98.0, 100.5],
               np.full(n - 8, 100.5), [95.0]]
    line = np.r_[np.full(6, 99.0), np.full(n - 6, 100.0)]
    env = _env_from(cp, line)
    # up cross at 6; dn cross only at the LAST bar (95 < 100)
    tr = mod.trade_revcross(env, 6, True)
    assert tr is not None
    assert tr["e1"] == 6 + mod.HORIZON


# ---- module hygiene (P2) -----------------------------------------------------

def test_no_experiments_imports():
    src = inspect.getsource(mod)
    assert "from experiments" not in src
    assert "import experiments" not in src


def test_frozen_constants_unchanged():
    assert mod.HORIZON == 500
    assert mod.K_STOP == 2.0
    assert mod.WARMUP == 400
    assert mod.SPLIT_FRAC == pytest.approx(2 / 3)
    assert mod.FROZEN["n_trades"] == 2941
