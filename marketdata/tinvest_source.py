"""T-Invest candle source wrapped in the shared CandleSource interface."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import polars as pl

from marketdata.common import CandleSource, register
from tinvest.src.fetch import fetch_candles as _ti_fetch_candles
from tinvest.src.mapping import TFS


@register
class TInvestSource(CandleSource):
    """T-Invest (Tinkoff Invest API) candle history via REST."""

    name: ClassVar[str] = "tinvest"
    BAR_MS: ClassVar[dict[str, int]] = {k: v.bar_ms for k, v in TFS.items()}
    # Approximate API history windows per interval (days).  The API
    # serves intraday history only for a recent period.
    MAX_HISTORY_DAYS: ClassVar[dict[str, int]] = {
        k: v.max_history_days for k, v in TFS.items()
    }

    def fetch_candles(
        self,
        inst: str,
        bar: str = "1m",
        max_bars: int = 20_000,
        cache_dir: str | Path | None = None,
    ) -> pl.DataFrame:
        """Fetch T-Invest candles (delegates to :mod:`tinvest.src.fetch`)."""
        return _ti_fetch_candles(
            inst, bar=bar, max_bars=max_bars, cache_dir=cache_dir
        )
