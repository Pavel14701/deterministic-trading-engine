"""OKX candle source wrapped in the shared CandleSource interface."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import polars as pl

from marketdata.common import CandleSource, register
from okx.src.fetch import fetch_candles as _okx_fetch_candles


@register
class OkxSource(CandleSource):
    """Public OKX REST candle history (no API keys needed)."""

    name: ClassVar[str] = "okx"
    # Full pipeline-relevant OKX bar set (the API accepts these bar
    # strings directly); `bars_per_year` is derived from this map.
    BAR_MS: ClassVar[dict[str, int]] = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1H": 3_600_000,
        "2H": 7_200_000,
        "4H": 14_400_000,
        "1D": 86_400_000,
        "1W": 604_800_000,
    }
    MAX_HISTORY_DAYS: ClassVar[dict[str, int]] = {}  # effectively unlimited

    def fetch_candles(
        self,
        inst: str,
        bar: str = "1m",
        max_bars: int = 20_000,
        cache_dir: str | Path | None = None,
    ) -> pl.DataFrame:
        """Fetch OKX candles (delegates to :mod:`okx.src.fetch`)."""
        return _okx_fetch_candles(
            inst, bar=bar, max_bars=max_bars, cache_dir=cache_dir
        )
