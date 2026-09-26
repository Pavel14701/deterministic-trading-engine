# -*- coding: utf-8 -*-
"""Configuration for order block detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal


@dataclass
class OrderBlockConfig:
    """All tuning parameters of the order block pipeline.

    Online / repaint-free section
    -----------------------------
    ``use_online_extremes`` switches the pipeline to the incremental
    (online) ZigZag: only pivots that are *confirmed* (cannot change
    any more) are used, and each candidate block must additionally
    satisfy the look-ahead guards

    - the pivot was confirmed *before* the breakout bar
      (``confirm_idx < break_idx``), i.e. the block was tradable live;
    - the distance from the pivot to the next extreme exceeds
      ``min_extreme_gap`` bars;
    - when ``require_complete_window`` is set, the whole retest
      confirmation window must fit inside the available history
      (``end_idx < n``).
    """

    # ZigZag (offline, scipy-style)
    zigzag_prominence_peak: float = 0.01
    zigzag_prominence_valley: float = 0.01
    zigzag_distance: int = 5
    zigzag_width: float | None = None
    zigzag_wlen: int | None = None
    zigzag_rel_height: float = 0.5
    zigzag_plateau_size: int | None = None

    # Online ZigZag (repaint-free).  Default ON: the offline scipy
    # ZigZag repaints pivots with hindsight (look-ahead leak); opt out
    # explicitly (use_online_extremes=False) only for legacy comparisons.
    use_online_extremes: bool = True
    online_reversal: float | None = None
    online_reversal_pct: float | None = None
    #: Reversal threshold as a multiple of the median ATR; wins over
    #: ``online_reversal``/``online_reversal_pct`` when set.  The median
    #: is taken over the FIRST ``reversal_warmup_bars`` bars only, so
    #: the threshold is causal: it never reads bars after the warmup
    #: window and is reproducible live (estimate once at stream start).
    reversal_atr_multiple: float | None = None
    #: Leading window (bars) for the causal ATR-median calibration of
    #: the online ZigZag reversal threshold.
    reversal_warmup_bars: int = 500
    min_extreme_gap: int = 0
    require_complete_window: bool = False

    # Breakout & lookback
    lookback_min: int = 5
    lookback_max: int = 50
    #: DEPRECATED, IGNORED (units bug, fixed 2026-09-22): the "dynamic"
    #: lookback multiplied a PRICE-valued median ATR by a multiplier and
    #: used the result as a BAR count -- for any asset priced above
    #: roughly ``lookback_max / multiplier`` the value always clamped to
    #: ``lookback_max``.  The breakout scan now always covers the window
    #: ``[lookback_min, lookback_max)`` bars after the pivot; the first
    #: valid breakout in that window wins.
    use_dynamic_lookback: bool = True
    lookback_atr_multiplier: float = 2.0
    #: DEPRECATED, IGNORED (semantics bug, fixed 2026-09-22): the flag
    #: never produced multiple signals per zone -- both branches took
    #: the first valid breakout and stopped; ``False`` additionally
    #: restricted the check to the single bar ``idx + lookback``.
    multiple_breakouts: bool = False
    breakout_volume_threshold: float = 1.0
    breakout_impulse_multiplier: float = 0.0

    # Trend filter (ADX)
    use_adx_filter: bool = False
    adx_period: int = 14
    adx_threshold: float = 25.0

    # Market structure filter (HH/HL/LH/LL)
    use_market_structure_filter: bool = False
    structure_lookback: int = 10
    min_structure_extremes: int = 3

    # Freshness filter
    max_extreme_age: int = 0

    # Fair Value Gap (FVG) filters
    require_fvg: bool = False
    fvg_tolerance: float = 0.0
    fvg_volume_multiplier: float = 0.0
    fvg_volume_mode: Literal["any", "center", "first", "last"] = "any"
    fvg_bonus_multiplier: float = 1.0

    # Breaker block filter
    check_breaker: bool = False
    breaker_lookback: int = 50
    breaker_bonus_multiplier: float = 1.5
    breaker_require_displacement: bool = False
    breaker_check_mitigated: bool = False

    # Orderflow shift filter (causal: past window only; requires the
    # online ZigZag so pivots can be confirm-guarded)
    check_orderflow_shift: bool = False
    shift_require_extremes: bool = True

    # Zone entry mode
    zone_entry_mode: Literal["wick", "close", "any"] = "wick"

    # Mitigation / closure filter
    require_closure_outside: bool = False

    # Zone freshness: reject a retest if between the breakout and the
    # retest bar the zone was re-pierced beyond its far edge (with the
    # same ``max_zone_penetration`` allowance as the retest bar itself).
    # A re-broken zone is no longer a zone -- classic SMC freshness.
    require_zone_intact: bool = True

    # Displacement (strong reaction) filter
    displacement_multiplier: float = 0.0

    # Additional confirmation (RSI, MACD)
    use_rsi_confirmation: bool = False
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    use_macd_confirmation: bool = False
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Retest & reaction
    confirmation_window: int = 10
    min_reaction_size: float = 0.002
    max_zone_penetration: float = 0.5

    # Zone sizing
    atr_period: int = 14
    #: Zone basis: the source pivot bar's range ``[low, high]`` (classic
    #: order block), its body ``[min(open, close), max(open, close)]``,
    #: or the legacy volatility band ``close +/- m * ATR``.
    zone_source: Literal["range", "body", "close_band"] = "range"
    #: Extension of the zone beyond the source bar, in ATR multiples
    #: (ignored width for ``close_band``, where it is the half-width).
    zone_atr_multiplier: float = 0.0

    # Volume & liquidity
    volume_window: int = 20
    liquidity_window: int = 10
    #: Relative tolerance: the pivot extreme must lie within this
    #: FRACTION OF PRICE from the rolling window extreme
    #: (0.001 = 0.1%).  Was an absolute price delta before the
    #: 2026-09-22 fix, which made it a no-op for high-priced assets.
    liquidity_tolerance: float = 0.001

    # Strength calculation options
    strength_log_volume: bool = False
    strength_atr_normalize: bool = False
    strength_age_penalty: bool = False
    strength_age_halflife: int = 20
    strength_max_multiplier: float = 10.0
    strength_reaction_cap: float = 3.0  # maximum allowed reaction factor

    # Clustering
    cluster_blocks: bool = False
    cluster_price_tolerance: float = 0.001
    max_cluster_time_gap: timedelta | None = timedelta(days=30)

    # Historical depth
    max_history: int | None = None

    # General
    use_talib: bool = True

    def __post_init__(self) -> None:
        """Validate cross-field invariants."""
        if self.strength_reaction_cap <= 0:
            raise ValueError(
                f"strength_reaction_cap must be positive; \
                    got {self.strength_reaction_cap}"
            )
        if self.strength_reaction_cap > self.strength_max_multiplier:
            raise ValueError(
                "strength_reaction_cap must not exceed "
                "strength_max_multiplier; "
                f"got strength_reaction_cap={self.strength_reaction_cap}, "
                f"strength_max_multiplier={self.strength_max_multiplier}"
            )
        if self.min_extreme_gap < 0:
            raise ValueError(
                f"min_extreme_gap must be >= 0; got {self.min_extreme_gap}"
            )
        if self.online_reversal is not None and self.online_reversal <= 0:
            raise ValueError(
                f"online_reversal must be positive; got {self.online_reversal}"
            )
        if self.online_reversal_pct is not None and not (
            0 < self.online_reversal_pct < 1
        ):
            raise ValueError(
                "online_reversal_pct must be in (0, 1); "
                f"got {self.online_reversal_pct}"
            )
        if self.reversal_atr_multiple is not None and (
            self.reversal_atr_multiple <= 0
        ):
            raise ValueError(
                "reversal_atr_multiple must be positive; "
                f"got {self.reversal_atr_multiple}"
            )
        if self.reversal_warmup_bars < 1:
            raise ValueError(
                "reversal_warmup_bars must be >= 1; "
                f"got {self.reversal_warmup_bars}"
            )
        if self.lookback_min < 1:
            raise ValueError(
                f"lookback_min must be >= 1; got {self.lookback_min}"
            )
        if self.lookback_max < self.lookback_min:
            raise ValueError(
                "lookback_max must be >= lookback_min; "
                f"got lookback_max={self.lookback_max}, "
                f"lookback_min={self.lookback_min}"
            )
        if self.zone_source not in ("range", "body", "close_band"):
            raise ValueError(
                "zone_source must be 'range', 'body' or 'close_band'; "
                f"got {self.zone_source!r}"
            )
        if self.zone_atr_multiplier < 0:
            raise ValueError(
                "zone_atr_multiplier must be >= 0; "
                f"got {self.zone_atr_multiplier}"
            )

    @property
    def effective_online_reversal(self) -> float:
        """Reversal threshold used by the online ZigZag."""
        if self.online_reversal is not None:
            return self.online_reversal
        return min(self.zigzag_prominence_peak, self.zigzag_prominence_valley)
