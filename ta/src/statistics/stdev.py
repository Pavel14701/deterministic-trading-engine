"""Rolling standard deviation (STDEV) for financial time series.

This module provides Numba-accelerated and TA-Lib implementations of
rolling standard deviation, with unified interface for numpy arrays
and Polars Series/DataFrames.

Functions:
    stdev_numba: Numba-accelerated rolling standard deviation.
    stdev_talib: TA-Lib-based rolling standard deviation (ddof=0).
    stdev_ind: Universal rolling standard deviation (numpy or Polars Series).
    stdev_polars: Rolling standard deviation of a DataFrame column,
    returned as a Polars Series.
    stdev_polars_multi: Add rolling standard deviation columns
    for multiple columns.

Backend note: TA-Lib's STDDEV always uses ddof=0 (population) and has
no ddof parameter.  :func:`stdev_ind` therefore routes to TA-Lib only
when ``ddof == 0``; for any other ``ddof`` the Numba implementation is
used so that results honour ``ddof`` on every backend.

The core algorithm is implemented in Numba for high performance.
"""

from typing import Literal

import numpy as np
import polars as pl

from numba import njit

from .._array_ops import _apply_offset_fillna
from ..external import talib, talib_available


@njit("float64[:](float64[:], int64, int64)", fastmath=False, cache=True)
def _stdev_numba_core_online(
    close: np.ndarray, length: int, ddof: int
) -> np.ndarray:
    """Online (one-pass) rolling standard deviation.

    This is a naive running-sum/sum-of-squares scheme, NOT Welford's
    algorithm; it gives O(1) updates per element at the cost of
    possible precision loss through cancellation (see below).
    To keep IEEE 754 corner-case semantics the sums are resynchronised
    from scratch whenever a non-finite value enters the window, so a
    single NaN/inf poisons only the windows that contain it.  Note that
    large-magnitude inputs can still lose precision through cancellation
    in the sum of squares; use the 'two_pass' algorithm when exactness
    matters.
    """
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < length:
        return out
    sum_x = 0.0
    sum_x2 = 0.0
    for i in range(length):
        val = close[i]
        sum_x += val
        sum_x2 += val * val
    mean = sum_x / length
    variance = (sum_x2 - 2 * mean * sum_x + length * mean * mean) / (
        length - ddof
    )
    out[length - 1] = np.sqrt(variance) if variance >= 0 else np.nan
    for i in range(length, n):
        new_val = close[i]
        old_val = close[i - length]
        if (
            np.isfinite(new_val)
            and np.isfinite(old_val)
            and np.isfinite(sum_x)
            and np.isfinite(sum_x2)
        ):
            sum_x += new_val - old_val
            sum_x2 += new_val * new_val - old_val * old_val
        else:
            # Resynchronise: recompute sums from scratch for the current
            # window so a NaN/inf affects only the windows containing it.
            sum_x = 0.0
            sum_x2 = 0.0
            for j in range(i - length + 1, i + 1):
                val = close[j]
                sum_x += val
                sum_x2 += val * val
        mean = sum_x / length
        variance = (sum_x2 - 2 * mean * sum_x + length * mean * mean) / (
            length - ddof
        )
        out[i] = np.sqrt(variance) if variance >= 0 else np.nan
    return out


@njit("float64[:](float64[:], int64, int64)", fastmath=False, cache=True)
def _stdev_numba_core_twopass(
    close: np.ndarray, length: int, ddof: int
) -> np.ndarray:
    """Two-pass rolling standard deviation.

    Computes the mean first, then the variance from the summed squared
    deviations.  Slower but strictly IEEE 754 compliant: no running-sum
    drift on large-magnitude inputs, and a NaN/inf propagates only to the
    windows that contain it.
    """
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < length:
        return out
    for i in range(length - 1, n):
        # Compute mean
        sum_x = 0.0
        for j in range(i - length + 1, i + 1):
            sum_x += close[j]
        mean = sum_x / length
        # Compute variance
        sum_sq = 0.0
        for j in range(i - length + 1, i + 1):
            diff = close[j] - mean
            sum_sq += diff * diff
        variance = sum_sq / (length - ddof)
        out[i] = np.sqrt(variance) if variance >= 0 else np.nan
    return out


def _stdev_numba_core(
    close: np.ndarray,
    length: int,
    ddof: int,
    algorithm: Literal["online", "two_pass"] = "online",
) -> np.ndarray:
    """Dispatch to the appropriate Numba core function."""
    if algorithm == "online":
        return _stdev_numba_core_online(close, length, ddof)
    else:
        return _stdev_numba_core_twopass(close, length, ddof)


