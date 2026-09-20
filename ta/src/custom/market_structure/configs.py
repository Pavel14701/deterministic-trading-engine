# -*- coding: utf-8 -*-
"""Ready-made per-timeframe configurations for order block detection.

Tuning rationale
----------------
- Zone basis is the **source pivot bar** (``zone_source="range"``),
  extended by a small ``zone_atr_multiplier`` (0.2 ATR) so the zone is
  not a single-bar sliver.
- The ZigZag reversal is **ATR-calibrated**
  (``reversal_atr_multiple=2.5``): the reversal/ATR ratio stays
  constant across timeframes instead of decaying with bar size.
- ADX trend filters and RSI "confirmation" are disabled everywhere:
  ADX > threshold keeps only strong-trend bars where zones break
  instead of retest, and the RSI gate demanded overbought/oversold at
  the retest bar - exactly the repeated-high case, not a zone retest.
- ``confirmation_window`` scales with the observed retest-delay
  distribution (retests typically arrive several bars after the
  breakout), and low-timeframe clustering is off (it blurred distinct
  zones into one wide band).
All presets use the repaint-free online ZigZag.
"""

from __future__ import annotations

from .config import OrderBlockConfig


#: Canonical timeframe -> preset mapping keys (aliases are resolved by
#: :func:`get_order_block_config`).
TIMEFRAME_CONFIGS: dict[str, OrderBlockConfig] = {
    # --- scalping: noise dominates, keep it fast and tight -------------
    "1m": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        zigzag_distance=3,
        min_extreme_gap=3,
        lookback_min=3,
        lookback_max=20,
        confirmation_window=8,
        volume_window=30,
        cluster_blocks=False,
        max_cluster_time_gap=None,
        zone_atr_multiplier=0.2,
    ),
    "5m": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        multiple_breakouts=True,
        zigzag_distance=4,
        min_extreme_gap=4,
        lookback_min=5,
        lookback_max=30,
        confirmation_window=36,
        volume_window=24,
        cluster_blocks=False,
        zone_atr_multiplier=0.2,
    ),
    # --- intraday: structural zones, no trend/RSI gates ----------------
    "15m": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        multiple_breakouts=True,
        zigzag_distance=5,
        min_extreme_gap=5,
        lookback_min=5,
        lookback_max=30,
        confirmation_window=36,
        volume_window=20,
        cluster_blocks=False,
        zone_atr_multiplier=0.2,
    ),
    "1h": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        zigzag_distance=6,
        min_extreme_gap=6,
        lookback_min=5,
        lookback_max=30,
        confirmation_window=15,
        volume_window=20,
        cluster_blocks=False,
        strength_age_penalty=True,
        zone_atr_multiplier=0.2,
    ),
    # --- swing: favour freshness and structure --------------------------
    "4h": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        zigzag_distance=8,
        min_extreme_gap=8,
        use_market_structure_filter=True,
        structure_lookback=8,
        strength_age_penalty=True,
        require_complete_window=True,
        zone_atr_multiplier=0.2,
    ),
    "1d": OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        zigzag_distance=10,
        min_extreme_gap=10,
        use_market_structure_filter=True,
        max_extreme_age=30,
        strength_age_penalty=True,
        strength_age_halflife=40,
        require_complete_window=True,
        zone_atr_multiplier=0.2,
    ),
}

# Accepted aliases for each canonical key
_ALIASES: dict[str, str] = {}
for _key in TIMEFRAME_CONFIGS:
    _ALIASES[_key] = _key
    _ALIASES[_key.upper()] = _key
    _ALIASES[_key + "s"] = _key
for _alt, _key in {
    "m1": "1m",
    "m5": "5m",
    "m15": "15m",
    "h1": "1h",
    "h4": "4h",
    "d1": "1d",
    "1min": "1m",
    "5min": "5m",
    "15min": "15m",
    "60min": "1h",
    "60m": "1h",
    "240m": "4h",
    "1day": "1d",
    "D": "1d",
    "1D": "1d",
    "4H": "4h",
    "1H": "1h",
    "15M": "15m",
    "5M": "5m",
    "1M": "1m",
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "H1": "1h",
    "H4": "4h",
}.items():
    _ALIASES[_alt] = _key


def get_order_block_config(timeframe: str) -> OrderBlockConfig:
    """Return a fresh preset config for ``timeframe``.

    Raises
    ------
    ValueError
        If the timeframe is not recognised.

    """
    key = _ALIASES.get(timeframe)
    if key is None:
        supported = ", ".join(sorted(TIMEFRAME_CONFIGS))
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; supported: {supported}"
        )
    return OrderBlockConfig(**vars(TIMEFRAME_CONFIGS[key]))


__all__ = [
    "TIMEFRAME_CONFIGS",
    "get_order_block_config",
]
