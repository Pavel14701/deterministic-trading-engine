"""Unit tests for the six entry-candidate families (stage A.2).

Each family is tested on a hand-crafted synthetic candle series so the
expected bar indices are known exactly.  Causality (no candidate before
``confirm_idx``) and deduplication priority are covered too.
"""

from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

from engine.candidates import (
    Candidate,
    collect_candidates,
    dedupe_candidates,
    detect_avsl_bounce,
    detect_break_retest,
    detect_fvg,
    detect_ob_retests,
    detect_ob_touches,
    detect_sweeps,
)
from engine.datatypes import OrderBlock


T0 = datetime(2024, 1, 1, tzinfo=UTC)


def make_df(
    opens: npt.NDArray[np.float64],
    highs: npt.NDArray[np.float64],
    lows: npt.NDArray[np.float64],
    closes: npt.NDArray[np.float64],
) -> pl.DataFrame:
    """Build a canonical OHLCV frame (unit volume, 1m ts spacing)."""
    n = len(opens)
    return pl.DataFrame(
        {
            "ts": 1_700_000_000_000 + np.arange(n, dtype=np.int64) * 60_000,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n),
        }
    )


def make_block(
    block_type: str,
    zone_low: float,
    zone_high: float,
    confirm_idx: int,
    block_id: int = 0,
) -> OrderBlock:
    """Build an order block whose zone is known at ``confirm_idx``."""
    return OrderBlock(
        id=block_id,
        block_type=block_type,
        start=T0,
        break_=T0,
        retest=T0,
        zone_low=zone_low,
        zone_high=zone_high,
        confirm_idx=confirm_idx,
    )


def ones(n: int) -> npt.NDArray[np.float64]:
    """Constant unit ATR series."""
    return np.ones(n)


@pytest.mark.unit
def test_ob_touch_and_retest_long() -> None:
    """First zone dip is a touch candidate, the second dip a retest."""
    opens = np.array([12.0] * 10)
    highs = np.array([12.5] * 10)
    lows = np.array([11.9, 11.9, 11.9, 11.9, 10.5, 11.9, 11.9, 11.9, 10.2, 11.9])
    closes = np.array([12.2] * 10)
    df = make_df(opens, highs, lows, closes)
    block = make_block("demand", 10.0, 11.0, confirm_idx=1)
    touches = detect_ob_touches(df, [block], ones(10))
    retests = detect_ob_retests(df, [block], ones(10))
    assert len(touches) == 1
    assert touches[0].entry_idx == 4
    assert touches[0].side == "long"
    assert touches[0].family == "ob_touch"
    assert len(retests) == 1
    assert retests[0].entry_idx == 8
    assert retests[0].family == "ob_retest"


@pytest.mark.unit
def test_supply_touch_is_short_and_zone_death_stops_scan() -> None:
    """Supply touch is short; a close above the zone kills the scan."""
    opens = np.array([9.0] * 6)
    highs = np.array([9.2, 9.2, 10.5, 12.5, 12.5, 12.5])
    lows = np.array([8.9] * 6)
    closes = np.array([9.1, 9.1, 10.4, 12.5, 12.5, 12.5])
    df = make_df(opens, highs, lows, closes)
    block = make_block("supply", 10.0, 11.0, confirm_idx=0)
    touches = detect_ob_touches(df, [block], ones(6))
    assert len(touches) == 1
    assert touches[0].entry_idx == 2
    assert touches[0].side == "short"


@pytest.mark.unit
def test_sweep_requires_pierce_and_reclaim() -> None:
    """Sweep fires when the wick pierces by wick_atr*ATR and close reclaims."""
    opens = np.array([12.0] * 6)
    highs = np.array([12.5] * 6)
    lows = np.array([11.9, 11.9, 9.4, 11.9, 9.4, 11.9])
    # Bar 2 pierces to 9.4 (< 10 - 0.5) but closes below zone -> no reclaim.
    # Bar 4 pierces to 9.4 and closes at 10.4 -> sweep.
    closes = np.array([12.2, 12.2, 9.8, 12.2, 10.4, 12.2])
    df = make_df(opens, highs, lows, closes)
    block = make_block("demand", 10.0, 11.0, confirm_idx=0)
    sweeps = detect_sweeps(df, [block], ones(6), wick_atr=0.5)
    assert len(sweeps) == 1
    assert sweeps[0].entry_idx == 4
    assert sweeps[0].side == "long"
    assert sweeps[0].family == "sweep"


@pytest.mark.unit
def test_fvg_bullish_entry_on_return() -> None:
    """Bullish gap at bar 2; entry when price returns into the gap."""
    opens = np.array([10.0, 11.0, 11.0, 11.0, 11.0, 11.0, 11.0])
    highs = np.array([10.0, 11.6, 11.6, 11.6, 11.6, 11.6, 11.6])
    lows = np.array([9.9, 10.5, 10.5, 11.5, 11.5, 11.5, 10.4])
    closes = np.array([10.0, 11.0, 11.0, 11.5, 11.5, 11.5, 10.6])
    # Bar 2: low=10.5 > high[0]=10.0 -> bullish FVG zone [10.0, 10.5].
    # Bar 6: low=10.4 <= 10.5 -> return into the gap.
    df = make_df(opens, highs, lows, closes)
    cands = detect_fvg(df, ones(7), min_gap_atr=0.2)
    assert len(cands) == 1
    assert cands[0].entry_idx == 6
    assert cands[0].side == "long"
    assert cands[0].zone_low == pytest.approx(10.0)
    assert cands[0].zone_high == pytest.approx(10.5)


