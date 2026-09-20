"""Shared bar-DSL feed plumbing for event collectors.

``SeriesCache`` and ``make_bar_context`` wire the canonical OHLCV bar
frame into the ``dsl`` package: causal indicator series are
precomputed once (O(N) per parameter set) and every DSL evaluation is
bound to a bar index so ``name[k]`` resolves ``k`` bars back.
:mod:`engine.mfe_mae` (event discovery) and :mod:`engine.feature_spec`
(per-event feature matrices) both build on this, so every bar-level
DSL consumer shares one indicator implementation and one causality
contract.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from dsl import Context, InProcessProvider
from dsl.exceptions import ProviderError
from engine.features import compute_atr


__all__ = ("BAR_DSL_MANIFEST", "SeriesCache", "make_bar_context")

BAR_COLUMNS = ("open", "high", "low", "close", "volume")
COMPUTED_INDICATORS = ("sma", "ema", "rsi", "atr")
BAR_DSL_MANIFEST: dict[str, Any] = {
    "indicators": {
        **{name: {"attributes": []} for name in BAR_COLUMNS},
        **{
            name: {
                "attributes": ["value"],
                "parameters": {"period": {"type": "float", "default": 14.0}},
            }
            for name in COMPUTED_INDICATORS
        },
    }
}


class SeriesCache:
    """Lazily precomputed causal indicator series for one DataFrame.

    All series are causal, so the value at bar ``j`` depends only on
    bars ``<= j``; serving ``series[i - offset]`` for a context bound
    to bar ``i`` is exactly prefix-correct.
    """

    def __init__(self, df: pl.DataFrame) -> None:
        missing = [
            c for c in ("open", "high", "low", "close") if c not in df.columns
        ]
        if missing:
            raise ValueError(f"df missing required columns: {missing}")
        self.df = df
        self.arrays: dict[str, np.ndarray] = {
            "open": df["open"].to_numpy().astype(np.float64),
            "high": df["high"].to_numpy().astype(np.float64),
            "low": df["low"].to_numpy().astype(np.float64),
            "close": df["close"].to_numpy().astype(np.float64),
        }
        if "volume" in df.columns:
            self.arrays["volume"] = df["volume"].to_numpy().astype(np.float64)
        self.computed: dict[tuple[str, int], np.ndarray] = {}

    def get(self, indicator: str, params: dict[str, Any]) -> np.ndarray:
        """Return the precomputed (or cached) series for a request."""
        if indicator in self.arrays:
            return self.arrays[indicator]
        period = int(float(params.get("period", 14)))
        key = (indicator, period)
        if key not in self.computed:
            self.computed[key] = self._compute(indicator, period)
        return self.computed[key]

    def _compute(self, indicator: str, period: int) -> np.ndarray:
        if period < 1:
            raise ProviderError(f"period must be >= 1, got {period}")
        close = self.arrays["close"]
        if indicator == "atr":
            return np.asarray(
                compute_atr(self.df, period=period), dtype=np.float64
            )
        if indicator == "sma":
            # expanding warm-up for t < period, then right-aligned MA
            csum = np.cumsum(close)
            out = np.empty_like(close)
            for t in range(len(close)):
                if t < period:
                    out[t] = csum[t] / (t + 1)
                else:
                    out[t] = (csum[t] - csum[t - period]) / period
            return out
        if indicator == "ema":
            alpha = 2.0 / (period + 1.0)
            out = np.empty_like(close)
            out[0] = close[0]
            for t in range(1, len(close)):
                out[t] = alpha * close[t] + (1.0 - alpha) * out[t - 1]
            return out
        if indicator == "rsi":
            return self._rsi(close, period)
        raise ProviderError(f"unknown computed indicator {indicator!r}")

    @staticmethod
    def _rsi(close: np.ndarray, period: int) -> np.ndarray:
        """Wilder RSI with an expanding seed (causal, no NaN warm-up)."""
        n = len(close)
        out = np.full(n, 50.0)
        if n < 2:
            return out
        diff = np.diff(close)
        gain = np.where(diff > 0, diff, 0.0)
        loss = np.where(diff < 0, -diff, 0.0)
        cg, cl = np.cumsum(gain), np.cumsum(loss)
        avg_g = avg_l = 0.0
        for t in range(1, n):
            k = t - 1  # number of diffs consumed so far
            if k < period:
                avg_g = cg[k] / (k + 1)
                avg_l = cl[k] / (k + 1)
            else:
                avg_g = (avg_g * (period - 1) + gain[k]) / period
                avg_l = (avg_l * (period - 1) + loss[k]) / period
            out[t] = (
                100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
            )
        return out


def make_bar_context(cache: SeriesCache, bar_idx: int) -> Context:
    """Build a DSL ``Context`` bound to bar ``bar_idx``.

    ``name[k]`` resolves to the value at bar ``bar_idx - k``; a
    reference before the series start yields NaN (comparisons against
    it are False, so expressions stay silent during warm-up) - an
    expression can therefore never read the future.
    """
    n = cache.df.height

    def resolver(
        indicator: str,
        params: dict[str, Any],
        attributes: list[str],
        offset: int,
    ) -> float:
        if attributes and attributes != ["value"]:
            raise ProviderError(
                f"unsupported attributes {attributes!r} "
                f"for indicator {indicator!r}"
            )
        if indicator == "volume" and "volume" not in cache.arrays:
            raise ProviderError(
                "column 'volume' not present in the bar DataFrame"
            )
        j = bar_idx - int(offset)
        if j < 0:
            # warm-up: history before the series start is undefined;
            # NaN makes comparisons False so the expression stays
            # silent (config errors like unknown indicators still raise)
            return float("nan")
        if j >= n:  # defensive; offsets are non-negative
            raise ProviderError(f"{indicator}[{offset}] out of range")
        return float(cache.get(indicator, params)[j])

    return Context([InProcessProvider(BAR_DSL_MANIFEST, resolver)])
