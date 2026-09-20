"""Performance metrics on per-trade R sequences.

Extracted from the ranker head and the walk-forward protocol: every
consumer (replays, experiments, reports) reads the same definitions.
All inputs are net R per trade; chronological order matters where
documented.
"""
from __future__ import annotations

from typing import Any

import numpy as np


DAY_MS = 86_400_000


def trade_curve_stats(r_net: np.ndarray) -> dict[str, float]:
    """Risk profile of a trade sequence (net R per trade).

    Returns trade count, per-trade t-stat (mean / std * sqrt(n) - the
    significance of the mean UNDER AN INDEPENDENCE ASSUMPTION; pooled
    cross-asset or overlapping trades inflate it - do not read it as a
    Sharpe ratio, the per-trade Sharpe is ``mean / std`` ~0.3-0.6
    whenever the t-stat reads ~10+), max drawdown of the cumulative
    equity curve in R (the input MUST be in chronological order for
    the drawdown to be meaningful), and the profit factor (gross wins
    / gross losses).
    """
    r = np.asarray(r_net, dtype=np.float64)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {"n": 0, "t_stat": 0.0, "max_dd_r": 0.0, "profit_factor": 0.0}
    eq = np.cumsum(r)
    max_dd = float(np.max(np.maximum.accumulate(eq) - eq))
    std = float(r.std(ddof=1)) if r.size > 1 else 0.0
    t = float(r.mean() / std * np.sqrt(r.size)) if std > 0 else 0.0
    wins = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    pf = wins / losses if losses > 0 else float("inf")
    return {
        "n": int(r.size),
        "t_stat": t,
        "max_dd_r": max_dd,
        "profit_factor": pf,
    }


def per_trade_sharpe(r_net: np.ndarray) -> float:
    """Sharpe ratio on the per-trade R scale: ``mean / std`` (ddof=1).

    Dimensionless, NOT annualized.  For a healthy strategy this lands
    in the 0.1-0.6 band; a value near 1+ per trade is a red flag for a
    computation error.  Returns 0.0 for fewer than 2 finite trades or
    zero dispersion.
    """
    r = np.asarray(r_net, dtype=np.float64)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    std = float(r.std(ddof=1))
    return float(r.mean() / std) if std > 0 else 0.0


def bucketed_sharpe(
    r_net: np.ndarray,
    ts_ms: np.ndarray,
    bucket_days: int = 7,
) -> float:
    """Annualized Sharpe from calendar-bucketed R sums.

    The honest annualization for trade-R sequences: aggregate R per
    time bucket (default week), then
    ``mean_bucket / std_bucket * sqrt(buckets_per_year)``.  Bucketing
    absorbs intra-bucket overlap (one slot per asset) and cross-asset
    pooling, which otherwise inflate a naive ``sqrt(n)`` annualization
    by an order of magnitude.  Buckets with no trades contribute
    nothing (they are absent from the series, not zero) - document
    this when comparing strategies with different activity gaps.

    Returns 0.0 when fewer than 2 non-empty buckets or zero
    dispersion.
    """
    r = np.asarray(r_net, dtype=np.float64)
    ts = np.asarray(ts_ms, dtype=np.float64)
    ok = np.isfinite(r) & np.isfinite(ts)
    r, ts = r[ok], ts[ok]
    if r.size < 2:
        return 0.0
    bucket_ms = float(bucket_days * DAY_MS)
    idx = np.floor((ts - ts.min()) / bucket_ms).astype(np.int64)
    # bincount keeps interior empty buckets as 0.0 - genuine flat weeks
    sums = np.bincount(idx, weights=r)
    if sums.size < 2:
        return 0.0
    std = float(sums.std(ddof=1))
    if std <= 0:
        return 0.0
    per_year = 365.25 / bucket_days
    return float(sums.mean() / std * np.sqrt(per_year))


def pooled_stats(r: np.ndarray, ts: np.ndarray) -> dict[str, Any]:
    """Chronology-restored pooled trade stats (the common report row)."""
    order = np.argsort(ts, kind="stable")
    chrono = r[order]
    stats = trade_curve_stats(chrono)
    return {
        "mean": float(r.mean()),
        "n": int(r.size),
        "dd": stats["max_dd_r"],
        "t_stat_naive": stats["t_stat"],
        "sharpe_per_trade": per_trade_sharpe(chrono),
        "sharpe_ann_bucketed": bucketed_sharpe(chrono, ts),
    }
