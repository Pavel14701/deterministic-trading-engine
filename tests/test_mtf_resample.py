"""Unit tests for the MTF resampling module (stage A.1).

Covers OHLCV aggregation correctness, incomplete-bar handling, the
``known_ts`` causality contract and gap tolerance.
"""

import numpy as np
import polars as pl
import pytest

from engine.features.mtf import (
    BAR_MS,
    asof_rows,
    bar_duration_ms,
    resample_ohlcv,
)


BASE_TS = 1_699_833_600_000  # 2023-11-13 Mon 00:00 UTC (bar-boundary aligned)


def make_1m(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> pl.DataFrame:
    """Build a canonical 1m frame from price arrays."""
    n = len(opens)
    ts = BASE_TS + np.arange(n, dtype=np.int64) * 60_000
    return pl.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def flat_prices(n: int, price: float) -> tuple:
    """``n`` bars all trading at ``price`` with unit volume."""
    arr = np.full(n, price)
    return arr, arr, arr, arr, np.ones(n)


@pytest.mark.unit
def test_5m_aggregation_correct() -> None:
    """Three 5m bars aggregate open/high/low/close/volume correctly."""
    o = 10.0 + np.arange(15)  # 15 one-minute bars
    h = o + 2.0
    low = o - 1.0
    c = o + 0.5
    v = np.ones(15)
    df = make_1m(o, h, low, c, v)
    out = resample_ohlcv(df, "5m")
    assert len(out) == 3
    row = out.row(0, named=True)
    assert row["open"] == pytest.approx(10.0)
    assert row["high"] == pytest.approx(16.0)  # max high of bars 0-4
    assert row["low"] == pytest.approx(9.0)  # min low of bars 0-4
    assert row["close"] == pytest.approx(14.5)  # close of bar 4
    assert row["volume"] == pytest.approx(5.0)
    assert row["n_bars"] == 5


@pytest.mark.unit
def test_incomplete_tail_dropped() -> None:
    """A trailing partial target bar is never emitted."""
    o, h, low, c, v = flat_prices(17, 100.0)
    df = make_1m(o, h, low, c, v)
    out = resample_ohlcv(df, "5m")
    assert len(out) == 3  # 17 bars -> 3 complete 5m bars + 2 orphan
    assert out["n_bars"].sum() == 15


@pytest.mark.unit
def test_known_ts_causality() -> None:
    """``known_ts`` equals bar start + duration for every target bar."""
    o, h, low, c, v = flat_prices(30, 50.0)
    df = make_1m(o, h, low, c, v)
    out = resample_ohlcv(df, "5m")
    assert (out["known_ts"] - out["ts"]).to_list() == [BAR_MS["5m"]] * len(out)
    assert out["ts"].to_list() == [BASE_TS + i * BAR_MS["5m"] for i in range(len(out))]


@pytest.mark.unit
def test_hourly_from_1m() -> None:
    """180 1m bars produce exactly 3 complete 1h bars."""
    o, h, low, c, v = flat_prices(180, 25.0)
    df = make_1m(o, h, low, c, v)
    out = resample_ohlcv(df, "1h")
    assert len(out) == 3
    assert set(out["n_bars"].to_list()) == {60}


@pytest.mark.unit
def test_weekly_from_daily() -> None:
    """The module also resamples already-resampled frames (1d -> 1w)."""
    n = 10
    ts = BASE_TS + np.arange(n, dtype=np.int64) * BAR_MS["1d"]
    df = pl.DataFrame(
        {
            "ts": ts,
            "open": np.full(n, 1.0),
            "high": np.full(n, 2.0),
            "low": np.full(n, 0.5),
            "close": np.full(n, 1.5),
            "volume": np.full(n, 10.0),
        }
    )
    out = resample_ohlcv(df, "1w")
    assert len(out) == 1
    row = out.row(0, named=True)
    assert row["n_bars"] == 7
    assert row["high"] == pytest.approx(2.0)
    assert row["low"] == pytest.approx(0.5)


@pytest.mark.unit
def test_gaps_tolerated() -> None:
    """Missing source bars do not crash; aggregation uses present bars."""
    o, h, low, c, v = flat_prices(10, 7.0)
    df = make_1m(o, h, low, c, v)
    df = df.filter(pl.col("ts") != BASE_TS + 3 * 60_000)  # drop bar 3
    out = resample_ohlcv(df, "5m")
    assert len(out) == 2
    assert out["n_bars"].to_list() == [4, 5]


@pytest.mark.unit
def test_asof_rows_causal_filter() -> None:
    """``asof_rows`` returns only bars known at the decision time."""
    o, h, low, c, v = flat_prices(30, 50.0)
    df = make_1m(o, h, low, c, v)
    htf = resample_ohlcv(df, "5m")
    # Decision at the close of the first 5m bar: only that row is visible.
    visible = asof_rows(htf, BASE_TS + BAR_MS["5m"])
    assert len(visible) == 1
    # One ms earlier: nothing is visible yet.
    assert len(asof_rows(htf, BASE_TS + BAR_MS["5m"] - 1)) == 0


@pytest.mark.unit
def test_invalid_inputs_raise() -> None:
    """Missing columns, wrong dtype and unknown bars raise ``ValueError``."""
    o, h, low, c, v = flat_prices(6, 1.0)
    df = make_1m(o, h, low, c, v)
    with pytest.raises(ValueError, match=r"unsupported bar|unsupported target bar"):
        bar_duration_ms("2h")
    with pytest.raises(ValueError, match="unsupported target bar"):
        resample_ohlcv(df, "2h")
    with pytest.raises(ValueError, match="missing columns"):
        resample_ohlcv(df.drop("volume"), "5m")
    with pytest.raises(ValueError, match="Int64"):
        resample_ohlcv(df.with_columns(pl.col("ts").cast(pl.Utf8)), "5m")
