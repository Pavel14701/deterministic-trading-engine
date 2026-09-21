"""Fetch Binance USDT-M futures data (public REST, no API keys).

Same page-cache pattern as ``okx_fetch``: the raw parquet files ARE
the cache, re-runs are incremental.  Two products:

- ``fetch_klines``: ``/fapi/v1/klines`` -- full history (BTC back to
  2019 verified live), 1500 bars/page walked backwards via the
  ``endTime`` cursor.  The frame keeps the aggressor-side flow
  column ``taker_buy_volume`` (kline field 9, taker buy base
  volume) -- the order-flow feature for the TTF / ProSP v2 tracks.
  Only closed bars are kept (``close_time`` in the past).

- ``fetch_oi_history``: ``/futures/data/openInterestHist`` --
  Binance hard-caps this endpoint at the most recent ~30 days
  (verified live 2026-09-21: an ``endTime`` older than 30d returns
  HTTP 400).  The cache is therefore MERGE-APPEND: each run fetches
  the whole 30d window and unions it into the existing parquet, so
  running at least once every 30 days accumulates an unbounded
  panel.  This is the OI accumulation track (STATUS.md 2026-09-21):
  no backtest now, a testable panel in ~3 months.
"""

from __future__ import annotations

import time

from pathlib import Path
from typing import cast

import niquests
import polars as pl


BASE_URL = "https://fapi.binance.com"
_PAGE_SLEEP = 0.25  # klines allows 6000 weights/min; stay polite
_KLINE_PAGE = 1_500
_OI_PAGE = 500
_KLINE_SCHEMA = pl.Schema(
    {
        "ts": pl.Int64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "close_time": pl.Int64,
        "quote_volume": pl.Float64,
        "n_trades": pl.Int64,
        "taker_buy_volume": pl.Float64,
    }
)
_OI_SCHEMA = pl.Schema(
    {
        "ts": pl.Int64,
        "oi": pl.Float64,        # sumOpenInterest, base-asset units
        "oi_quote": pl.Float64,  # sumOpenInterestValue, USDT
    }
)
_RAW_KLINE_SCHEMA = pl.Schema(
    {f"column_{i}": pl.String for i in range(1, 13)}
)


class _WindowEndError(Exception):
    """Raised internally when the endpoint's retention window ends."""


