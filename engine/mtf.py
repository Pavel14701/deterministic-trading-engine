"""Multi-timeframe utilities: resample 1m candles to higher timeframes.

Stage A.1 of the MTF plan: the okx21 cache stores raw 1m bars only.
This module derives 5m/15m/1h/4h/1d/1w bars deterministically and
attaches ``known_ts`` so downstream consumers can enforce causality:
an HTF bar that *starts* at ``ts`` only becomes known at ``known_ts``
(its close).  Nothing here looks into the future - aggregation is a
pure function of already-confirmed 1m bars.

"""

from __future__ import annotations

from typing import cast

import polars as pl


#: Supported target bars and their durations in milliseconds.  Keys
#: mirror the naming used in the MTF plan (lowercase units).
BAR_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}

#: polars ``every`` strings accepted by ``group_by_dynamic``.
_EVERY: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
}

_BASE_MS = BAR_MS["1m"]


def _validate(df: pl.DataFrame) -> None:
    """Raise ``ValueError`` unless ``df`` is a canonical OHLCV frame."""
    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        msg = f"missing columns: {sorted(missing)}"
        raise ValueError(msg)
    if df["ts"].dtype != pl.Int64:
        msg = f"ts must be Int64 epoch ms, got {df['ts'].dtype}"
        raise ValueError(msg)
    if not df["ts"].is_sorted():
        msg = "ts must be sorted ascending"
        raise ValueError(msg)


def bar_duration_ms(target_bar: str) -> int:
    """Return the duration of ``target_bar`` in milliseconds."""
    if target_bar not in BAR_MS:
        msg = (
            f"unsupported bar {target_bar!r}, expected one of {sorted(BAR_MS)}"
        )
        raise ValueError(msg)
    return BAR_MS[target_bar]


def resample_ohlcv(df: pl.DataFrame, target_bar: str) -> pl.DataFrame:
    """Resample a canonical 1m OHLCV frame to ``target_bar``.

    A 1m bar with ``ts = t`` covers ``[t, t + 60_000)``.  A target bar
    starting at ``s`` is emitted only when every source minute it needs
    is present, i.e. when ``s + dur <= max(ts) + 60_000``; the trailing
    partial bar is dropped.  The result carries ``n_bars`` (source bars
    aggregated) and ``known_ts = ts + dur`` (the moment the target bar
    is confirmed and may be consumed causally).

    Args:
        df: Canonical frame (``ts`` Int64 epoch ms, sorted ascending).
        target_bar: One of :data:`BAR_MS` keys (e.g. ``"1h"``).

    Returns:
        Frame with columns ``ts, open, high, low, close, volume,
        n_bars, known_ts``.

    """
    _validate(df)
    if target_bar not in _EVERY:
        msg = (
            f"unsupported target bar {target_bar!r}, "
            f"expected one of {sorted(_EVERY)}"
        )
        raise ValueError(msg)
    dur = BAR_MS[target_bar]
    last_known = int(cast("float", df["ts"].max())) + _BASE_MS
    out = (
        df.with_columns(pl.from_epoch("ts", time_unit="ms").alias("_dt"))
        .group_by_dynamic(
            "_dt", every=_EVERY[target_bar], closed="left", label="left"
        )
        .agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.len().alias("n_bars"),
        )
        .with_columns(pl.col("_dt").dt.epoch("ms").alias("ts"))
        .drop("_dt")
        .filter(pl.col("ts") + dur <= last_known)
        .with_columns((pl.col("ts") + dur).alias("known_ts"))
    )
    return out.select(
        "ts", "open", "high", "low", "close", "volume", "n_bars", "known_ts"
    )


def asof_rows(htf: pl.DataFrame, ts: int) -> pl.DataFrame:
    """Return HTF rows that are causally known at ``ts``.

    Args:
        htf: Frame produced by :func:`resample_ohlcv`.
        ts: Base-TF timestamp (Int64 epoch ms) of the decision moment.

    Returns:
        Rows with ``known_ts <= ts`` - everything an entry decision at
        ``ts`` is allowed to see.

    """
    return htf.filter(pl.col("known_ts") <= ts)
