"""Structural stop geometry: anchor levels, zone painting, TP/SL rules.

Extracted verbatim from the archived ``scripts/dsl_strategy_search.py``
(see ``legacy/MANIFEST.md``) - this is the live stop-rule engine used by
``scripts/build_stop_dataset.py`` to build the stop-geometry panels
zone geometry (see STATUS.md).

Stop rule formats handled by :func:`build_tp_sl`:
- ``atr:m``  -> volatility stop, entry -/+ m*ATR;
- ``zone:b`` -> structural stop, behind the block zone +/- b*ATR;
- ``anchor:<name>:<b>`` -> indicator anchor level +/- b*ATR beyond.
"""

from __future__ import annotations

import numpy as np
import polars as pl


PAINT_HORIZON = 2000  # bars a block stays eligible for the zone paint

# Indicator-anchored stop levels: name -> sides it is valid for.
# Support anchors (below price) stop longs, resistance anchors stop shorts;
# 'st' (supertrend) is direction-aware and valid for both (invalid
# geometries are filtered by the RR check anyway).
ANCHOR_SIDES = {
    "avsl": ("long",),      # Adaptive Volume Support Level
    "avsr": ("short",),     # Adaptive Volume Support/Resistance line
    "hilo": ("long", "short"),  # HiLo activator: long line / short line
    "st": ("long", "short"),    # supertrend trailing line
    "bb": ("long", "short"),    # Bollinger band (lower / upper)
}

BB_LENGTH = 20
BB_STD = 2.0


def compute_anchors(df: pl.DataFrame) -> dict[str, np.ndarray]:
    """Causal per-bar anchor levels for indicator-based stops.

    All series are float64 numpy arrays aligned with ``df``; warm-up
    bars are NaN and simply produce no entries.
    """
    from ta.src.custom.avsl import avsl_numpy
    from ta.src.custom.avsr import avsr_numpy
    from ta.src.overlap.hilo import hilo_ind
    from ta.src.overlap.supertrend import supertrend_ind

    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()

    anchors: dict[str, np.ndarray] = {
        "avsl": avsl_numpy(high, low, close, volume, fast=52, slow=134),
        "avsr": avsr_numpy(high, low, close, volume, fast=52, slow=134),
    }
    _hilo, hilo_long, hilo_short = hilo_ind(high, low, close)
    anchors["hilo_l"] = hilo_long
    anchors["hilo_s"] = hilo_short
    st_line = supertrend_ind(high, low, close)[0]
    anchors["st"] = st_line
    cs = df["close"]
    mean = cs.rolling_mean(BB_LENGTH)
    std = cs.rolling_std(BB_LENGTH, ddof=0)
    anchors["bb_l"] = (mean - BB_STD * std).to_numpy()
    anchors["bb_u"] = (mean + BB_STD * std).to_numpy()
    return anchors


def anchor_for_side(name: str, side: str) -> str | None:
    """Resolve an anchor family name to the concrete level key."""
    if name in ANCHOR_SIDES:
        if side not in ANCHOR_SIDES[name]:
            return None
        if name == "hilo":
            return "hilo_l" if side == "long" else "hilo_s"
        if name == "bb":
            return "bb_l" if side == "long" else "bb_u"
        return name
    return None


def paint_zone(blocks: list, n: int, side: str) -> np.ndarray:
    """First-match zone level per bar for the structural stop rule.

    Iterates blocks in list order (the generator's priority) and paints
    ``[end_idx, end_idx + PAINT_HORIZON)`` with the stop-side zone edge
    (``zone_low`` for demand/long, ``zone_high`` for supply/short).
    Earlier blocks win; later blocks only fill unpainted bars.
    """
    zone = np.full(n, np.nan)
    for ob in blocks:
        is_demand = ob.block_type.lower() == "demand"
        if side == "long" and not is_demand:
            continue
        if side == "short" and is_demand:
            continue
        level = ob.zone_low if is_demand else ob.zone_high
        lo = max(ob.end_idx, 0)
        hi = min(n, lo + PAINT_HORIZON)
        if lo >= hi:
            continue
        seg = zone[lo:hi]
        mask = np.isnan(seg)
        seg[mask] = level
        zone[lo:hi] = seg
    return zone


def build_tp_sl(
    close: np.ndarray,
    atr: np.ndarray,
    stop_rule: str,
    target_r: float,
    side: str,
    zone: np.ndarray | None,
    anchors: dict[str, np.ndarray] | None = None,
    min_risk_atr: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar TP/SL arrays for one (stop_rule, target_r) pair.

    Bars whose risk unit is below ``min_risk_atr`` ATRs are marked
    invalid (no entry): a stop closer than that cannot survive
    round-trip costs, so the trade is not part of the strategy.
    """
    sign = 1.0 if side == "long" else -1.0
    if stop_rule.startswith("zone:"):
        if zone is None:
            raise ValueError("zone stop rule requires a zone overlay")
        buffer = float(stop_rule.split(":")[1])
        sl = zone - sign * buffer * atr
    elif stop_rule.startswith("atr:"):
        m = float(stop_rule.split(":")[1])
        sl = close - sign * m * atr
    elif stop_rule.startswith("anchor:"):
        _pfx, name, buffer_s = stop_rule.split(":")
        buffer = float(buffer_s)
        key = anchor_for_side(name, side)
        level = anchors[key] if (key and anchors is not None) else None
        if level is None:
            # anchor not valid for this side -> no trades for candidate
            sl = np.full(close.shape, np.nan)
        else:
            sl = level - sign * buffer * atr
    else:  # pragma: no cover - argparse constrains values
        raise ValueError(f"unknown stop rule {stop_rule!r}")
    risk_unit = np.abs(close - sl)
    tp = close + sign * target_r * risk_unit
    invalid = ~(
        np.isfinite(sl)
        & np.isfinite(tp)
        & (risk_unit > 0)
        & (risk_unit >= min_risk_atr * atr)
    )
    tp[invalid] = np.nan
    sl[invalid] = np.nan
    return tp, sl
