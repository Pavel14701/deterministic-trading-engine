"""Pure helpers for the MTF dataset build (stage A.3/A.4).

Everything here is causal by construction and unit-testable:

- :func:`rolling_percentile` - percentile of the current value within
  its own trailing window (regime features without look-ahead);
- :func:`assign_splits` - chronological train/val/test assignment with
  an embargo of ``hold`` bars so no trade crosses a split boundary;
- :func:`limit_fill` - pessimistic maker-fill simulation (price must
  trade *through* the limit by a buffer before the order fills);
- :func:`nearest_zone_dists` - distance to the nearest known zone
  above/below a price (HTF context);
- :func:`sma` / :func:`sma_state` - simple moving average and the
  trend/slope state derived from it.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def sma(x: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    """Trailing simple moving average; NaN until ``n`` samples exist."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    csum = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1 :] = (csum[n:] - csum[:-n]) / n
    return out


def rolling_percentile(
    x: npt.NDArray[np.float64],
    window: int = 500,
) -> npt.NDArray[np.float64]:
    """Percentile (0..1) of ``x[i]`` within ``x[max(0, i - window) : i + 1]``.

    Causal: the comparison set ends at the current bar.  NaN inputs
    propagate as NaN.
    """
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        if not np.isfinite(x[i]):
            continue
        seg = x[max(0, i - window + 1) : i + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) == 0:
            continue
        out[i] = float(np.sum(seg <= x[i])) / len(seg)
    return out


def assign_splits(
    entry_idxs: npt.NDArray[np.int64],
    n_bars: int,
    hold: int,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
) -> list[str]:
    """Chronological train/val/test labels with a ``hold``-bar embargo.

    An entry is assigned to a segment only when its whole trade
    ``[entry_idx, entry_idx + hold]`` fits inside that segment's bar
    range; trades crossing a boundary get ``""`` (unused).  With
    ``n_bars`` bars the segments are ``[0, train_end)``,
    ``[train_end, val_end)``, ``[val_end, n_bars)`` where
    ``train_end = int(n_bars * train_frac)`` and
    ``val_end = int(n_bars * (train_frac + val_frac))``.
    """
    train_end = int(n_bars * train_frac)
    val_end = int(n_bars * (train_frac + val_frac))
    labels: list[str] = []
    for idx in entry_idxs:
        if idx + hold < train_end:
            labels.append("train")
        elif train_end + hold <= idx < val_end - hold:
            labels.append("val")
        elif val_end + hold <= idx < n_bars:
            labels.append("test")
        else:
            labels.append("")
    return labels


def limit_fill(
    side: str,
    limit_price: float,
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    atr: npt.NDArray[np.float64],
    start_idx: int,
    buf_atr: float = 0.1,
    max_wait: int = 5,
) -> int:
    """Return the bar index where a maker limit order fills, or ``-1``.

    Pessimistic: a long limit at ``p`` fills only when the bar's low
    trades through ``p - buf_atr * ATR``; a short at ``p`` when the
    high trades through ``p + buf_atr * ATR``.  The order lives for
    ``max_wait`` bars starting at ``start_idx``.
    """
    if not np.isfinite(limit_price):
        return -1
    end = min(start_idx + max_wait, len(high))
    for j in range(start_idx, end):
        buf = buf_atr * atr[j] if np.isfinite(atr[j]) else 0.0
        if side == "long":
            if low[j] <= limit_price - buf:
                return j
        elif high[j] >= limit_price + buf:
            return j
    return -1


def nearest_zone_dists(
    zones: list[tuple[float, float]],
    price: float,
) -> tuple[float, float]:
    """Distances from ``price`` to the nearest known zone edges.

    Args:
        zones: ``(zone_low, zone_high)`` pairs known at decision time.
        price: Reference price (the close at the entry bar).

    Returns:
        ``(dist_below, dist_above)`` in price units - distance down to
        the nearest zone top edge below the price and up to the nearest
        zone bottom edge above it; ``inf`` when no zone exists on that
        side.  A zone straddling the price contributes ``0.0`` to both.

    """
    below = np.inf
    above = np.inf
    for lo, hi in zones:
        if hi <= price:
            below = min(below, price - hi)
        elif lo >= price:
            above = min(above, lo - price)
        else:  # price inside the zone
            below = 0.0
            above = 0.0
    return below, above


def trend_state(
    close: npt.NDArray[np.float64],
    atr: npt.NDArray[np.float64],
    n: int = 50,
    slope_bars: int = 10,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64],
    npt.NDArray[np.int64]]:
    """Causal trend features from an SMA: z-distance, slope, sign.

    Returns ``(z, slope, sign)`` where ``z[i] = (close[i] - sma[i]) /
    atr[i]``, ``slope[i] = (sma[i] - sma[i - slope_bars]) / atr[i]``
    and ``sign[i]`` is ``+1/-1`` by the close-vs-SMA relation (0 while
    the SMA is undefined).
    """
    avg = sma(close, n)
    z = np.full(len(close), np.nan)
    slope = np.full(len(close), np.nan)
    sign = np.zeros(len(close), dtype=np.int64)
    for i in range(len(close)):
        if not np.isfinite(avg[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        z[i] = (close[i] - avg[i]) / atr[i]
        j = i - slope_bars
        if j >= 0 and np.isfinite(avg[j]):
            slope[i] = (avg[i] - avg[j]) / atr[i]
        sign[i] = 1 if close[i] >= avg[i] else -1
    return z, slope, sign