def stdev_numba(
    close: np.ndarray,
    length: int = 30,
    ddof: int = 1,
    offset: int = 0,
    fillna: float | None = None,
    algorithm: Literal["online", "two_pass"] = "online",
) -> np.ndarray:
    """Numba-accelerated rolling standard deviation.

    Parameters
    ----------
    close : np.ndarray
        1D float64 array of close prices.
    length : int, default 30
        Window size.
    ddof : int, default 1
        Delta Degrees of Freedom (1 for sample std, 0 for population).
        Must satisfy 0 <= ddof < length.
    offset : int, default 0
        Shift applied to the output array. Positive = forward shift.
    fillna : float or None, default None
        Value to fill positions that become NaN due to offset.
    algorithm : {'online', 'two_pass'}, default 'online'
        - 'online': one-pass algorithm (fast, may have small errors).
        - 'two_pass': two-pass algorithm (slower, more accurate).

    Returns
    -------
    np.ndarray
        Float64 array of rolling standard deviations, shifted and NaN-filled.

    """
    close = np.asarray(close, dtype=np.float64, copy=False)
    if length < 1:
        raise ValueError("length must be >= 1")
    if ddof < 0 or ddof >= length:
        raise ValueError("ddof must satisfy 0 <= ddof < length")
    if not close.flags.writeable:
        close = close.copy()
    if not close.flags.c_contiguous:
        close = np.ascontiguousarray(close)
    result = _stdev_numba_core(close, length, ddof, algorithm)
    return _apply_offset_fillna(result, offset, fillna)


def stdev_talib(
    close: np.ndarray,
    length: int = 30,
    offset: int = 0,
    fillna: float | None = None,
) -> np.ndarray:
    """TA-Lib-based rolling standard deviation (ddof=0)."""
    if not talib_available:
        raise ImportError("TA-Lib is not available")
    close = np.asarray(close, dtype=np.float64, copy=False)
    if not close.flags.c_contiguous:
        close = np.ascontiguousarray(close)
    result = talib.STDDEV(close, timeperiod=length)
    return _apply_offset_fillna(result, offset, fillna)


def stdev_ind(
    close: np.ndarray | pl.Series,
    length: int = 30,
    ddof: int = 1,
    offset: int = 0,
    fillna: float | None = None,
    use_talib: bool = True,
    algorithm: Literal["online", "two_pass"] = "online",
) -> np.ndarray:
    """Universal rolling standard deviation (numpy array or Polars Series).

    Parameters
    ----------
    close : np.ndarray or pl.Series
        1D array or Polars Series of close prices.
    length : int, default 30
        Window size.
    ddof : int, default 1
        Delta Degrees of Freedom (1 for sample, 0 for population).
    offset : int, default 0
        Shift applied to the output array.
    fillna : float or None, default None
        Value to fill NaN positions after offset.
    use_talib : bool, default True
        If True and TA-Lib is available, TA-Lib is used -- but ONLY when
        ``ddof == 0``: TA-Lib's STDDEV always computes the population
        standard deviation and has no ddof parameter.  Whenever
        ``ddof != 0`` the Numba implementation is used instead, so the
        returned values always honour ``ddof``.
    algorithm : {'online', 'two_pass'}, default 'online'
        Only used when the Numba implementation runs (use_talib=False,
        TA-Lib unavailable, or ddof != 0). See stdev_numba.

    Returns
    -------
    np.ndarray
        Float64 array of rolling standard deviations.

    """
    if isinstance(close, pl.Series):
        close = close.to_numpy()
    if use_talib and talib_available and ddof == 0:
        return stdev_talib(close, length, offset, fillna)
    return stdev_numba(close, length, ddof, offset, fillna, algorithm)


def stdev_polars(
    df: pl.DataFrame,
    close_col: str = "close",
    length: int = 30,
    ddof: int = 1,
    offset: int = 0,
    fillna: float | None = None,
    use_talib: bool = False,
    algorithm: Literal["online", "two_pass"] = "online",
    output_col: str | None = None,
) -> pl.Series:
    """Compute the rolling standard deviation of a DataFrame column.

    Returns a :class:`pl.Series` named ``output_col`` (or
    ``f"STDEV_{length}"``).  The input DataFrame is not modified and
    is NOT returned -- use ``df.with_columns(stdev_polars(...))`` or
    :func:`stdev_polars_multi` to attach the column to a DataFrame.

    ``use_talib`` defaults to False, matching
    :func:`stdev_polars_multi` and the default ``ddof=1`` (which the
    TA-Lib backend cannot compute; see :func:`stdev_ind`).
    """
    close = df[close_col].to_numpy()
    result = stdev_ind(
        close,
        length=length,
        ddof=ddof,
        offset=offset,
        fillna=fillna,
        use_talib=use_talib,
        algorithm=algorithm,
    )
    out_name = output_col or f"STDEV_{length}"
    return pl.Series(out_name, result)


def stdev_polars_multi(
    df: pl.DataFrame,
    columns: list[str],
    length: int = 30,
    ddof: int = 1,
    offset: int = 0,
    fillna: float | None = None,
    suffix: str = "_stdev",
    use_talib: bool = False,
    algorithm: Literal["online", "two_pass"] = "online",
) -> pl.DataFrame:
    """Add rolling standard deviation columns for multiple columns."""
    for col in columns:
        arr = df[col].to_numpy()
        result = stdev_ind(
            arr,
            length=length,
            ddof=ddof,
            offset=offset,
            fillna=fillna,
            use_talib=use_talib,
            algorithm=algorithm,
        )
        df = df.with_columns(pl.Series(f"{col}{suffix}", result))
    return df
