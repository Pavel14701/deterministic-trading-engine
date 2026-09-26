# -*- coding: utf-8 -*-
"""Tests for the market_structure package (order block detection).

Covers:
- ``identify_order_blocks`` contract: output schema, ordering, zone sanity
- anti-look-ahead property in online mode: every block's pivot was
  confirmed strictly before its breakout bar (no repaint)
- zone construction per ``zone_source`` (range / body / close_band)
- wick-entry symmetry between supply and demand zones
- causal ``check_orderflow_shift`` (offline pivots rejected, no future
  reads) and the confirm-guarded ``min_extreme_gap`` filter
- ``reversal_atr_multiple`` resolution and validation
- ``OrderBlockConfig`` validation errors
- ``get_order_block_config`` aliases / unknown timeframe
- all timeframe presets: tuned field values and end-to-end validity
"""

from datetime import datetime, timedelta
from itertools import pairwise

import numpy as np
import polars as pl
import pytest

from ta.src.custom.market_structure import (
    OnlineZigZag,
    OrderBlockConfig,
    identify_order_blocks,
    zigzag_reversal_numpy,
)
from ta.src.custom.market_structure.blocks import effective_online_reversal
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.custom.market_structure.filters import (
    check_orderflow_shift,
    check_zone_entry,
)


EXPECTED_COLUMNS = [
    "id",
    "block_type",
    "start",
    "break",
    "retest",
    "zone_low",
    "zone_high",
    "strength",
    "structure_label",
    "trend_direction",
]


def make_ohlcv(
    n: int = 300,
    seed: int = 0,
    start: float = 100.0,
    freq: str = "5m",
) -> pl.DataFrame:
    """Synthetic OHLCV frame: random-walk close with sane high/low."""
    rng = np.random.default_rng(seed)
    close = start + np.cumsum(rng.normal(0, 0.8, n))
    spread = np.abs(rng.normal(0.4, 0.15, n))
    high = close + spread
    low = close - spread
    volume = rng.gamma(2.0, 50.0, n)
    step = timedelta(minutes=int(freq.rstrip("m")))
    dates = [datetime(2024, 1, 1) + i * step for i in range(n)]
    return (
        pl.DataFrame(
            {
                "date": dates,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        ),
        high,
        low,
    )


def assert_valid_block_frame(out: pl.DataFrame) -> None:
    assert isinstance(out, pl.DataFrame)
    assert out.columns == EXPECTED_COLUMNS
    if out.is_empty():
        return
    # sorted by start, ids strictly increasing
    assert out["start"].to_list() == sorted(out["start"].to_list())
    assert out["id"].to_list() == sorted(out["id"].to_list())
    assert set(out["id"].to_list()) == set(range(out.height))
    # zone sanity and temporal ordering
    assert (out["zone_low"] <= out["zone_high"]).all()
    assert (out["start"] < out["break"]).all()
    assert (out["break"] <= out["retest"]).all()
    assert out["block_type"].is_in(["supply", "demand"]).all()
    assert (out["strength"] >= 0).all()


# -----------------------------------------------------------------------------
# Output schema / contract
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_empty_output_schema() -> None:
    """A flat series has no pivots -> empty frame with the full schema."""
    n = 120
    df = pl.DataFrame(
        {
            "date": [
                datetime(2024, 1, 1) + i * timedelta(minutes=5)
                for i in range(n)
            ],
            "high": np.full(n, 100.5),
            "low": np.full(n, 99.5),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 1000.0),
        }
    )
    out = identify_order_blocks(
        df,
        cfg=OrderBlockConfig(use_online_extremes=True),
    )
    assert out.is_empty()
    assert out.columns == EXPECTED_COLUMNS
    schema = out.schema
    assert schema["id"] == pl.Int64
    assert schema["block_type"] == pl.Utf8
    assert schema["start"] == pl.Datetime
    assert schema["break"] == pl.Datetime
    assert schema["retest"] == pl.Datetime
    assert schema["zone_low"] == pl.Float64
    assert schema["zone_high"] == pl.Float64
    assert schema["strength"] == pl.Float64
    assert schema["structure_label"] == pl.Utf8
    assert schema["trend_direction"] == pl.Utf8


