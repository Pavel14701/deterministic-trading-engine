"""Timeframe mapping between pipeline bar names and T-Invest intervals.

Also carries the API's history-depth limits per interval: T-Invest
serves only a recent window for intraday intervals (roughly a day of
1m, a week of 5m, a month of 15m, a year of 1H and a decade of 1D),
which the pipeline checks before fetching.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TfSpec:
    """Pipeline bar name mapped onto T-Invest details."""

    interval: str  # T-Invest CandleInterval enum name
    bar_ms: int  # bar duration in milliseconds
    max_history_days: int  # approximate API history depth


TFS: dict[str, TfSpec] = {
    "1m": TfSpec("INTERVAL_1_MIN", 60_000, 1),
    "5m": TfSpec("INTERVAL_5_MIN", 300_000, 7),
    "15m": TfSpec("INTERVAL_15_MIN", 900_000, 31),
    "1H": TfSpec("INTERVAL_HOUR", 3_600_000, 365),
    "1D": TfSpec("INTERVAL_DAY", 86_400_000, 3_650),
}


def resolve_bar(bar: str) -> TfSpec:
    """Return the T-Invest spec for a pipeline bar name.

    Args:
        bar: Pipeline bar name (``1m``, ``5m``, ``15m``, ``1H``, ``1D``).

    Returns:
        The corresponding :class:`TfSpec`.

    Raises:
        ValueError: For bar names the T-Invest API cannot serve.

    """
    spec = TFS.get(bar)
    if spec is None:
        known = ", ".join(sorted(TFS))
        raise ValueError(
            f"T-Invest: unsupported bar {bar!r} (supported: {known})"
        )
    return spec
