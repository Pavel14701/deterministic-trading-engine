"""Tests for the FeatureProvider (engine.feature_provider)."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from dsl.exceptions import DSLError
from engine.feature_provider import ColumnProvider, HybridContextFactory
from engine.feature_spec import FeatureDef, FeatureSpec, collect_features
from engine.mfe_mae import MfeMaeSpec, collect_mfe_mae


STEP = 3_600_000
T0 = 1_700_000_000_000


def make_bars(closes):
    """Handcrafted hourly bar frame."""
    closes = np.asarray(closes, dtype=np.float64)
    return pl.DataFrame(
        {
            "ts": T0 + STEP * np.arange(len(closes)),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
        }
    )


def test_provider_validation_fail_fast():
    extra = pl.DataFrame(
        {"ts": [T0], "x": [1.0], "9bad": [2.0], "close": [3.0]}
    )
    with pytest.raises(ValueError, match="must not be empty"):
        ColumnProvider(extra, [])
    with pytest.raises(ValueError, match="duplicate"):
        ColumnProvider(extra, ["x", "x"])
    with pytest.raises(ValueError, match="missing columns"):
        ColumnProvider(extra, ["nope"])
    with pytest.raises(ValueError, match="identifiers"):
        ColumnProvider(extra, ["9bad"])
    with pytest.raises(ValueError, match="collide"):
        ColumnProvider(extra, ["close"])


def test_hybrid_values_and_offsets():
    bars = make_bars([10, 11, 12, 13])
    extra = pl.DataFrame(
        {
            "ts": bars["ts"],
            "htf_close": [100.0, 101.0, 102.0, 103.0],
        }
    )
    factory = HybridContextFactory(extra, ["htf_close"])
    spec = FeatureSpec(
        features=(
            FeatureDef("diff", "close - htf_close"),
            FeatureDef("prev", "htf_close[1]"),
            FeatureDef("above", "close > htf_close"),
        )
    )
    out = collect_features(bars, spec, [1, 3], context_factory=factory)
    assert out["diff"].to_list() == pytest.approx([-90.0, -90.0])
    assert out["prev"].to_list() == pytest.approx([100.0, 102.0])
    assert out["above"].to_list() == [0.0, 0.0]
    assert out.schema["diff"] == pl.Float64
    assert out.schema["above"] == pl.Float64  # flags, not Boolean


def test_warmup_nan_for_columns():
    bars = make_bars([10, 11, 12])
    extra = pl.DataFrame({"ts": bars["ts"], "h": [1.0, 2.0, 3.0]})
    factory = HybridContextFactory(extra, ["h"])
    spec = FeatureSpec(features=(FeatureDef("back", "h[2]"),))
    out = collect_features(bars, spec, [0, 2], context_factory=factory)
    assert out["back"][0] != out["back"][0]  # NaN at bar 0 (warm-up)
    assert out["back"][1] == pytest.approx(1.0)  # event bar 2: h[2] = row 0


def test_prefix_invariance_with_columns():
    rng = np.random.default_rng(11)
    closes = 100 + np.cumsum(rng.standard_normal(32))
    bars = make_bars(closes)
    extra = pl.DataFrame(
        {
            "ts": bars["ts"],
            "h_close": closes * 1.01,
            "h_vol": np.abs(rng.standard_normal(32)),
        }
    )
    spec = FeatureSpec(
        features=(
            FeatureDef("gap", "close - h_close"),
            FeatureDef("h_mom", "h_close / h_close[3]"),
            FeatureDef("h_hot", "h_vol > h_vol[1]"),
        )
    )
    events = [5, 15, 25]
    full = collect_features(
        bars,
        spec,
        events,
        context_factory=(HybridContextFactory(extra, ["h_close", "h_vol"])),
    )
    short = collect_features(
        bars.slice(0, 26),
        spec,
        events,
        context_factory=(
            HybridContextFactory(extra.slice(0, 26), ["h_close", "h_vol"])
        ),
    )
    assert full.equals(short)


def test_alignment_guards_fail_fast():
    bars = make_bars([10, 11, 12, 13])
    spec = FeatureSpec(features=(FeatureDef("d", "close - h"),))
    # height mismatch
    short_extra = pl.DataFrame({"ts": bars["ts"][:2], "h": [1.0, 2.0]})
    with pytest.raises(ValueError, match="1:1"):
        collect_features(
            bars,
            spec,
            [3],
            context_factory=HybridContextFactory(short_extra, ["h"]),
        )
    # same height, ts mismatch
    shifted = pl.DataFrame({"ts": bars["ts"] + 1, "h": [1.0, 2.0, 3.0, 4.0]})
    with pytest.raises(ValueError, match="not aligned"):
        collect_features(
            bars,
            spec,
            [3],
            context_factory=HybridContextFactory(shifted, ["h"]),
        )


def test_unknown_indicator_with_hybrid_still_raises():
    bars = make_bars([10, 11, 12])
    extra = pl.DataFrame({"ts": bars["ts"], "h": [1.0, 2.0, 3.0]})
    factory = HybridContextFactory(extra, ["h"])
    spec = FeatureSpec(features=(FeatureDef("x", "macd(period=5)"),))
    with pytest.raises(DSLError):
        collect_features(bars, spec, [2], context_factory=factory)


def test_mfe_mae_signal_with_columns():
    bars = make_bars([10, 11, 12, 13])
    extra = pl.DataFrame({"ts": bars["ts"], "gate": [5.0, 5.0, 20.0, 20.0]})
    factory = HybridContextFactory(extra, ["gate"])
    ev = collect_mfe_mae(
        bars,
        MfeMaeSpec(signal="close > gate"),
        context_factory=factory,
    )
    # signal fires only at bars 0 and 1
    assert ev["signal_ts"].to_list() == [T0, T0 + STEP]