@pytest.mark.custom
@pytest.mark.parametrize("mode", [False, True])
def test_online_and_offline_modes_valid(mode: bool) -> None:
    df, _, _ = make_ohlcv(300, seed=1)
    cfg = OrderBlockConfig(use_online_extremes=mode)
    out = identify_order_blocks(df, cfg=cfg)
    assert_valid_block_frame(out)


@pytest.mark.custom
def _crafted_swing() -> tuple[pl.DataFrame, np.ndarray]:
    """Decline -> valley -> slow rally -> immediate breakout -> retest.

    The rally is deliberately slow (0.35/bar): the valley pivot becomes
    confirmed by the online ZigZag exactly at the breakout bar, not
    before - the textbook repaint scenario.
    """
    close: list[float] = []
    for i in range(11):  # decline 100 -> 98
        close.append(100.0 - 0.2 * i)
    c = 98.0
    for _ in range(9):  # slow rally -> breakout
        c += 0.35
        close.append(c)
    close += [99.6, 98.9, 98.3, 98.1]  # pullback into the zone
    for i in range(6):  # reaction bounce
        close.append(98.1 + 0.4 * (i + 1))
    close_arr = np.asarray(close)
    n = len(close_arr)
    volume = np.full(n, 100.0)
    volume[15] = 800.0  # breakout surge
    volume[21] = 900.0  # retest volume
    volume[23] = 700.0
    df = pl.DataFrame(
        {
            "date": [
                datetime(2024, 1, 1) + i * timedelta(hours=1) for i in range(n)
            ],
            "high": close_arr + 0.2,
            "low": close_arr - 0.2,
            "close": close_arr,
            "volume": volume,
        }
    )
    return df, close_arr


def _swing_cfg(**kwargs) -> OrderBlockConfig:
    """Short indicator windows so nothing sits in NaN warm-up."""
    return OrderBlockConfig(
        use_dynamic_lookback=False,
        lookback_min=5,
        confirmation_window=12,
        atr_period=3,
        volume_window=5,
        **kwargs,
    )


@pytest.mark.custom
def test_offline_mode_finds_blocks_on_crafted_swing() -> None:
    """Sanity: the pipeline confirms a demand block on a clean swing."""
    df, _ = _crafted_swing()
    out = identify_order_blocks(
        df,
        cfg=_swing_cfg(use_online_extremes=False),
    )
    assert_valid_block_frame(out)
    assert out.height >= 1
    row = out.row(0, named=True)
    assert row["block_type"] == "demand"
    assert row["start"] == df["date"][10]  # the valley bar
    assert row["break"] == df["date"][15]  # first bar above its high


# -----------------------------------------------------------------------------
# Anti-look-ahead property (online mode)
# -----------------------------------------------------------------------------
@pytest.mark.custom
@pytest.mark.parametrize("seed", [0, 2, 4])
def test_online_blocks_are_repaint_free(seed: int) -> None:
    """Every online block's pivot was final before the breakout bar.

    This is the core no-repaint guarantee: the batch ZigZag reference
    must contain the pivot, and its confirmation bar must precede the
    breakout - so the block was tradable live, without hindsight.
    """
    df, high, low = make_ohlcv(350, seed=seed)
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
    )
    out = identify_order_blocks(df, cfg=cfg)
    assert_valid_block_frame(out)
    dates = df["date"].to_list()
    pos = {d: i for i, d in enumerate(dates)}
    pivots = zigzag_reversal_numpy(high, low, 2.0)
    confirm_of = {p.idx: p.confirm_idx for p in pivots}
    for row in out.iter_rows(named=True):
        pivot_idx = pos[row["start"]]
        break_idx = pos[row["break"]]
        assert pivot_idx in confirm_of
        assert confirm_of[pivot_idx] < break_idx


