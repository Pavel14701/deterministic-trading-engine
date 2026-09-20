"""Multi-timeframe utilities: resample 1m candles to higher timeframes.

Stage A.1 of the MTF plan: the okx21 cache stores raw 1m bars only.
This module derives 5m/15m/1h/4h/1d/1w bars deterministically and
attaches ``known_ts`` so downstream consumers can enforce causality:
an HTF bar that *starts* at ``ts`` only becomes known at ``known_ts``
(its close).  Nothing here looks into the future - aggregation is a
pure function of already-confirmed 1m bars.

"""

from __future__ import annotations

from collections.abc import Sequence
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


def asof_join_features(
    base: pl.DataFrame,
    htf: pl.DataFrame,
    cols: Sequence[str],
    prefix: str = "htf_",
    age_col: str | None = None,
) -> pl.DataFrame:
    """Attach HTF columns to a base frame as-of each base ``ts``.

    A base row at ``ts`` sees only HTF bars with ``known_ts <= ts`` -
    i.e. fully closed bars, the same causality rule as
    :func:`asof_rows`.  Base rows before the first known HTF bar get
    nulls; feature values never look into the future by construction.

    Args:
        base: Base-TF frame with an Int64 epoch-ms ``ts`` column.
        htf: Frame produced by :func:`resample_ohlcv`.
        cols: HTF column names to attach.
        prefix: Name prefix for the attached columns.
        age_col: Optional name for an Int64 column holding
            ``ts - known_ts`` (how stale the attached HTF bar is; a
            legitimate input - the staleness itself is known at
            decision time).

    Staleness policy: the adapter NEVER filters or masks stale HTF
    bars - an old but closed bar is still causal information, and
    dropping it here would silently change feature semantics.  If a
    family needs a freshness cap, express it at the FeatureSpec /
    event-filtering level (e.g. a ``{prefix}age_ms < cap`` flag via
    :mod:`engine.features.spec`, or drop events where the age column
    exceeds the cap) so the decision is explicit and testable.

    Returns:
        ``base`` sorted by ``ts`` with the attached columns.

    Raises:
        ValueError: on a missing ``ts``/``known_ts`` column, missing
            HTF columns, empty/duplicate ``cols``, or name collisions
            with existing base columns.

    """
    if "ts" not in base.columns:
        raise ValueError("base missing required column: ts")
    if not cols:
        raise ValueError("cols must not be empty")
    if len(set(cols)) != len(cols):
        raise ValueError(f"duplicate cols: {sorted(cols)}")
    missing = [c for c in cols if c not in htf.columns]
    if missing:
        raise ValueError(f"htf missing columns: {missing}")
    if "known_ts" not in htf.columns:
        raise ValueError("htf missing required column: known_ts")
    added = [f"{prefix}{c}" for c in cols]
    if age_col is not None:
        added.append(age_col)
    collide = [c for c in added if c in base.columns]
    if collide:
        raise ValueError(f"attached columns already in base: {collide}")

    right = htf.select(
        [pl.col("known_ts").alias("_known_ts")]
        + [pl.col(c).alias(f"{prefix}{c}") for c in cols]
    ).sort("_known_ts")
    out = base.sort("ts").join_asof(
        right, left_on="ts", right_on="_known_ts", strategy="backward"
    )
    if age_col is not None:
        out = out.with_columns(
            (pl.col("ts") - pl.col("_known_ts")).alias(age_col)
        )
    return out.drop("_known_ts")
