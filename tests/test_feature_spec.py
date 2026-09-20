"""Tests for the per-event feature matrix (engine.feature_spec) and
the HTF as-of feature adapter (engine.mtf.asof_join_features)."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from dsl.exceptions import DSLError, ParseError
from engine.feature_spec import FeatureDef, FeatureSpec, collect_features
from engine.mtf import asof_join_features, resample_ohlcv


STEP = 3_600_000
T0 = 1_700_000_000_000
MIN = 60_000
# 15m-grid-aligned epoch: resample_ohlcv buckets align to the epoch,
# so minute-bar MTF tests must start on a bucket boundary.
T0Q = T0 - (T0 % (15 * MIN))


def make_bars(closes, opens=None, highs=None, lows=None, volume=None):
    """Handcrafted hourly bar frame (mirrors tests/test_mfe_mae.py)."""
    closes = np.asarray(closes, dtype=np.float64)
    n = len(closes)
    opens = closes if opens is None else np.asarray(opens, dtype=np.float64)
    highs = (
        np.maximum(opens, closes)
        if highs is None
        else np.asarray(highs, dtype=np.float64)
    )
    lows = (
        np.minimum(opens, closes)
        if lows is None
        else np.asarray(lows, dtype=np.float64)
    )
    data = {
        "ts": T0 + STEP * np.arange(n),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    }
    if volume is not None:
        data["volume"] = np.asarray(volume, dtype=np.float64)
    return pl.DataFrame(data)


def make_minutes(closes, volume=None):
    """Handcrafted 1-minute bar frame for resampling tests."""
    closes = np.asarray(closes, dtype=np.float64)
    if volume is None:
        volume = np.ones_like(closes)
    volume = np.broadcast_to(
        np.asarray(volume, dtype=np.float64), closes.shape
    )
    data = {
        "ts": T0Q + MIN * np.arange(len(closes)),
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": np.array(volume),
    }
    return pl.DataFrame(data)


# ---------------------------------------------------------------- spec


def test_spec_roundtrip():
    spec = FeatureSpec(
        features=(
            FeatureDef(name="mom3", expr="close[3]"),
            FeatureDef(name="above", expr="close > sma(period=4)"),
        )
    )
    assert FeatureSpec.from_dict(spec.to_dict()) == spec


def test_spec_validation_fail_fast():
    with pytest.raises(ValueError, match="identifier"):
        FeatureDef(name="9bad", expr="close")
    with pytest.raises(ValueError, match="identifier"):
        FeatureDef(name="event_ts", expr="close")
    with pytest.raises(ParseError):
        FeatureDef(name="ok", expr="close >")
    with pytest.raises(ValueError, match="at least one"):
        FeatureSpec(features=())
    with pytest.raises(ValueError, match="duplicate"):
        FeatureSpec(
            features=(FeatureDef("a", "close"), FeatureDef("a", "high"))
        )


# ------------------------------------------------------------- collect


def test_collect_values_hand_computed():
    bars = make_bars([10, 11, 12, 13, 14, 15])
    spec = FeatureSpec(
        features=(
            FeatureDef(name="mom3", expr="close[3]"),
            FeatureDef(name="above_sma2", expr="close > sma(period=2)"),
            FeatureDef(name="rng", expr="let r = high - low in r / close"),
            FeatureDef(name="down", expr="close < close[1]"),
        )
    )
    out = collect_features(bars, spec, [4, 5])
    assert out["event_idx"].to_list() == [4, 5]
    assert out["event_ts"].to_list() == [T0 + 4 * STEP, T0 + 5 * STEP]
    assert out["mom3"].to_list() == [11.0, 12.0]
    # sma(2) at bar 4 = 13.5 <= 14 -> 1.0; bar 5 = 14.5 <= 15 -> 1.0
    assert out["above_sma2"].to_list() == [1.0, 1.0]
    assert out["rng"].to_list() == [0.0, 0.0]  # o = h = l = c bars
    assert out["down"].to_list() == [0.0, 0.0]  # monotonically rising


def test_numeric_arithmetic_keeps_value():
    bars = make_bars([10, 11, 12, 13, 14, 15])
    spec = FeatureSpec(
        features=(
            FeatureDef("ratio", "close / sma(period=2)"),
            FeatureDef("gap", "close[1] - close[3]"),
        )
    )
    out = collect_features(bars, spec, [4, 5])
    assert out["ratio"].to_list() == pytest.approx([14 / 13.5, 15 / 14.5])
    assert out["gap"].to_list() == pytest.approx([2.0, 2.0])


def test_warmup_nan_not_error():
    bars = make_bars([10, 11, 12])
    spec = FeatureSpec(features=(FeatureDef("back", "close[5]"),))
    out = collect_features(bars, spec, [0])
    assert out["back"][0] != out["back"][0]  # NaN, not an exception


def test_unknown_indicator_fails_fast():
    bars = make_bars([10, 11, 12])
    spec = FeatureSpec(features=(FeatureDef("x", "macd(period=5)"),))
    with pytest.raises(DSLError):
        collect_features(bars, spec, [2])


def test_event_idx_contract():
    bars = make_bars([10, 11, 12, 13])
    spec = FeatureSpec(features=(FeatureDef("c", "close"),))
    with pytest.raises(ValueError, match="strictly increasing"):
        collect_features(bars, spec, [3, 1])
    with pytest.raises(ValueError, match="strictly increasing"):
        collect_features(bars, spec, [1, 1])
    with pytest.raises(ValueError, match="within"):
        collect_features(bars, spec, [0, 4])


def test_empty_events_typed_schema():
    bars = make_bars([10.0])
    spec = FeatureSpec(features=(FeatureDef("c", "close"),))
    out = collect_features(bars, spec, [])
    assert out.height == 0
    assert out.schema == {
        "event_idx": pl.Int64,
        "event_ts": pl.Int64,
        "c": pl.Float64,
    }


# ----------------------------------------------------------- causality


def test_prefix_invariance_causal():
    """Truncating the frame after the last event changes nothing."""
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.standard_normal(64))
    volume = np.abs(rng.standard_normal(64)) + 0.5
    bars = make_bars(closes, volume=volume)
    spec = FeatureSpec(
        features=(
            FeatureDef("mom", "close[4] / close"),
            FeatureDef("atr_n", "atr(period=7) / close"),
            FeatureDef("rsi", "rsi(period=9)"),
            FeatureDef("ema_gap", "close - ema(period=5)"),
            FeatureDef("vol_up", "volume > volume[1]"),
        )
    )
    events = [10, 30, 44]
    full = collect_features(bars, spec, events)
    short = collect_features(bars.slice(0, 45), spec, events)
    assert full.equals(short)


def test_future_mutation_invariance():
    """Mutating bars after the last event changes nothing."""
    bars = make_bars([10, 11, 12, 13, 14, 15, 16, 17])
    spec = FeatureSpec(
        features=(
            FeatureDef("c", "close / atr(period=3)"),
            FeatureDef("s", "close - sma(period=4)"),
        )
    )
    base = collect_features(bars, spec, [3])
    cut_ts = T0 + 5 * STEP  # mutate bars 6..7 only

    def mutate(col):
        return (
            pl.when(pl.col("ts") > cut_ts)
            .then(pl.col(col) * 10)
            .otherwise(pl.col(col))
            .alias(col)
        )

    mutated = bars.with_columns(mutate("close"), mutate("high"), mutate("low"))
    assert base.equals(collect_features(mutated, spec, [3]))


# ------------------------------------------------------- mtf as-of join


def test_asof_join_causality_and_age():
    closes = np.linspace(10, 20, 180)
    minutes = make_minutes(closes, volume=1.0)
    htf = resample_ohlcv(minutes, "15m")
    base = pl.DataFrame(
        {
            "ts": [
                T0Q + 2 * MIN,  # bucket 0 still forming -> null
                T0Q + 15 * MIN,  # == known_ts(bucket 0) -> sees bucket 0
                T0Q + 17 * MIN,  # still bucket 0 -> sees bucket 0
                T0Q + 30 * MIN,  # == known_ts(bucket 1) -> sees bucket 1
            ]
        }
    )
    out = asof_join_features(
        base,
        htf,
        ["close", "volume"],
        prefix="h_",
        age_col="h_age_ms",
    )
    # bucket k close = closes[15k + 14]
    assert out["h_close"].to_list()[:1] == [None]
    assert out["h_close"].to_list()[1:] == pytest.approx(
        [closes[14], closes[14], closes[29]]
    )
    assert out["h_volume"].to_list()[1:] == pytest.approx([15.0, 15.0, 15.0])
    assert out["h_age_ms"].to_list() == [None, 0, 2 * MIN, 0]


def test_asof_join_fail_fast():
    closes = np.linspace(10, 20, 40)
    minutes = make_minutes(closes)
    htf = resample_ohlcv(minutes, "15m")
    base = pl.DataFrame({"ts": [T0], "htf_close": [1.0]})
    with pytest.raises(ValueError, match="already in base"):
        asof_join_features(base, htf, ["close"])
    with pytest.raises(ValueError, match="missing columns"):
        asof_join_features(pl.DataFrame({"ts": [T0]}), htf, ["nope"])
    with pytest.raises(ValueError, match="duplicate"):
        asof_join_features(pl.DataFrame({"ts": [T0]}), htf, ["close", "close"])
    with pytest.raises(ValueError, match="must not be empty"):
        asof_join_features(pl.DataFrame({"ts": [T0]}), htf, [])


def test_asof_join_preserves_base_sort():
    closes = np.linspace(10, 20, 60)
    htf = resample_ohlcv(make_minutes(closes), "15m")
    base = pl.DataFrame({"ts": [T0Q + 20 * MIN, T0Q + 16 * MIN]})
    out = asof_join_features(base, htf, ["close"])
    assert out["ts"].to_list() == sorted(out["ts"].to_list())
    assert out["htf_close"].to_list() == pytest.approx(
        [closes[14], closes[14]]
    )