@pytest.mark.custom
def test_online_stricter_than_offline() -> None:
    """Repaint scenario: breakout on the very bar the pivot finalises.

    The offline ZigZag happily uses the valley (hindsight: it knows the
    rally continues).  The online machine confirms that valley exactly
    at the breakout bar, and the ``confirm_idx < break_idx`` guard must
    reject the block - nothing repaintable is ever reported.
    """
    df, _ = _crafted_swing()
    valley_date = df["date"][10]
    # offline: the valley IS used, breakout allowed
    off = identify_order_blocks(
        df,
        cfg=_swing_cfg(use_online_extremes=False),
    )
    assert off.filter(pl.col("start") == valley_date).height >= 1
    # online: the valley finalises at the breakout bar -> rejected
    on = identify_order_blocks(
        df,
        cfg=_swing_cfg(use_online_extremes=True, online_reversal=2.0),
    )
    assert on.filter(pl.col("start") == valley_date).height == 0
    # and indeed the pivot is only confirmed AT the breakout bar
    zz = OnlineZigZag(2.0)
    zz.update_series(
        df["high"].to_numpy(),
        df["low"].to_numpy(),
    )
    confirm_of = {p.idx: p.confirm_idx for p in zz.confirmed}
    assert confirm_of[10] == 15


# -----------------------------------------------------------------------------
# Zone construction (zone_source modes)
# -----------------------------------------------------------------------------
def _pivot_bounds(out: pl.DataFrame, df: pl.DataFrame) -> list[tuple[int, dict]]:
    """(pivot bar index, ohlc at the pivot) for every detected block."""
    dates = df["date"].to_list()
    pos = {d: i for i, d in enumerate(dates)}
    open_col = df["open"] if "open" in df.columns else df["close"]
    res = []
    for row in out.iter_rows(named=True):
        p = pos[row["start"]]
        res.append(
            (
                p,
                {
                    "open": open_col[p],
                    "high": df["high"][p],
                    "low": df["low"][p],
                    "close": df["close"][p],
                },
            )
        )
    return res


@pytest.mark.custom
def test_zone_source_range_matches_source_bar() -> None:
    """Default zone = the source pivot bar's [low, high] (zero extension)."""
    df, _, _ = make_ohlcv(300, seed=3)
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
        atr_period=5,
        zone_atr_multiplier=0.0,
        zone_source="range",
    )
    out = identify_order_blocks(df, cfg=cfg)
    assert out.height >= 1
    for p, ohlc in _pivot_bounds(out, df):
        row = out.filter(pl.col("start") == df["date"][p]).row(0, named=True)
        assert row["zone_low"] == pytest.approx(ohlc["low"])
        assert row["zone_high"] == pytest.approx(ohlc["high"])


@pytest.mark.custom
def test_zone_source_body_matches_source_bar_body() -> None:
    """``body`` zone = the source bar's open/close envelope."""
    df, _, _ = make_ohlcv(300, seed=3)
    rng = np.random.default_rng(7)
    df = df.with_columns(
        pl.Series(
            "open",
            df["close"].to_numpy() + rng.normal(0, 0.1, df.height),
        )
    )
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
        atr_period=5,
        zone_atr_multiplier=0.0,
        zone_source="body",
        # zero-width body zones give the freshness guard no allowance;
        # this test targets zone GEOMETRY, not freshness
        require_zone_intact=False,
    )
    out = identify_order_blocks(df, cfg=cfg)
    assert out.height >= 1
    for p, ohlc in _pivot_bounds(out, df):
        row = out.filter(pl.col("start") == df["date"][p]).row(0, named=True)
        body_lo = min(ohlc["open"], ohlc["close"])
        body_hi = max(ohlc["open"], ohlc["close"])
        assert row["zone_low"] == pytest.approx(body_lo)
        assert row["zone_high"] == pytest.approx(body_hi)


