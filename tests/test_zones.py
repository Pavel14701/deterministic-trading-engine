"""Unit tests for the stop-geometry engine (scripts/zones.py).

Covers the per-bar TP/SL rules (atr / zone / anchor) and the first-match
zone painting.  Indicator anchor *series* are not tested here (they need
the vendored ta kernels); the side-resolution logic is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from engine.zones import (
    anchor_for_side,
    build_tp_sl,
    paint_zone,
)


@dataclass
class _Block:
    """Minimal order-block stand-in for paint_zone."""

    block_type: str
    zone_low: float
    zone_high: float
    end_idx: int


class TestAnchorForSide:
    def test_side_validity(self) -> None:
        assert anchor_for_side("avsl", "long") == "avsl"
        assert anchor_for_side("avsl", "short") is None
        assert anchor_for_side("avsr", "short") == "avsr"
        assert anchor_for_side("avsr", "long") is None

    def test_direction_families(self) -> None:
        assert anchor_for_side("hilo", "long") == "hilo_l"
        assert anchor_for_side("hilo", "short") == "hilo_s"
        assert anchor_for_side("bb", "long") == "bb_l"
        assert anchor_for_side("bb", "short") == "bb_u"
        assert anchor_for_side("st", "short") == "st"

    def test_unknown_family(self) -> None:
        assert anchor_for_side("nope", "long") is None


class TestPaintZone:
    def test_first_match_wins(self) -> None:
        # two demand blocks overlapping in horizon: earlier one wins
        blocks = [
            _Block("demand", zone_low=100.0, zone_high=101.0, end_idx=0),
            _Block("demand", zone_low=200.0, zone_high=201.0, end_idx=5),
        ]
        zone = paint_zone(blocks, n=10, side="long")
        assert np.all(zone == 100.0)

    def test_side_filter(self) -> None:
        blocks = [_Block("supply", zone_low=90.0, zone_high=91.0, end_idx=0)]
        assert np.all(np.isnan(paint_zone(blocks, n=5, side="long")))
        zone = paint_zone(blocks, n=5, side="short")
        assert np.all(zone == 91.0)  # stop edge = zone_high for shorts

    def test_horizon_limited(self) -> None:
        blocks = [_Block("demand", zone_low=100.0, zone_high=101.0, end_idx=8)]
        zone = paint_zone(blocks, n=10, side="long")
        assert np.isnan(zone[:8]).all()
        assert np.isfinite(zone[8:]).all()


class TestBuildTpSl:
    close = np.full(10, 100.0)
    atr = np.full(10, 1.0)

    def test_atr_rule(self) -> None:
        tp, sl = build_tp_sl(self.close, self.atr, "atr:2", 2.0, "long",
                             zone=None)
        assert np.allclose(sl, 98.0)
        assert np.allclose(tp, 104.0)

    def test_zone_rule_uses_buffer(self) -> None:
        zone = np.full(10, 99.0)
        tp, sl = build_tp_sl(self.close, self.atr, "zone:0.5", 2.0, "long",
                             zone=zone)
        assert np.allclose(sl, 98.5)  # zone_low - 0.5*ATR
        assert np.allclose(tp, 103.0)  # 100 + 2*(100-98.5)

    def test_anchor_rule_resolves_level(self) -> None:
        anchors = {"avsl": np.full(10, 97.0)}
        out = build_tp_sl(self.close, self.atr, "anchor:avsl:1.0", 2.0,
                          "long", zone=None, anchors=anchors)
        _tp, sl = out
        assert np.allclose(sl, 96.0)

    def test_side_invalid_anchor_yields_no_trades(self) -> None:
        anchors = {"avsl": np.full(10, 97.0)}
        tp, sl = build_tp_sl(self.close, self.atr, "anchor:avsl:1.0", 2.0,
                             "short", zone=None, anchors=anchors)
        assert np.isnan(sl).all()
        assert np.isnan(tp).all()

    def test_min_risk_filter(self) -> None:
        # stop 0.5 ATR away < min_risk_atr=1 -> bar invalidated
        tp, sl = build_tp_sl(self.close, self.atr, "atr:0.5", 2.0, "long",
                             zone=None, min_risk_atr=1.0)
        assert np.isnan(sl).all()
        assert np.isnan(tp).all()

    def test_short_geometry_mirrors_long(self) -> None:
        tp_l, sl_l = build_tp_sl(self.close, self.atr, "atr:2", 2.0, "long",
                                 zone=None)
        tp_s, sl_s = build_tp_sl(self.close, self.atr, "atr:2", 2.0, "short",
                                 zone=None)
        assert np.allclose(sl_s, 102.0)
        assert np.allclose(tp_s, 96.0)
        # identical risk unit and target distance
        assert np.allclose(tp_l - self.close, self.close - tp_s)
        assert np.allclose(sl_s - self.close, self.close - sl_l)

    def test_unknown_rule_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown stop rule"):
            build_tp_sl(self.close, self.atr, "magic:7", 2.0, "long", zone=None)
