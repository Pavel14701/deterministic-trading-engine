"""Shared candle-source abstraction for dataset pipelines.

Every venue adapter (OKX, T-Invest, ...) exposes the same interface:
``fetch_candles(inst, bar, max_bars, cache_dir)`` returning the
canonical OHLCV frame (``ts`` in epoch ms int64, OHLCV float64, sorted
ascending, only confirmed bars) plus a ``BAR_MS`` map and history-depth
limits so the pipeline can validate the request up front.
"""

from __future__ import annotations

import abc

from pathlib import Path
from typing import ClassVar

import polars as pl


MS_PER_YEAR = 365.25 * 24 * 3600 * 1000


class CandleSource(abc.ABC):
    """Abstract candle history provider.

    Class attributes each concrete source must define:

    - ``name``: registry key used by ``--source``.
    - ``BAR_MS``: pipeline bar name -> bar duration in milliseconds.
      This is the single source of truth for bar support: any bar in
      this map can be requested (``BARS_PER_YEAR`` is derived from it).
    - ``MAX_HISTORY_DAYS``: bar name -> approximate API history depth
      in days; bars missing here are assumed unlimited.
    """

    name: ClassVar[str]
    BAR_MS: ClassVar[dict[str, int]]
    MAX_HISTORY_DAYS: ClassVar[dict[str, int]]

    @abc.abstractmethod
    def fetch_candles(
        self,
        inst: str,
        bar: str = "1m",
        max_bars: int = 20_000,
        cache_dir: str | Path | None = None,
    ) -> pl.DataFrame:
        """Return up to ``max_bars`` confirmed candles for ``inst``."""

    def supports_bar(self, bar: str) -> bool:
        """Return whether this source can serve ``bar``.

        Args:
            bar: Pipeline bar name.

        Returns:
            ``True`` when the bar is present in :attr:`BAR_MS`.

        """
        return bar in self.BAR_MS

    def bars_per_year(self, bar: str) -> float:
        """Return the approximate number of ``bar`` bars in a year.

        Derived from :attr:`BAR_MS` so adding a bar to the map never
        requires updating a second table.

        Args:
            bar: Pipeline bar name.

        Returns:
            Bars per (365.25-day) year as a float.

        Raises:
            ValueError: When the source cannot serve ``bar``.

        """
        if not self.supports_bar(bar):
            raise ValueError(
                f"{self.name}: unsupported bar {bar!r} "
                f"(supported: {sorted(self.BAR_MS)})"
            )
        return MS_PER_YEAR / self.BAR_MS[bar]

    def check_depth(self, bar: str, years: float) -> None:
        """Validate the requested history depth against API limits.

        Args:
            bar: Pipeline bar name.
            years: Requested history depth in years.

        Raises:
            ValueError: When the source cannot serve that depth for
                this bar size.

        """
        limit_days = self.MAX_HISTORY_DAYS.get(bar)
        if limit_days is None:
            return
        requested_days = years * 365.25
        if round(requested_days) > limit_days:
            raise ValueError(
                f"{self.name}: {bar} history is limited to ~{limit_days} "
                f"days by the API, requested {requested_days:.0f} days. "
                "Reduce --years for this bar or drop it from --bars."
            )

    def validate_bars(self, bars: list[str], years: float) -> None:
        """Validate a full ``--bars`` request against this source.

        Checks both bar support and history depth, so mixed-source
        datasets fail fast with a clear message instead of raising a
        ``KeyError`` deep inside the fetch loop.

        Args:
            bars: Requested pipeline bar names (first = base).
            years: Requested history depth in years.

        Raises:
            ValueError: When any bar is unsupported or too deep.

        """
        for bar in bars:
            if not self.supports_bar(bar):
                raise ValueError(
                    f"source {self.name!r} does not support bar {bar!r} "
                    f"(supported: {sorted(self.BAR_MS)})"
                )
            self.check_depth(bar, years)


_REGISTRY: dict[str, type[CandleSource]] = {}


def register(cls: type[CandleSource]) -> type[CandleSource]:
    """Class decorator adding a candle source to the registry."""
    _REGISTRY[cls.name] = cls
    return cls


def get_source(name: str) -> CandleSource:
    """Return an instantiated candle source by registry key.

    Args:
        name: Source name (``okx``, ``tinvest``).

    Returns:
        A fresh :class:`CandleSource` instance.

    Raises:
        ValueError: For unknown source names.

    """
    if name not in _REGISTRY:
        known = ", ".join(known_sources())
        raise ValueError(f"unknown data source {name!r} (known: {known})")
    return _REGISTRY[name]()


def known_sources() -> list[str]:
    """Return the registered source names (sorted).

    Returns:
        Sorted list of registry keys, e.g. ``["okx", "tinvest"]``.

    """
    return sorted(_REGISTRY)
