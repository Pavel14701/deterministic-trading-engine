# -*- coding: utf-8 -*-
"""Breakout candidate generation (Numba-optimized)."""

from __future__ import annotations

import numpy as np

from numba import boolean, float64, int64, njit  # type: ignore[attr-defined]
from numba.typed import List

from .config import OrderBlockConfig


@njit(
    (
        float64[:],
        float64[:],
        float64[:],
        float64[:],
        float64[:],
        float64[:],
        float64[:],
        float64[:],
        boolean[:],
        boolean[:],
        float64[:],
        float64[:],
        float64[:],
        int64,
        int64,
        float64,
        float64,
        float64,
        boolean,
        float64,
    ),
    cache=True,
    fastmath=True,
)
def _generate_block_candidates_nb(
    high,
    low,
    close,
    volume,
    avg_volume,
    atr,
    local_highs,
    local_lows,
    peak_mask,
    valley_mask,
    adx,
    di_plus,
    di_minus,
    lookback_min,
    lookback_max,
    breakout_volume_threshold,
    breakout_impulse_multiplier,
    liquidity_tolerance,
    use_adx_filter,
    adx_threshold,
):
    # NaN (missing ADX) fails the `adx != adx` check below, so the
    # ADX filter automatically rejects bars without a valid ADX value
    vol_mult = breakout_volume_threshold
    imp_mult = breakout_impulse_multiplier
    n = len(high)
    block_types = List.empty_list(int64)
    idx_list = List.empty_list(int64)
    break_idx_list = List.empty_list(int64)
    strength_list = List.empty_list(float64)
    # Breakout window: [idx + lookback_min, idx + lookback_max); the
    # first valid breakout wins.  (Historically the non-windowed
    # variant checked the SINGLE bar idx + "dynamic lookback" -- a
    # units bug that pinned the delay at lookback_max bars for any
    # reasonably priced asset.)
    brk_cap = lookback_max if lookback_max > lookback_min else (
        lookback_min + 1
    )
    for idx in range(n):
        brk_start = idx + lookback_min
        brk_stop = idx + brk_cap
        if brk_stop > n:
            brk_stop = n
        if brk_start >= brk_stop:
            continue
        if peak_mask[idx]:
            # Relative liquidity proximity (fraction of price); the
            # old absolute tolerance was a no-op above ~$25 assets.
            if abs(
                local_highs[idx] - high[idx]
            ) >= liquidity_tolerance * high[idx]:
                continue
            for brk in range(brk_start, brk_stop):
                if low[brk] < low[idx]:
                    ok = True
                    if volume[brk] <= vol_mult * avg_volume[brk]:
                        ok = False
                    if ok and breakout_impulse_multiplier > 0:
                        candle_range = high[brk] - low[brk]
                        if (
                            not np.isfinite(atr[brk])
                            or candle_range < imp_mult * atr[brk]
                        ):
                            ok = False
                    if ok and use_adx_filter:
                        adx_v = adx[brk]
                        if adx_v != adx_v or adx_v < adx_threshold:
                            ok = False
                        elif di_minus[brk] <= di_plus[brk]:
                            ok = False
                    if ok:
                        move = (close[idx] - close[brk]) / max(
                            close[idx], 1e-9
                        )
                        strength = max(0.0, move)
                        block_types.append(0)  # supply
                        idx_list.append(idx)
                        break_idx_list.append(brk)
                        strength_list.append(strength)
                        break
        elif valley_mask[idx]:
            if abs(
                local_lows[idx] - low[idx]
            ) >= liquidity_tolerance * low[idx]:
                continue
            for brk in range(brk_start, brk_stop):
                if high[brk] > high[idx]:
                    ok = True
                    if volume[brk] <= vol_mult * avg_volume[brk]:
                        ok = False
                    if ok and breakout_impulse_multiplier > 0:
                        candle_range = high[brk] - low[brk]
                        if (
                            not np.isfinite(atr[brk])
                            or candle_range < imp_mult * atr[brk]
                        ):
                            ok = False
                    if ok and use_adx_filter:
                        adx_v = adx[brk]
                        if adx_v != adx_v or adx_v < adx_threshold:
                            ok = False
                        elif di_plus[brk] <= di_minus[brk]:
                            ok = False
                    if ok:
                        move = (close[brk] - close[idx]) / max(
                            close[idx], 1e-9
                        )
                        strength = max(0.0, move)
                        block_types.append(1)  # demand
                        idx_list.append(idx)
                        break_idx_list.append(brk)
                        strength_list.append(strength)
                        break
    return block_types, idx_list, break_idx_list, strength_list


def generate_block_candidates(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    dates: np.ndarray,
    peak_indices: np.ndarray,
    valley_indices: np.ndarray,
    indicators: dict[str, np.ndarray],
    cfg: OrderBlockConfig,
) -> list[dict]:
    """Build breakout candidates from confirmed pivot masks."""
    n = len(high)
    # Masks
    peak_mask = np.zeros(n, dtype=bool)
    valley_mask = np.zeros(n, dtype=bool)
    if len(peak_indices) > 0:
        peak_mask[peak_indices] = True
    if len(valley_indices) > 0:
        valley_mask[valley_indices] = True
    avg_volume = indicators["avg_volume"]
    atr = indicators["atr"]
    local_highs = indicators["local_highs"]
    local_lows = indicators["local_lows"]
    # ADX arrays (or placeholders)
    if cfg.use_adx_filter and "adx" in indicators:
        adx = indicators["adx"]
        di_plus = indicators["di_plus"]
        di_minus = indicators["di_minus"]
    else:
        adx = np.full(n, np.nan, dtype=np.float64)
        di_plus = np.full(n, np.nan, dtype=np.float64)
        di_minus = np.full(n, np.nan, dtype=np.float64)
    block_types, idx_list, break_idx_list, strength_list = (
        _generate_block_candidates_nb(
            high,
            low,
            close,
            volume,
            avg_volume,
            atr,
            local_highs,
            local_lows,
            peak_mask,
            valley_mask,
            adx,
            di_plus,
            di_minus,
            cfg.lookback_min,
            cfg.lookback_max,
            cfg.breakout_volume_threshold,
            cfg.breakout_impulse_multiplier,
            cfg.liquidity_tolerance,
            cfg.use_adx_filter,
            cfg.adx_threshold,
        )
    )
    candidates = []
    for bt, idx, brk, st in zip(
        block_types,
        idx_list,
        break_idx_list,
        strength_list,
        strict=False,
    ):
        block_type = "supply" if bt == 0 else "demand"
        candidates.append(
            {
                "block_type": block_type,
                "idx": idx,
                "break_idx": brk,
                "strength": st,
                "start_date": dates[idx],
            }
        )
    return candidates
