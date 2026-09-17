"""Fetch OHLCV candle history from the T-Invest REST API.

Used by the dataset-preparation pipeline via the shared
``marketdata`` registry.  Pagination walks forward in fixed chunks
(``GetCandles`` accepts ``from``/``to`` instants, not cursors); prices
arrive as Quotation objects (``units`` + ``nano``) and are converted to
float.  Output is the same canonical frame as the OKX adapter:
``ts, open, high, low, close, volume`` (``ts`` in ms, int64).
"""

from __future__ import annotations

import time

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from tinvest.src.http import _PAGE_SLEEP, api_post
from tinvest.src.instruments import resolve_instrument
from tinvest.src.mapping import resolve_bar


_CHECKPOINT_BARS = 5_000
_CHUNK_CANDLES = 1_000  # request window size, in bars


def _quotation_to_float(q: dict) -> float:
    """Convert a Quotation object (units + nano) to a float."""
    return float(q.get("units", 0)) + float(q.get("nano", 0)) / 1e9


def _ts_to_ms(ts: str) -> int:
    """Convert an RFC3339 timestamp string to epoch milliseconds."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _candles_page(
    figi: str,
    interval: str,
    from_ms: int,
    to_ms: int,
    token: str | None,
) -> list[dict]:
    """Request one GetCandles page for the [from, to) window."""
    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    body = {
        "figi": figi,
        "interval": interval,
        "from": datetime.fromtimestamp(
            from_ms / 1000, tz=timezone.utc
        ).strftime(fmt),
        "to": datetime.fromtimestamp(to_ms / 1000, tz=timezone.utc).strftime(
            fmt
        ),
        "candleSourceType": "CANDLE_SOURCE_EXCHANGE",
    }
    resp = api_post(
        "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
        body=body,
        token=token,
    )
    return resp.get("candles") or []


def _rows_to_df(
    candles: list[dict], cached_df: pl.DataFrame | None
) -> pl.DataFrame:
    """Convert GetCandles payloads into the canonical OHLCV frame."""
    rows = [
        (
            _ts_to_ms(c["time"]),
            _quotation_to_float(c["open"]),
            _quotation_to_float(c["high"]),
            _quotation_to_float(c["low"]),
            _quotation_to_float(c["close"]),
            _quotation_to_float(c.get("volume", {"units": 0, "nano": 0})),
        )
        for c in candles
    ]
    df = pl.DataFrame(
        rows,
        schema={
            "ts": pl.Int64,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        },
        orient="row",
    )
    if df.height:
        df = df.unique(subset="ts", keep="first")
    if cached_df is not None and cached_df.height:
        df = pl.concat([cached_df, df], how="vertical")
    return (
        df.unique(subset="ts", keep="first")
        .sort("ts")
        .select("ts", "open", "high", "low", "close", "volume")
    )


def fetch_candles(
    inst: str,
    bar: str = "1m",
    max_bars: int = 20_000,
    cache_dir: str | Path | None = None,
    token: str | None = None,
) -> pl.DataFrame:
    """Fetch up to ``max_bars`` confirmed candles for ``inst``.

    Args:
        inst: FIGI, bare ticker, or ``TICKER@CLASS`` (e.g.
            ``SBER@MOEX``).
        bar: Pipeline bar name (``1m``, ``5m``, ``15m``, ``1H``, ``1D``).
        max_bars: Maximum number of bars to collect.
        cache_dir: Optional directory; the frame is cached as
            ``raw_<inst>_<bar>.parquet`` and extended on reruns.
        token: T-Invest token (defaults to ``T_INVEST_TOKEN``).

    Returns:
        Polars DataFrame sorted by ``ts`` ascending with columns
        ``ts, open, high, low, close, volume``.

    """
    spec = resolve_bar(bar)
    tok = token  # resolved inside api_post if None
    cache: Path | None = (
        Path(cache_dir) / f"raw_{inst}_{bar}.parquet" if cache_dir else None
    )
    cached_df: pl.DataFrame | None = None
    if cache is not None and cache.exists():
        cached_df = pl.read_parquet(cache)

    now_ms = int(time.time() * 1000)
    # align the request start to a bar boundary
    start_ms = ((now_ms - max_bars * spec.bar_ms) // spec.bar_ms) * spec.bar_ms
    chunk_ms = _CHUNK_CANDLES * spec.bar_ms

    if (
        cached_df is not None
        and cached_df.height
        and int(cached_df["ts"][-1]) >= now_ms - 3 * spec.bar_ms
    ):
        print(f"[{inst}] cache hit: {cache}")
        return cached_df.tail(max_bars)

    figi = resolve_instrument(
        inst,
        token=tok,
        cache_path=cache.parent / "figi_cache.json"
        if cache is not None
        else None,
    )

    candles: list[dict] = []
    cur = (
        start_ms
        if cached_df is None or not cached_df.height
        else max(start_ms, int(cached_df["ts"][-1]) + spec.bar_ms)
    )
    fetched_since_save = 0
    while cur < now_ms:
        page = _candles_page(
            figi, spec.interval, cur, min(cur + chunk_ms, now_ms), tok
        )
        candles.extend(page)
        fetched_since_save += len(page)
        cur += chunk_ms
        time.sleep(_PAGE_SLEEP)
        if fetched_since_save >= _CHECKPOINT_BARS and cache is not None:
            cached_df = _rows_to_df(candles, cached_df)
            candles = []
            fetched_since_save = 0
            cache.parent.mkdir(parents=True, exist_ok=True)
            cached_df.write_parquet(cache)

    df = _rows_to_df(candles, cached_df)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache)
    return df.tail(max_bars)