@pytest.mark.custom
def test_zone_source_close_band_backcompat() -> None:
    """``close_band`` keeps the legacy close +/- m*ATR volatility band."""
    df, _, _ = make_ohlcv(300, seed=3)
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
        atr_period=5,
        zone_atr_multiplier=0.5,
        zone_source="close_band",
    )
    out = identify_order_blocks(df, cfg=cfg)
    assert out.height >= 1
    for p, ohlc in _pivot_bounds(out, df):
        row = out.filter(pl.col("start") == df["date"][p]).row(0, named=True)
        # symmetric strictly-positive band around the pivot close
        assert row["zone_low"] < ohlc["close"] < row["zone_high"]
        upper = row["zone_high"] - ohlc["close"]
        lower = ohlc["close"] - row["zone_low"]
        assert upper == pytest.approx(lower, rel=1e-6)
        assert upper > 0


@pytest.mark.custom
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"zone_source": "candle"}, "zone_source"),
        ({"zone_atr_multiplier": -0.1}, "zone_atr_multiplier"),
        ({"reversal_atr_multiple": 0.0}, "reversal_atr_multiple"),
    ],
)
def test_config_validation_new_fields(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        OrderBlockConfig(**kwargs)


# -----------------------------------------------------------------------------
# Wick-entry symmetry (filters.check_zone_entry)
# -----------------------------------------------------------------------------
def _entry_call(
    high: float,
    low: float,
    close: float,
    zone_low: float,
    zone_high: float,
    is_supply: bool,
    mode: str = "wick",
    penetration: float = 0.5,
) -> bool:
    return check_zone_entry(
        np.array([0.0, high]),
        np.array([0.0, low]),
        np.array([0.0, close]),
        1,
        zone_low,
        zone_high,
        is_supply,
        penetration,
        mode,
    )


@pytest.mark.custom
def test_wick_entry_symmetric() -> None:
    """Supply zones are touched by high, demand zones by low."""
    # supply zone [100, 101]
    assert _entry_call(100.5, 99.0, 99.5, 100.0, 101.0, True)
    # demand mirror [100, 101]
    assert _entry_call(102.0, 100.5, 101.5, 100.0, 101.0, False)
    # the opposite wick inside the zone does NOT count
    assert not _entry_call(99.9, 99.0, 99.5, 100.0, 101.0, True)
    assert not _entry_call(102.0, 101.1, 101.5, 100.0, 101.0, False)


@pytest.mark.custom
def test_wick_entry_penetration_guard() -> None:
    """Bars punching through the far side of the zone are rejected."""
    # supply: 1.0 beyond the far edge with 0.5 tolerance -> reject
    assert not _entry_call(102.0, 99.0, 99.5, 100.0, 101.0, True)
    assert _entry_call(101.4, 99.0, 99.5, 100.0, 101.0, True)
    # demand mirror
    assert not _entry_call(102.0, 99.0, 101.5, 100.0, 101.0, False)
    assert _entry_call(102.0, 99.6, 101.5, 100.0, 101.0, False)


# -----------------------------------------------------------------------------
# Causal orderflow-shift filter
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_orderflow_shift_ignores_unconfirmed_and_future() -> None:
    """Only extremes formed AND confirmed before the retest bar count."""
    high = np.array([11.0, 11.0, 10.5, 10.0, 10.2, 10.4, 10.6, 9.0, 9.0])
    low = high - 1.0
    # peaks at 0 (ref), 2 (pivot, confirmed 3), 6 (confirmed only at 9)
    peak_list = [0, 2, 6]
    valley_list: list[int] = []
    pivot_confirm = {0: 1, 2: 3, 6: 9}
    # j=8: peak 6 is inside (2, 8) but confirms at 9 -> excluded
    assert not check_orderflow_shift(
        peak_list, valley_list, high, low, 2, 8, pivot_confirm, True, True
    )
    # j=10 (window is by index, not by array length): now confirmed;
    # lower high at 6 vs the pivot peak -> supply shift True
    assert check_orderflow_shift(
        peak_list, valley_list, high, low, 2, 10, pivot_confirm, True, True
    )


@pytest.mark.custom
def test_orderflow_shift_never_reads_future_bars() -> None:
    """Mutation test: changing bars at/after j must not change the result."""
    high = np.array([11.0, 11.0, 10.5, 10.0, 10.2, 10.4, 10.6, 10.1, 10.0])
    low = high - 1.0
    peak_list = [0, 2, 6]
    valley_list: list[int] = []
    pivot_confirm = {0: 1, 2: 3, 6: 5}
    base = check_orderflow_shift(
        peak_list, valley_list, high, low, 2, 7, pivot_confirm, True, True
    )
    assert base
    mutated_high = high.copy()
    mutated_high[7:] = 999.0  # clobber everything from the retest bar on
    mutated_low = low.copy()
    mutated_low[7:] = -999.0
    assert check_orderflow_shift(
        peak_list,
        valley_list,
        mutated_high,
        mutated_low,
        2,
        7,
        pivot_confirm,
        True,
        True,
    )


@pytest.mark.custom
def test_orderflow_shift_requires_online_pivots() -> None:
    """Offline pivots + shift filter is a look-ahead leak -> ValueError."""
    df, _, _ = make_ohlcv(300, seed=1)
    with pytest.raises(ValueError, match="online ZigZag"):
        identify_order_blocks(
            df,
            cfg=OrderBlockConfig(
                use_online_extremes=False,
                check_orderflow_shift=True,
            ),
        )


# -----------------------------------------------------------------------------
# Confirm-guarded extreme-gap filter (causality)
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_extreme_gap_filter_never_uses_unconfirmed_next_extreme() -> None:
    """A huge min_extreme_gap may only drop blocks whose next extreme
    was confirmed before the breakout; the survivor set must be a
    subset of the unfiltered set (no hindsight-based rejections)."""
    df, _, _ = make_ohlcv(350, seed=0)
    base_cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
        min_extreme_gap=0,
    )
    strict_cfg = OrderBlockConfig(
        use_online_extremes=True,
        online_reversal=2.0,
        min_extreme_gap=10_000,
    )
    base = identify_order_blocks(df, cfg=base_cfg)
    strict = identify_order_blocks(df, cfg=strict_cfg)
    assert base.height >= 1
    base_keys = set(
        zip(base["start"].to_list(), base["break"].to_list(), strict=True)
    )
    strict_keys = set(
        zip(strict["start"].to_list(), strict["break"].to_list(), strict=True)
    )
    assert strict_keys <= base_keys


