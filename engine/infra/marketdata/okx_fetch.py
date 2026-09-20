"""Fetch OHLCV candle history from OKX public REST (no API keys needed).

Used by the dataset-preparation pipeline (scripts/prepare_okx_dataset.py).
Pagination walks backwards in time via the ``after`` cursor:
``/market/candles`` serves the most recent bars (up to 300 per page),
``/market/history-candles`` serves older ones (up to 100 per page).
"""

from __future__ import annotations

import time

from pathlib import Path

import niquests
import polars as pl


BASE_URL = "https://www.okx.com/api/v5"
_PAGE_SLEEP = 0.1  # OKX allows ~20 history-candles requests / 2 s
_CHECKPOINT_BARS = 5_000  # flush the cache every N fetched bars
_FUNDING_PAGE_SLEEP = 0.15  # /public/funding-rate-history rate limit


def _rows_to_df(
    rows: list[list[str]], cached_df: pl.DataFrame | None
) -> pl.DataFrame:
    """Convert raw OKX rows into the canonical OHLCV frame.

    Args:
        rows: Accumulated raw rows (``ts, open, high, low, close, volume``).
        cached_df: Previously cached frame to merge with, if any.

    Returns:
        A frame sorted by ``ts`` ascending, deduplicated, float64 OHLCV.

    """
    df = pl.DataFrame(
        rows,
        schema={
            "ts": pl.Utf8,
            "open": pl.Utf8,
            "high": pl.Utf8,
            "low": pl.Utf8,
            "close": pl.Utf8,
            "volume": pl.Utf8,
        },
        orient="row",
    ).with_columns(
        pl.col("ts").cast(pl.Int64),
        pl.col(["open", "high", "low", "close", "volume"]).cast(pl.Float64),
    )
    df = df.unique(subset="ts", keep="first")
    if cached_df is not None:
        df = pl.concat([cached_df, df], how="vertical")
    return (
        df.unique(subset="ts", keep="first")
        .sort("ts")
        .select("ts", "open", "high", "low", "close", "volume")
    )


