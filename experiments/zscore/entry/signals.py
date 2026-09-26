"""Frozen signal rules for the z-score strategy track.

Pre-registered in STATUS.md 2026-09-21 (commit d25cad9) BEFORE this
file existed.  Any change to these functions = track killed.

All time-series signal functions return an int8 position array
(+1 long / -1 short / 0 flat) aligned to the input bars; positions
are EXECUTED at the next bar open by the runner (no lookahead).
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from numba import njit


@njit(cache=True)
def mr1_signals(
    z: np.ndarray,
    entry_z: float,
    exit_z: float,
    allow_short: bool,
) -> np.ndarray:
    """MR-1: classic mean reversion (frozen: entry 2.0, exit 0.0)."""
    n = z.shape[0]
    pos = np.zeros(n, dtype=np.int8)
    cur = 0
    for i in range(n):
        if not np.isfinite(z[i]):
            pos[i] = cur
            continue
        if cur == 1 and z[i] >= exit_z:
            cur = 0
        elif cur == -1 and z[i] <= -exit_z:
            cur = 0
        if z[i] <= -entry_z:
            cur = 1
        elif allow_short and z[i] >= entry_z:
            cur = -1
        pos[i] = cur
    return pos


@njit(cache=True)
def mom1_signals(
    z: np.ndarray,
    entry_z: float,
    exit_z: float,
) -> np.ndarray:
    """MOM-1: z-score momentum (frozen: entry 1.5 cross, exit 0.0)."""
    n = z.shape[0]
    pos = np.zeros(n, dtype=np.int8)
    cur = 0
    for i in range(1, n):
        if not (np.isfinite(z[i]) and np.isfinite(z[i - 1])):
            pos[i] = cur
            continue
        if cur == 1 and z[i] < exit_z:
            cur = 0
        elif cur == -1 and z[i] > -exit_z:
            cur = 0
        if cur == 0:
            if z[i - 1] <= entry_z < z[i]:
                cur = 1
            elif z[i - 1] >= -entry_z > z[i]:
                cur = -1
        pos[i] = cur
    return pos


@njit(cache=True)
def hyb1_signals(
    z: np.ndarray,
    adx: np.ndarray,
    adx_range: float,
    adx_trend: float,
    entry_z: float,
) -> np.ndarray:
    """HYB-1: MR when ADX < adx_range, momentum when ADX > adx_trend.

    Frozen: adx_range=20, adx_trend=25, entry_z=2.0, MR exit |z|<=0.5,
    momentum entry |z| crossing 1.0, momentum exit through 0, and HOLD
    the current position while ADX is in the dead zone.
    """
    n = z.shape[0]
    pos = np.zeros(n, dtype=np.int8)
    cur = 0
    for i in range(n):
        if not (np.isfinite(z[i]) and np.isfinite(adx[i])):
            pos[i] = cur
            continue
        if adx[i] < adx_range:
            if cur != 0 and -0.5 <= z[i] <= 0.5:
                cur = 0               # frozen MR exit: |z| <= 0.5
            if z[i] <= -entry_z:
                cur = 1
            elif z[i] >= entry_z:
                cur = -1
        elif adx[i] > adx_trend:
            if cur == 0:
                if z[i] > 1.0:
                    cur = 1
                elif z[i] < -1.0:
                    cur = -1
            elif cur == 1 and z[i] < 0.0:
                cur = 0
            elif cur == -1 and z[i] > 0.0:
                cur = 0
        # dead zone [20, 25]: hold current position
        pos[i] = cur
    return pos


def xsec1_weights(
    z_panel: np.ndarray,
    top_frac: float,
    bottom_frac: float,
    rebalance_every: int,
    min_assets: int,
) -> np.ndarray:
    """XSEC-1: cross-sectional MR weights (frozen 0.2/0.2, 168, 10).

    Returns float array (n_bars, n_assets); long = most OVERSOLD
    (lowest z), short = most overbought.  Rebalance on the frozen
    schedule; < min_assets valid z at a rebalance -> flat until the
    next one.  Invalid (non-finite) z never enters either basket.
    """
    n_bars, n_assets = z_panel.shape
    weights = np.zeros((n_bars, n_assets), dtype=np.float64)
    cur = np.zeros(n_assets, dtype=np.float64)
    for i in range(n_bars):
        if i % rebalance_every == 0 and i > 0:
            z_row = z_panel[i]
            valid = np.isfinite(z_row)
            n_valid = int(valid.sum())
            if n_valid < min_assets:
                cur = np.zeros(n_assets, dtype=np.float64)
            else:
                n_long = max(1, int(n_valid * bottom_frac))
                n_short = max(1, int(n_valid * top_frac))
                # invalid -> +inf: pushed to the END of the ascending
                # sort, so the first n_long picks are always valid.
                long_idx = np.argsort(
                    np.where(valid, z_row, np.inf), kind="stable"
                )[:n_long]
                # invalid -> -inf: pushed to the FRONT, so the LAST
                # n_short picks are always valid (slice from the end,
                # not from n_valid -- the array includes invalids).
                short_idx = np.argsort(
                    np.where(valid, z_row, -np.inf), kind="stable"
                )[-n_short:]
                cur = np.zeros(n_assets, dtype=np.float64)
                cur[long_idx] = 1.0 / n_long
                cur[short_idx] = -1.0 / n_short
        weights[i] = cur
    return weights