# -----------------------------------------------------------------------------
# ATR-calibrated reversal threshold
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_reversal_atr_multiple_resolution() -> None:
    """2.5 * median(ATR), NaN warm-up ignored, wins over static value."""
    atr = np.array([np.nan, np.nan, 1.0, 2.0, 3.0, 2.0])
    cfg = OrderBlockConfig(reversal_atr_multiple=2.5, online_reversal=99.0)
    assert effective_online_reversal(cfg, atr) == pytest.approx(2.5 * 2.0)
    # static fallback when unset
    cfg2 = OrderBlockConfig(online_reversal=1.5)
    assert effective_online_reversal(cfg2, atr) == pytest.approx(1.5)
    # degenerate ATR series -> explicit error
    with pytest.raises(ValueError, match="ATR"):
        effective_online_reversal(
            OrderBlockConfig(reversal_atr_multiple=2.5),
            np.array([np.nan, np.nan]),
        )


@pytest.mark.custom
def test_reversal_atr_multiple_end_to_end() -> None:
    df, _, _ = make_ohlcv(300, seed=1)
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=2.5,
        atr_period=14,
    )
    out = identify_order_blocks(df, cfg=cfg)
    assert_valid_block_frame(out)


# -----------------------------------------------------------------------------
# Timeframe presets
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_timeframe_presets_tuned_values() -> None:
    """Presets encode the agreed recalibration decisions."""
    for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
        cfg = TIMEFRAME_CONFIGS[tf]
        assert cfg.use_online_extremes
        assert cfg.reversal_atr_multiple == 2.5
        assert cfg.zone_atr_multiplier == 0.2
        assert cfg.zone_source == "range"
        # ADX / RSI gates are inverted or harmful for OB retests
        assert not cfg.use_adx_filter
        if tf in ("1h", "4h", "1d"):
            assert not cfg.use_rsi_confirmation
    # low-timeframe clustering off (blurred distinct zones)
    assert not TIMEFRAME_CONFIGS["1m"].cluster_blocks
    assert not TIMEFRAME_CONFIGS["5m"].cluster_blocks
    # confirmation windows widened for the retest-delay distribution
    # (measured p90 ~ 35 bars on BTC 5m/15m -> cover it with 36)
    assert TIMEFRAME_CONFIGS["5m"].confirmation_window == 36
    assert TIMEFRAME_CONFIGS["15m"].confirmation_window == 36
    assert TIMEFRAME_CONFIGS["1h"].confirmation_window == 15
    # lookback_max = first-break search window (multiple_breakouts=True),
    # calibrated from the natural break-delay distribution (p90 ~ 28)
    assert TIMEFRAME_CONFIGS["5m"].lookback_max == 30
    assert TIMEFRAME_CONFIGS["15m"].lookback_max == 30
    assert TIMEFRAME_CONFIGS["1h"].lookback_max == 30
    assert TIMEFRAME_CONFIGS["5m"].multiple_breakouts
    assert TIMEFRAME_CONFIGS["15m"].multiple_breakouts