def _get(
    path: str, params: dict[str, str], timeout: float = 30.0, retries: int = 4
) -> list[list[str]]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = niquests.get(
                f"{BASE_URL}{path}", params=params, timeout=timeout
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX {path} error: {payload.get('msg')}")
            data: list[list[str]] = payload.get("data", [])
            return data
        except (niquests.RequestException, RuntimeError) as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(
        f"OKX {path} failed after {retries} attempts"
    ) from last_exc


def fetch_candles(
    inst_id: str,
    bar: str = "1m",
    max_bars: int = 20_000,
    cache_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Fetch up to ``max_bars`` confirmed candles for ``inst_id``.

    Args:
        inst_id: OKX instrument id, e.g. ``BTC-USDT``.
        bar: Bar size in OKX notation (``1m``, ``5m``, ``1H`` ...).
        max_bars: Maximum number of bars to collect.
        cache_dir: Optional directory; the fetched frame is cached as
            ``raw_<inst_id>_<bar>.parquet`` there and reused on reruns.

    Returns:
        Polars DataFrame sorted by ``ts`` ascending with columns
        ``ts, open, high, low, close, volume`` (``ts`` in ms,
        int64; OHLCV as float64).  Only ``confirm=1`` bars.

    """
    cache: Path | None = (
        Path(cache_dir) / f"raw_{inst_id}_{bar}.parquet" if cache_dir else None
    )
    cached_df: pl.DataFrame | None = None
    if cache is not None and cache.exists():
        cached_df = pl.read_parquet(cache)
        if cached_df.height >= max_bars:
            print(f"[{inst_id}] cache hit: {cache}")
            return cached_df.tail(max_bars)
        rows: list[list[str]] = []
        cursor = str(cached_df["ts"][0])
    else:
        rows = []
        cursor = None
    # Resuming from a cache: the oldest cached bar may be far outside
    # the recent endpoint's window (~1440 bars), which would serve an
    # empty page for the old cursor.  Start at the history endpoint.
    endpoint = (
        "/market/history-candles"
        if cached_df is not None
        else "/market/candles"
    )
    last_saved = 0
    while len(rows) < max_bars:
        params: dict[str, str] = {
            "instId": inst_id,
            "bar": bar,
            "limit": "300",
        }
        if cursor is not None:
            params["after"] = cursor
        page = _get(endpoint, params)
        if not page:
            # A transient empty page (rate-limit blips return empty data
            # with code "0" sometimes) must not be mistaken for the end
            # of history: re-ask once before concluding.
            time.sleep(1.5)
            page = _get(endpoint, params)
        if not page:
            if endpoint == "/market/candles":
                endpoint = "/market/history-candles"
                continue
            break
        for row in page:
            if len(row) > 8 and row[8] != "1":  # skip unconfirmed bar
                continue
            rows.append(row[:6])
        oldest = page[-1][0]
        if oldest == cursor:
            break
        cursor = oldest
        if len(rows) >= 300:  # switch to history endpoint for older data
            endpoint = "/market/history-candles"
        # Periodic checkpoint: a year of 1m bars is ~5000 pages, so an
        # interrupted run must not lose everything.  The partial frame is
        # written to the cache and reused as a resume point next time
        # (``cursor = cached_df["ts"][0]`` above).
        if cache is not None and len(rows) - last_saved >= _CHECKPOINT_BARS:
            last_saved = len(rows)
            partial = _rows_to_df(rows, cached_df)
            cache.parent.mkdir(parents=True, exist_ok=True)
            partial.write_parquet(cache)
            print(
                f"[{inst_id}] {bar}: {len(rows)}/{max_bars} bars "
                f"({len(partial)} cached)",
                flush=True,
            )
        time.sleep(_PAGE_SLEEP)

    rows = rows[:max_bars]
    if not rows:
        if cached_df is not None:
            # Cache already reaches listing depth -- nothing older exists.
            print(
                f"[{inst_id}] {bar}: cache complete "
                f"({cached_df.height} bars)"
            )
            return cached_df
        raise RuntimeError(f"no candles returned for {inst_id}")

    df = _rows_to_df(rows, cached_df)
    df = df.tail(max_bars)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache)
    return df


def fetch_funding_history(
    inst_id: str,
    max_records: int = 2_000,
    cache_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Fetch funding-rate settlement history for a OKX perp.

    Endpoint: ``/public/funding-rate-history`` (public, no keys),
    100 records per page, paginated backwards via the ``after``
    cursor (``fundingTime`` of the oldest record so far).

    Args:
        inst_id: OKX instrument id, e.g. ``BTC-USDT`` (USDT perp).
        max_records: Stop once this many records are collected.
        cache_dir: Optional directory; cached as
            ``funding_<inst_id>.parquet`` and reused on reruns.

    Returns:
        Polars DataFrame sorted by ``ts`` ascending with columns
        ``ts, rate`` (``ts`` = settlement time ms int64, ``rate`` =
        funding rate per settlement, float64; positive = longs pay
        shorts).

    """
    cache: Path | None = (
        Path(cache_dir) / f"funding_{inst_id}.parquet" if cache_dir else None
    )
    if cache is not None and cache.exists():
        # OKX /public/funding-rate-history only serves the most recent
        # ~3 months (~284 settlements), so a cache can never reach
        # max_records; reuse it as-is instead of refetching.
        return pl.read_parquet(cache)
    rows: list[tuple[int, float]] = []
    cursor: str | None = None
    while len(rows) < max_records:
        params: dict[str, str] = {"instId": inst_id, "limit": "100"}
        if cursor is not None:
            params["after"] = cursor
        page = _get("/public/funding-rate-history", params)
        if not page:
            break
        for row in page:
            # dict form: {instId, fundingRate, realizedRate, fundingTime,
            # method}; list form: [instId, fundingRate, realizedRate,
            # fundingTime, method]
            if isinstance(row, dict):
                rows.append((int(row["fundingTime"]),
                             float(row["fundingRate"])))
            else:
                rows.append((int(row[3]), float(row[1])))
        oldest = (page[-1]["fundingTime"]
                  if isinstance(page[-1], dict) else page[-1][3])
        if oldest == cursor:
            break
        cursor = oldest
        time.sleep(_FUNDING_PAGE_SLEEP)
    if not rows:
        raise RuntimeError(f"no funding history returned for {inst_id}")
    df = (
        pl.DataFrame(rows, schema={"ts": pl.Int64, "rate": pl.Float64},
                     orient="row")
        .unique(subset="ts", keep="first")
        .sort("ts")
    )
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache)
    return df