def _get(
    path: str, params: dict[str, str], timeout: float = 30.0, retries: int = 4
) -> list[dict[str, str]] | list[list[str]]:
    """GET a public Binance endpoint, retrying transient failures.

    Args:
        path: Endpoint path appended to ``BASE_URL``.
        params: Query parameters.
        timeout: Per-request timeout in seconds.
        retries: Attempts before giving up.

    Returns:
        The raw JSON payload (list of dicts or lists).

    Raises:
        RuntimeError: When the endpoint keeps failing.
        _WindowEndError: HTTP 400 -- retention window reached
            (openInterestHist answers 400 for an ``endTime`` older
            than ~30 days; a clean stop signal, not an error).

    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = niquests.get(
                f"{BASE_URL}{path}", params=params, timeout=timeout
            )
            resp.raise_for_status()
            payload: dict[str, object] | list[object] = resp.json()
            data = cast(
                "list[dict[str, str]] | list[list[str]]",
                payload.get("data", [])  # type: ignore[union-attr]
                if isinstance(payload, dict)
                else payload,
            )
            return data
        except niquests.HTTPError as exc:
            status = getattr(
                getattr(exc, "response", None), "status_code", 0
            )
            if status == 400:
                raise _WindowEndError() from exc
            last_exc = exc
        except niquests.RequestException as exc:
            last_exc = exc
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(
        f"Binance {path} failed after {retries} attempts"
    ) from last_exc


def merge_frames(
    old: pl.DataFrame | None, new: pl.DataFrame
) -> pl.DataFrame:
    """Union two ts-keyed frames into a sorted, deduplicated frame.

    The cache is immutable-by-convention: on duplicate ``ts`` the
    previously cached row wins (``concat(old, new)`` + keep-first),
    so a merge can never rewrite history or shrink the panel.

    Args:
        old: Previously cached frame (or None/empty for fresh cache).
        new: Newly fetched frame.

    Returns:
        Frame sorted by ``ts`` ascending, unique per ``ts``.

    """
    if old is None or old.height == 0:
        return new.sort("ts").unique(subset="ts", keep="first")
    df = pl.concat([old, new], how="vertical")
    return df.unique(subset="ts", keep="first").sort("ts")


def _parse_klines(rows: list[list[str]]) -> pl.DataFrame:
    """Convert raw kline rows into the canonical frame.

    Args:
        rows: Raw rows ``[open_time, o, h, l, c, v, close_time, qv,
            n_trades, taker_buy_base, taker_buy_quote, ignore]``.

    Returns:
        Typed frame with the ``_KLINE_SCHEMA`` columns; in-progress
        bars (``close_time`` in the future) are dropped.

    """
    df = (
        pl.DataFrame(rows, schema=_RAW_KLINE_SCHEMA, orient="row")
        .rename(
            {
                "column_1": "ts",
                "column_2": "open",
                "column_3": "high",
                "column_4": "low",
                "column_5": "close",
                "column_6": "volume",
                "column_7": "close_time",
                "column_8": "quote_volume",
                "column_9": "n_trades",
                "column_10": "taker_buy_volume",
            }
        )
        .select(*_KLINE_SCHEMA)
        .cast(_KLINE_SCHEMA)
    )
    now_ms = int(time.time() * 1000)
    return df.filter(pl.col("close_time") <= now_ms)


def fetch_klines(
    symbol: str,
    interval: str = "1h",
    max_bars: int = 60_000,
    cache_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Fetch up to ``max_bars`` closed klines for a Binance perp.

    Args:
        symbol: Binance USDT-M symbol, e.g. ``BTCUSDT``.
        interval: Bar size (``1m`` ... ``1d``).
        max_bars: Maximum bars in the cached frame.
        cache_dir: Optional directory; cached as
            ``kl_{symbol}_{interval}.parquet``.  Re-runs fetch only
            bars newer than the cache end (incremental).

    Returns:
        Frame sorted by ``ts`` ascending (epoch-ms int64) with the
        ``_KLINE_SCHEMA`` columns incl. ``taker_buy_volume``.

    """
    cache: Path | None = (
        Path(cache_dir) / f"kl_{symbol}_{interval}.parquet"
        if cache_dir
        else None
    )
    cached: pl.DataFrame | None = None
    if cache is not None and cache.exists():
        cached = pl.read_parquet(cache)
        start = int(cached["ts"].max()) + 1  # type: ignore[arg-type]
        rows: list[list[str]] = []
        while len(rows) < max_bars:
            page = cast(
                "list[list[str]]",
                _get(
                    "/fapi/v1/klines",
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": str(start),
                        "limit": str(_KLINE_PAGE),
                    },
                ),
            )
            if not page:
                break
            rows.extend(page)
            start = int(page[-1][0]) + 1
            if start > int(time.time() * 1000):
                break
            time.sleep(_PAGE_SLEEP)
        df = (
            merge_frames(cached, _parse_klines(rows)) if rows else cached
        )
        if df.height < max_bars:
            # Depth-extension: walk backwards from the oldest cached
            # bar until the cap is reached (same behavior as
            # okx_fetch.fetch_candles -- depth grows run over run).
            older: list[list[str]] = []
            end = int(df["ts"].min()) - 1  # type: ignore[arg-type]
            while df.height + len(older) < max_bars:
                page = cast(
                    "list[list[str]]",
                    _get(
                        "/fapi/v1/klines",
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "endTime": str(end),
                            "limit": str(_KLINE_PAGE),
                        },
                    ),
                )
                if not page:
                    break
                older = page + older
                end = int(page[0][0]) - 1
                time.sleep(_PAGE_SLEEP)
            if older:
                df = merge_frames(df, _parse_klines(older)).tail(max_bars)
    else:
        end = int(time.time() * 1000)
        back: list[list[str]] = []
        while len(back) < max_bars:
            page = cast(
                "list[list[str]]",
                _get(
                    "/fapi/v1/klines",
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "endTime": str(end),
                        "limit": str(_KLINE_PAGE),
                    },
                ),
            )
            if not page:
                break
            back = page + back
            end = int(page[0][0]) - 1
            time.sleep(_PAGE_SLEEP)
        df = _parse_klines(back).tail(max_bars)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache)
    return df


def fetch_oi_history(
    symbol: str,
    interval: str = "1h",
    cache_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Fetch the 30d OI window and merge-append it into the cache.

    Args:
        symbol: Binance USDT-M symbol, e.g. ``BTCUSDT``.
        interval: Window granularity (``5m`` ... ``1d``).
        cache_dir: Required in practice; cached as
            ``oi_{symbol}_{interval}.parquet``.  Each run unions the
            fetched window into the existing file, so periodic runs
            accumulate a panel beyond Binance's 30d retention cap.

    Returns:
        The FULL cached frame (not just the fetched window) sorted
        by ``ts`` ascending with columns ``ts, oi, oi_quote``.

    """
    cache: Path | None = (
        Path(cache_dir) / f"oi_{symbol}_{interval}.parquet"
        if cache_dir
        else None
    )
    cached: pl.DataFrame | None = None
    if cache is not None and cache.exists():
        cached = pl.read_parquet(cache)
    end = int(time.time() * 1000)
    rows: list[dict[str, str]] = []
    while True:
        try:
            page = cast(
                "list[dict[str, str]]",
                _get(
                    "/futures/data/openInterestHist",
                    {
                        "symbol": symbol,
                        "period": interval,
                        "endTime": str(end),
                        "limit": str(_OI_PAGE),
                    },
                ),
            )
        except _WindowEndError:
            break
        if not page:
            break
        rows = page + rows
        end = int(page[0]["timestamp"]) - 1
        time.sleep(_PAGE_SLEEP)
    df_new = pl.DataFrame(
        {
            "ts": [int(r["timestamp"]) for r in rows],
            "oi": [float(r["sumOpenInterest"]) for r in rows],
            "oi_quote": [float(r["sumOpenInterestValue"]) for r in rows],
        }
    ).cast(_OI_SCHEMA)
    df = merge_frames(cached, df_new)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache)
    return df