@pytest.mark.custom
@pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1h", "4h", "1d"])
def test_timeframe_presets_end_to_end(tf: str) -> None:
    df, _, _ = make_ohlcv(400, seed=5)
    out = identify_order_blocks(df, cfg=TIMEFRAME_CONFIGS[tf])
    assert_valid_block_frame(out)


# -----------------------------------------------------------------------------
# 2026-09-22 detector fixes: regression tests
# -----------------------------------------------------------------------------
@pytest.mark.custom
def test_causal_reversal_threshold_ignores_future_bars() -> None:
    """Warmup-median reversal: mutating the far future changes nothing."""
    df, _, _ = make_ohlcv(1500, seed=9)
    cfg = OrderBlockConfig(
        use_online_extremes=True,
        reversal_atr_multiple=1.5,
        reversal_warmup_bars=300,
        atr_period=14,
    )
    out_full = identify_order_blocks(df, cfg=cfg)
    # overwrite every bar after the warmup window with fresh noise
    # (same dates); a causal threshold cannot see this, so blocks fully
    # inside the warmup prefix must be identical
    rng = np.random.default_rng(123)
    close = df["close"].to_numpy().copy()
    high = df["high"].to_numpy().copy()
    low = df["low"].to_numpy().copy()
    volume = df["volume"].to_numpy().copy()
    spread = np.abs(rng.normal(0.4, 0.15, 500))
    close[1000:] = close[999] + np.cumsum(rng.normal(0, 0.8, 500))
    high[1000:] = close[1000:] + spread
    low[1000:] = close[1000:] - spread
    volume[1000:] = rng.gamma(2.0, 50.0, 500)
    df_future = df.with_columns(high=high, low=low, close=close,
                                volume=volume)
    out_mut = identify_order_blocks(df_future, cfg=cfg)
    cutoff = df["date"][1000]
    full_pre = out_full.filter(pl.col("retest") < cutoff)
    mut_pre = out_mut.filter(pl.col("retest") < cutoff)
    assert full_pre.height >= 1  # the property is tested on real data
    assert full_pre["start"].to_list() == mut_pre["start"].to_list()
    assert full_pre["retest"].to_list() == mut_pre["retest"].to_list()


