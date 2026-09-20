"""FeatureProvider: wire aligned feature columns into the bar DSL.

:func:`engine.features.mtf.asof_join_features` and other collectors produce
DataFrames whose rows are *aligned 1:1 with the bar frame*.  This
module exposes such columns to DSL expressions (via the
``context_factory`` hook of :func:`engine.features.spec.collect_features`
and :func:`engine.features.events.collect_mfe_mae`) under strict causal
guards:

1. ``col[k]`` resolves to row ``bar_idx - k`` of the extra frame -
   the same offset contract as bar indicators; negative offsets are
   impossible by DSL grammar and rejected defensively.
2. Reads before row 0 yield NaN (warm-up, never an error, never a
   future value).
3. Reads past the frame end raise (defensive; unreachable for
   in-range event indices).
4. Row alignment is enforced once on the first call: the extra frame
   must have the same height as the bar frame and, when both carry
   ``ts``, identical timestamps - a misaligned join would silently
   corrupt every feature, so it fails fast instead.
5. Name collisions with bar-DSL indicators (``close``, ``sma``, ...)
   are rejected - ambiguity must be a config error, not a silent
   override.

Causality of the *column values themselves* is the producer's
contract (e.g. ``asof_join_features`` guarantees ``known_ts <= ts``);
this module guarantees only offset-causal access to them.

Usage::

    joined = asof_join_features(bars, htf, ["close"], prefix="htf_")
    factory = HybridContextFactory(joined, ["htf_close"])
    feats = collect_features(
        bars,
        FeatureSpec(
            features=(
                FeatureDef("htf_gap", expr="close - htf_close"),
                FeatureDef("above_htf", expr="close > htf_close"),
            )
        ),
        event_idx,
        context_factory=factory,
    )
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import polars as pl

from dsl import Context, InProcessProvider
from dsl.exceptions import ProviderError
from engine.features.dsl_feed import (
    BAR_DSL_MANIFEST,
    SeriesCache,
    make_bar_provider,
)


__all__ = ("ColumnProvider", "HybridContextFactory")


class ColumnProvider:
    """Expose aligned DataFrame columns as causal DSL indicators.

    Args:
        df: Extra frame row-aligned with the bar frame.
        cols: Column names to expose; must be valid identifiers and
            must not collide with bar-DSL indicator names.

    Raises:
        ValueError: on empty/duplicate/missing/non-identifier ``cols``
            or on collisions with bar-DSL indicator names.

    """

    def __init__(self, df: pl.DataFrame, cols: Sequence[str]) -> None:
        if not cols:
            raise ValueError("cols must not be empty")
        if len(set(cols)) != len(cols):
            raise ValueError(f"duplicate cols: {sorted(cols)}")
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"df missing columns: {missing}")
        bad = [c for c in cols if not c.isidentifier()]
        if bad:
            raise ValueError(f"cols must be identifiers, got {bad}")
        collide = sorted(
            c for c in cols if c in BAR_DSL_MANIFEST["indicators"]
        )
        if collide:
            raise ValueError(
                "cols collide with bar-DSL indicator names; rename via "
                f"prefix: {collide}"
            )
        self._arrays: dict[str, np.ndarray] = {
            c: df[c].to_numpy().astype(np.float64) for c in cols
        }
        self._extra = df
        self._manifest: dict[str, Any] = {
            "indicators": {c: {"attributes": []} for c in cols}
        }

    @property
    def manifest(self) -> dict[str, Any]:
        """Provider manifest (one attribute-less indicator per col)."""
        return self._manifest

    @property
    def height(self) -> int:
        """Row count of the wrapped frame (alignment reference)."""
        return self._extra.height

    @property
    def ts(self) -> np.ndarray | None:
        """``ts`` column of the wrapped frame if present, else None."""
        if "ts" not in self._extra.columns:
            return None
        return self._extra["ts"].to_numpy().astype(np.int64)

    def resolver(self, bar_idx: int):
        """Return a resolver closure bound to ``bar_idx``."""

        def resolve(
            indicator: str,
            params: dict[str, Any],
            attributes: list[str],
            offset: int,
        ) -> float:
            arr = self._arrays.get(indicator)
            if arr is None:
                raise ProviderError(f"unknown column {indicator!r}")
            if attributes:
                raise ProviderError(
                    f"unsupported attributes {attributes!r} "
                    f"for column {indicator!r}"
                )
            if offset < 0:  # defensive; DSL offsets are non-negative
                raise ProviderError(
                    f"negative offset {offset} for {indicator!r}"
                )
            j = bar_idx - int(offset)
            if j < 0:
                # warm-up: undefined history is NaN, never a future value
                return float("nan")
            if j >= self._extra.height:  # defensive
                raise ProviderError(f"{indicator}[{offset}] out of range")
            return float(arr[j])

        return resolve


class HybridContextFactory:
    """``(cache, bar_idx) -> Context``: bar DSL + aligned columns.

    Combines :func:`engine.features.dsl_feed.make_bar_provider` with a
    :class:`ColumnProvider`, enforcing row alignment once on the
    first call (fail fast before any feature is computed).

    Args:
        extra: Frame row-aligned with the bar frame (e.g. the output
            of :func:`engine.features.mtf.asof_join_features`).
        cols: Column names to expose to DSL expressions.

    """

    def __init__(self, extra: pl.DataFrame, cols: Sequence[str]) -> None:
        """Precompute column arrays and validate names eagerly."""
        self._provider = ColumnProvider(extra, cols)
        self._extra = extra
        self._checked = False

    def __call__(self, cache: SeriesCache, bar_idx: int) -> Context:
        """Build a combined bar+columns Context bound to ``bar_idx``."""
        if not self._checked:
            self._check_alignment(cache)
            self._checked = True
        return Context(
            [
                make_bar_provider(cache, bar_idx),
                InProcessProvider(
                    self._provider.manifest,
                    self._provider.resolver(bar_idx),
                ),
            ]
        )

    def _check_alignment(self, cache: SeriesCache) -> None:
        if cache.df.height != self._provider.height:
            raise ValueError(
                f"bar frame height {cache.df.height} != extra frame "
                f"height {self._provider.height}; rows must be 1:1 "
                "aligned (e.g. via asof_join_features on the same bars)"
            )
        bar_ts = (
            cache.df["ts"].to_numpy().astype(np.int64)
            if "ts" in cache.df.columns
            else None
        )
        extra_ts = self._provider.ts
        if (
            bar_ts is not None
            and extra_ts is not None
            and not np.array_equal(bar_ts, extra_ts)
        ):
            raise ValueError(
                "bar frame and extra frame 'ts' columns differ - rows "
                "are not aligned; refusing to build features on a "
                "misaligned join"
            )
