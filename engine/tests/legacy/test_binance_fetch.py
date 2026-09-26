"""Cache-merge and kline-parse pins for the Binance fetcher.

The merge contract matters downstream: the cache must never shrink
or rewrite history (keep-old on duplicate ts), and the kline parser
must drop the in-progress bar and keep the aggressor-flow column.
"""
import time

import polars as pl

from engine.infra.marketdata.binance_fetch import (
    _parse_klines,
    merge_frames,
)


def _frame(ts: list[int], v: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"ts": ts, "oi": v}).cast(
        {"ts": pl.Int64, "oi": pl.Float64}
    )


def test_merge_sorted_and_deduped():
    old = _frame([10, 20], [1.0, 2.0])
    new = _frame([15, 20, 5], [9.0, 8.0, 7.0])
    df = merge_frames(old, new)
    assert df["ts"].to_list() == [5, 10, 15, 20]


def test_merge_keeps_old_row_on_duplicate_ts():
    old = _frame([10], [1.0])
    new = _frame([10], [99.0])
    df = merge_frames(old, new)
    assert df.height == 1
    assert df["oi"][0] == 1.0


def test_merge_never_shrinks():
    old = _frame([1, 2, 3], [1.0, 2.0, 3.0])
    df = merge_frames(old, _frame([], []))
    assert df.height == 3


def test_merge_none_old_is_sorted_new():
    df = merge_frames(None, _frame([30, 10], [3.0, 1.0]))
    assert df["ts"].to_list() == [10, 30]


def _raw_row(ts_ms: int, close_ms: int) -> list[str]:
    return [
        str(ts_ms), "100", "110", "90", "105", "1000",
        str(close_ms), "105000", "42", "600", "63000", "0",
    ]


def test_parse_klines_drops_in_progress_bar():
    now = int(time.time() * 1000)
    rows = [
        _raw_row(now - 3_600_000, now - 1),
        _raw_row(now, now + 3_599_000),  # still open -> dropped
    ]
    df = _parse_klines(rows)
    assert df.height == 1
    assert df["close_time"][0] == now - 1


def test_parse_klines_schema_and_taker_flow():
    now = int(time.time() * 1000)
    df = _parse_klines([_raw_row(now - 3_600_000, now - 1)])
    assert df["ts"].dtype == pl.Int64
    assert df["close"].dtype == pl.Float64
    assert df["taker_buy_volume"][0] == 600.0
    assert df["n_trades"][0] == 42