@pytest.mark.unit
def test_fvg_min_gap_filters_small_gaps() -> None:
    """Gaps below ``min_gap_atr * ATR`` produce no candidates."""
    opens = np.full(4, 10.0)
    highs = np.array([10.0, 10.2, 10.2, 10.2])
    lows = np.array([9.9, 10.1, 10.1, 10.1])  # gap 0.1 < 0.2 * ATR=1
    closes = opens
    df = make_df(opens, highs, lows, closes)
    assert detect_fvg(df, ones(4), min_gap_atr=0.2) == []


@pytest.mark.unit
def test_avsl_bounce_long_and_short() -> None:
    """Touch of AVSL with bullish close is long; AVSR mirrored short."""
    n = 4
    opens = np.array([100.0, 100.5, 110.0, 109.5])
    highs = np.array([100.6, 100.9, 110.5, 110.0])
    lows = np.array([100.5, 100.2, 109.4, 109.8])
    closes = np.array([100.2, 100.8, 109.6, 109.0])
    df = make_df(opens, highs, lows, closes)
    avsl = np.full(n, 100.0)
    avsr = np.full(n, 110.0)
    cands = detect_avsl_bounce(df, avsl, avsr, ones(n), tol_atr=0.3)
    longs = [c for c in cands if c.side == "long"]
    shorts = [c for c in cands if c.side == "short"]
    assert [c.entry_idx for c in longs] == [1]
    assert [c.entry_idx for c in shorts] == [3]


@pytest.mark.unit
def test_avsl_bounce_skips_wrong_close_direction() -> None:
    """A bearish close at AVSL is not a long bounce."""
    opens = np.array([100.5])
    highs = np.array([100.6])
    lows = np.array([100.2])
    closes = np.array([100.1])  # close < open at the level
    df = make_df(opens, highs, lows, closes)
    cands = detect_avsl_bounce(
        df, np.full(1, 100.0), np.full(1, np.nan), ones(1), tol_atr=0.3
    )
    assert cands == []


@pytest.mark.unit
def test_break_retest_short_after_demand_break() -> None:
    """Demand broken down becomes resistance; return into zone is short."""
    opens = np.full(7, 11.0)
    highs = np.array([11.2, 10.8, 9.8, 9.8, 9.8, 9.8, 11.2])
    lows = np.array([10.9, 9.4, 9.2, 9.2, 9.2, 9.2, 10.4])
    closes = np.array([11.0, 9.5, 9.3, 9.3, 9.3, 9.3, 11.0])
    # Bar 1 closes below zone_low=10.0 (break); price stays below the
    # zone until bar 6, whose high rises back into the zone (retest).
    df = make_df(opens, highs, lows, closes)
    block = make_block("demand", 10.0, 11.0, confirm_idx=0)
    cands = detect_break_retest(df, [block], max_wait=10)
    assert len(cands) == 1
    assert cands[0].entry_idx == 6
    assert cands[0].side == "short"
    assert cands[0].family == "break_retest"


@pytest.mark.unit
def test_dedupe_priority_and_overlap_flag() -> None:
    """Sweep wins the collision with touch; overlap is flagged."""
    touch = Candidate(4, "long", "ob_touch", 10.0, 11.0, block_id=0)
    sweep = Candidate(4, "long", "sweep", 10.0, 11.0, block_id=0)
    out = dedupe_candidates([touch, sweep])
    assert len(out) == 1
    row = out.row(0, named=True)
    assert row["family"] == "sweep"
    assert row["overlap"] is True


@pytest.mark.unit
def test_dedupe_keeps_distinct_sides() -> None:
    """Same bar but opposite sides are separate candidates."""
    long_c = Candidate(4, "long", "ob_touch", 10.0, 11.0)
    short_c = Candidate(4, "short", "ob_touch", 10.0, 11.0)
    out = dedupe_candidates([long_c, short_c])
    assert out["side"].to_list() == ["long", "short"]
    assert out["overlap"].to_list() == [False, False]


@pytest.mark.unit
def test_collect_candidates_end_to_end() -> None:
    """``collect_candidates`` returns the expected schema and causality."""
    opens = np.array([12.0] * 10)
    highs = np.array([12.5] * 10)
    lows = np.array([11.9, 11.9, 11.9, 11.9, 10.5, 11.9, 11.9, 11.9, 10.2, 11.9])
    closes = np.array([12.2] * 10)
    df = make_df(opens, highs, lows, closes)
    block = make_block("demand", 10.0, 11.0, confirm_idx=1)
    out = collect_candidates(df, [block], ones(10))
    assert set(out.columns) == {
        "entry_idx",
        "side",
        "family",
        "zone_low",
        "zone_high",
        "block_id",
        "overlap",
    }
    assert set(out["family"].to_list()) == {"ob_touch", "ob_retest"}
    # Causality: nothing before the zone was known (confirm_idx=1).
    assert out["entry_idx"].min() > 1
    # With AVSL level at the dip bar the touch also bounces -> overlap.
    avsl = np.full(10, 10.6)
    out2 = collect_candidates(
        df, [block], ones(10), avsl=avsl, avsr=np.full(10, np.nan)
    )
    touch_row = out2.filter(pl.col("family") == "ob_touch").row(0, named=True)
    assert touch_row["overlap"] is True