@pytest.mark.custom
def test_breakout_window_scans_lookback_range() -> None:
    """Breakout inside [lookback_min, lookback_max) is always found."""
    n = 120
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    # retest volume gate needs volume > 20-bar SMA: a low head + high
    # tail keeps the SMA below the late-bar volume
    volume = np.concatenate([np.full(20, 1000.0), np.full(n - 20, 6000.0)])
    # one peak pivot at bar 20, breakout at bar 27 (7 bars later --
    # inside [5, 50); the old fixed-bar bug only checked idx + a
    # clamped constant, typically 50 bars after the pivot)
    high[20] = 110.0
    high[19] = 104.0
    high[21] = 104.0
    close[27] = low[27] = 95.0  # breaks below the pivot's low
    dates = np.array(
        [datetime(2024, 1, 1) + i * timedelta(hours=1) for i in range(n)]
    )
    df = pl.DataFrame(
        {
            "date": dates,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    base = dict(
        use_online_extremes=True,
        online_reversal=2.0,
        atr_period=5,
        breakout_volume_threshold=0.0,  # volume gate off
        require_zone_intact=False,
    )
    out = identify_order_blocks(
        df, cfg=OrderBlockConfig(lookback_min=5, lookback_max=50, **base)
    )
    from_pivot = out.filter(pl.col("start") == dates[20])
    assert from_pivot.height == 1
    assert from_pivot["block_type"][0] == "supply"
    assert from_pivot["break"][0] == dates[27]
    # a window that ends before the breakout misses this pivot
    out_early = identify_order_blocks(
        df, cfg=OrderBlockConfig(lookback_min=5, lookback_max=6, **base)
    )
    assert out_early.filter(pl.col("start") == dates[20]).height == 0


def _validation_env() -> tuple[dict, dict, "np.ndarray"]:
    """Minimal arrays for direct ``validate_block_candidates`` tests."""
    n = 60
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    close = np.full(n, 100.0)
    volume = np.full(n, 2000.0)  # above avg -> retest volume gate passes
    dates = np.array(
        [datetime(2024, 1, 1) + i * timedelta(hours=1) for i in range(n)]
    )
    indicators = {
        "avg_volume": np.full(n, 1000.0),
        "zone_low": np.full(n, 105.0),
        "zone_high": np.full(n, 110.0),
        "atr": np.full(n, 2.0),
    }
    env = dict(high=high, low=low, close=close, volume=volume, dates=dates)
    return env, indicators, dates


@pytest.mark.custom
def test_zone_intact_guard_rejects_rebroken_zone() -> None:
    from ta.src.custom.market_structure.validation import (
        validate_block_candidates,
    )

    env, indicators, dates = _validation_env()
    candidates = [{
        "idx": 30,
        "break_idx": 40,
        "block_type": "supply",
        "strength": 1.0,
        "start_date": dates[30],
    }]
    peaks = np.array([], dtype=np.int64)
    valleys = np.array([], dtype=np.int64)
    common = dict(
        high=env["high"], low=env["low"], close=env["close"],
        volume=env["volume"], dates=env["dates"],
        cfg=OrderBlockConfig(), indicators=indicators,
        peak_indices=peaks, valley_indices=valleys, existing_blocks=[],
    )
    # retest bar 45 wicks into the zone, closes well below it
    env["high"][45] = 107.0
    env["close"][45] = 100.0
    out = validate_block_candidates(candidates=candidates, **common)
    assert len(out) == 1  # clean zone -> valid retest
    # now the zone is re-pierced at bar 42 (high 115 > far edge + 0.5
    # span): the zone is dead, the retest must be rejected
    env["high"][42] = 115.0
    out = validate_block_candidates(candidates=candidates, **common)
    assert len(out) == 0
    # opt-out restores the old (leaky) behaviour
    common["cfg"] = OrderBlockConfig(require_zone_intact=False)
    out = validate_block_candidates(candidates=candidates, **common)
    assert len(out) == 1


@pytest.mark.custom
def test_structure_filter_confirm_guarded_online() -> None:
    from ta.src.custom.market_structure.validation import (
        validate_block_candidates,
    )

    env, indicators, dates = _validation_env()
    # structure: peaks 5, 10 confirmed early; peak 30 (the block's own
    # pivot) confirms only at bar 50 -- AFTER the candidate's pivot bar
    env["high"][5] = 100.0
    env["high"][10] = 105.0
    env["high"][30] = 103.0
    env["low"][20] = 95.0
    env["low"][25] = 98.0
    env["high"][45] = 107.0  # retest bar: wicks into the zone [105, 110]
    candidates = [{
        "idx": 30,
        "break_idx": 40,
        "block_type": "supply",
        "strength": 1.0,
        "start_date": dates[30],
    }]
    peaks = np.array([5, 10, 30], dtype=np.int64)
    valleys = np.array([20, 25], dtype=np.int64)
    cfg = OrderBlockConfig(
        use_market_structure_filter=True,
        structure_lookback=10,
        min_structure_extremes=2,
    )
    # ONLINE: pivot 30 is unconfirmed at bar 30, so the classification
    # may only see peaks [5, 10] -> HH + HL -> trend up -> a supply
    # block is REJECTED (misaligned).  The old code read the unconfirmed
    # peak 30 (LH), flipped the trend to unknown and accepted the block.
    out = validate_block_candidates(
        high=env["high"], low=env["low"], close=env["close"],
        volume=env["volume"], dates=env["dates"],
        candidates=candidates, cfg=cfg, indicators=indicators,
        peak_indices=peaks, valley_indices=valleys, existing_blocks=[],
        pivot_confirm={5: 7, 10: 12, 20: 22, 25: 27, 30: 50},
    )
    assert len(out) == 0
    # OFFLINE legacy mode (no confirm info): unchanged behaviour
    out = validate_block_candidates(
        high=env["high"], low=env["low"], close=env["close"],
        volume=env["volume"], dates=env["dates"],
        candidates=candidates, cfg=cfg, indicators=indicators,
        peak_indices=peaks, valley_indices=valleys, existing_blocks=[],
    )
    assert len(out) == 1


@pytest.mark.custom
def test_liquidity_tolerance_is_relative_to_price() -> None:
    """Scaling ALL prices by k must not change detected blocks."""
    df, _, _ = make_ohlcv(300, seed=3)
    cfg = dict(use_online_extremes=True, reversal_atr_multiple=2.5,
               atr_period=5)
    out_small = identify_order_blocks(df, cfg=OrderBlockConfig(**cfg))
    df_big = df.with_columns(
        pl.col("high") * 50.0,
        pl.col("low") * 50.0,
        pl.col("close") * 50.0,
    )
    out_big = identify_order_blocks(df_big, cfg=OrderBlockConfig(**cfg))
    assert out_small.height == out_big.height
    assert out_small["start"].to_list() == out_big["start"].to_list()
    assert out_small["retest"].to_list() == out_big["retest"].to_list()


@pytest.mark.custom
def test_online_pivot_indices_are_strictly_increasing() -> None:
    """Pivot bar indices are strictly increasing (audit batch 2, R7).

    ``pivot_confirm`` / ``pivot_next_extreme`` are dicts keyed by
    ``p.idx``; two pivots sharing a bar would silently collide.  That
    is impossible by construction: a pivot is confirmed at bar
    ``confirm_idx > pivot.idx`` and the next leg starts AT the confirm
    bar, so every later pivot index is strictly greater.
    """
    rng = np.random.default_rng(11)
    n = 2000
    close = 100.0 + np.cumsum(rng.normal(0, 1.0, n))
    spread = np.abs(rng.normal(0.5, 0.2, n))
    high = close + spread
    low = close - spread
    zz = OnlineZigZag(reversal=2.0)
    pivots = zz.update_series(high, low)
    assert len(pivots) >= 10
    idxs = [p.idx for p in pivots]
    assert all(a < b for a, b in pairwise(idxs))
    assert all(p.confirm_idx > p.idx for p in pivots)
