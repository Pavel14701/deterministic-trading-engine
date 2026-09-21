"""Unit tests for zscore module.

Tests cover:
- Basic functionality of zscore_numpy, zscore_ind, zscore_polars
- Multiplier scaling
- ddof influence
- Offset and fillna
- Polars Series and DataFrame integration
- Consistency between Numba algorithms (online vs two_pass)
- Comparison with TA-Lib (if available)
"""

import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

from numpy.testing import assert_allclose

from ta.src.external import talib_available
from ta.src.statistics.zscore import zscore_ind, zscore_numpy, zscore_polars


# -----------------------------------------------------------------------------
# Basic functionality tests using shared fixtures
# -----------------------------------------------------------------------------


@pytest.mark.statistics
def test_zscore_numpy_basic(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test zscore_numpy with default parameters on a random walk."""
    close = prices_random_walk
    n = len(close)
    result = zscore_numpy(
        close, length=30, multiplier=1.0, ddof=1, use_talib=False
    )

    assert result.shape == (n,)
    assert result.dtype == np.float64
    # First 29 values should be NaN (window not full)
    assert np.isnan(result[:29]).all()
    # After window, values should be finite
    assert np.isfinite(result[29:]).all()


@pytest.mark.statistics
def test_zscore_numpy_multiplier(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test that multiplier scales the z-score correctly."""
    close = prices_random_walk
    result1 = zscore_numpy(
        close, length=30, multiplier=1.0, ddof=1, use_talib=False
    )
    result2 = zscore_numpy(
        close, length=30, multiplier=2.0, ddof=1, use_talib=False
    )

    valid_mask = ~np.isnan(result1)
    assert_allclose(result2[valid_mask], result1[valid_mask] / 2.0, rtol=1e-6)


@pytest.mark.statistics
def test_zscore_numpy_ddof(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test that ddof affects the standard deviation calculation."""
    close = prices_random_walk
    result0 = zscore_numpy(
        close, length=30, multiplier=1.0, ddof=0, use_talib=False
    )
    result1 = zscore_numpy(
        close, length=30, multiplier=1.0, ddof=1, use_talib=False
    )

    assert result0.shape == result1.shape
    valid_mask = ~np.isnan(result0)
    assert np.isfinite(result0[valid_mask]).all()
    assert np.isfinite(result1[valid_mask]).all()

    # ddof should affect the result (population vs sample std)
    diff = np.abs(result0[valid_mask] - result1[valid_mask]).max()
    assert diff > 1e-10, "ddof should affect the result"


@pytest.mark.statistics
def test_zscore_numpy_offset_fillna(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test offset and fillna parameters."""
    close = prices_random_walk
    result_no_offset = zscore_numpy(
        close, length=30, offset=0, use_talib=False
    )
    result_offset = zscore_numpy(
        close, length=30, offset=1, fillna=0.0, use_talib=False
    )

    assert result_offset[0] == 0.0
    # fillna also replaces the warm-up NaNs of the shifted series
    no_offset_tail = result_no_offset[:-1]
    expected = np.where(np.isnan(no_offset_tail), 0.0, no_offset_tail)
    assert_allclose(result_offset[1:], expected, rtol=1e-6)


# -----------------------------------------------------------------------------
# Polars integration tests using shared fixtures
# -----------------------------------------------------------------------------


@pytest.mark.statistics
def test_zscore_ind_with_pl_series(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test zscore_ind with Polars Series input."""
    close_s = pl.Series(prices_random_walk)
    result = zscore_ind(
        close_s, length=30, multiplier=1.0, ddof=1, use_talib=False
    )

    assert isinstance(result, np.ndarray)
    assert result.shape == (len(prices_random_walk),)
    assert result.dtype == np.float64
    assert np.isnan(result[:29]).all()
    assert np.isfinite(result[29:]).all()


@pytest.mark.statistics
def test_zscore_polars_basic(df_random_walk: pl.DataFrame) -> None:
    """Test zscore_polars adds a column correctly."""
    result_df = zscore_polars(
        df_random_walk,
        close_col="close",
        length=30,
        use_talib=False,
        output_col="ZSCORE",
    )

    assert "ZSCORE" in result_df.columns
    assert len(result_df) == len(df_random_walk)
    assert result_df["ZSCORE"].dtype == pl.Float64

    close_arr = df_random_walk["close"].to_numpy()
    expected = zscore_numpy(close_arr, length=30, use_talib=False)
    assert_allclose(
        result_df["ZSCORE"].to_numpy(), expected, rtol=1e-6, equal_nan=True
    )


@pytest.mark.statistics
def test_zscore_polars_default_output_col(
    df_random_walk: pl.DataFrame,
) -> None:
    """Test default output column name."""
    result_df = zscore_polars(
        df_random_walk, close_col="close", length=30, use_talib=False
    )
    expected_col = "ZS_30"
    assert expected_col in result_df.columns
    assert result_df[expected_col].dtype == pl.Float64


@pytest.mark.statistics
def test_zscore_polars_with_offset_fillna(
    df_random_walk: pl.DataFrame,
) -> None:
    """Test zscore_polars with offset and fillna."""
    result_df = zscore_polars(
        df_random_walk,
        close_col="close",
        length=30,
        offset=1,
        fillna=0.0,
        use_talib=False,
        output_col="ZSCORE",
    )

    assert result_df["ZSCORE"][0] == 0.0

    close_arr = df_random_walk["close"].to_numpy()
    expected = zscore_numpy(
        close_arr, length=30, offset=1, fillna=0.0, use_talib=False
    )
    assert_allclose(
        result_df["ZSCORE"].to_numpy(), expected, rtol=1e-6, equal_nan=True
    )


# -----------------------------------------------------------------------------
# Algorithm consistency and TA-Lib comparison
# -----------------------------------------------------------------------------


@pytest.mark.statistics
def test_zscore_numba_algorithms_consistency(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test that Numba online and two_pass algorithms produce similar
    results."""
    close = prices_random_walk
    result_online = zscore_numpy(
        close, length=30, use_talib=False, algorithm="online"
    )
    result_twopass = zscore_numpy(
        close, length=30, use_talib=False, algorithm="two_pass"
    )

    valid_mask = ~np.isnan(result_online)
    assert_allclose(
        result_online[valid_mask],
        result_twopass[valid_mask],
        rtol=1e-4,
        atol=1e-4,
        err_msg="Numba online and two_pass differ too much",
    )


@pytest.mark.skipif(not talib_available, reason="TA-Lib not installed")
@pytest.mark.statistics
def test_zscore_talib_vs_numba(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test TA-Lib vs Numba (using two_pass for accuracy) with tight
    tolerance."""
    close = prices_random_walk
    result_talib = zscore_numpy(close, length=30, use_talib=True)
    result_numba = zscore_numpy(
        close, length=30, use_talib=False, algorithm="two_pass"
    )

    valid_mask = ~np.isnan(result_talib)
    assert_allclose(
        result_talib[valid_mask],
        result_numba[valid_mask],
        rtol=0.02,
        atol=0.02,
        err_msg="TA-Lib and Numba two_pass differ beyond tolerance",
    )


@pytest.mark.skipif(not talib_available, reason="TA-Lib not installed")
@pytest.mark.statistics
def test_zscore_talib_vs_numba_online(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test TA-Lib vs Numba online algorithm with wider tolerance."""
    close = prices_random_walk
    result_talib = zscore_numpy(close, length=30, use_talib=True)
    result_numba = zscore_numpy(
        close, length=30, use_talib=False, algorithm="online"
    )

    valid_mask = ~np.isnan(result_talib)
    assert_allclose(
        result_talib[valid_mask],
        result_numba[valid_mask],
        rtol=0.02,
        atol=0.02,
        err_msg="TA-Lib and Numba online differ beyond tolerance",
    )


@pytest.mark.skipif(not talib_available, reason="TA-Lib not installed")
@pytest.mark.statistics
def test_zscore_talib_vs_numba_twopass(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Test TA-Lib vs Numba two_pass algorithm with tight tolerance."""
    close = prices_random_walk
    result_talib = zscore_numpy(close, length=30, use_talib=True)
    result_numba = zscore_numpy(
        close, length=30, use_talib=False, algorithm="two_pass"
    )

    valid_mask = ~np.isnan(result_talib)
    assert_allclose(
        result_talib[valid_mask],
        result_numba[valid_mask],
        rtol=0.014,
        atol=0.014,
        err_msg="TA-Lib and Numba two_pass differ beyond tolerance",
    )


# -----------------------------------------------------------------------------
# IEEE-754 corner-case tests
# -----------------------------------------------------------------------------


@pytest.mark.statistics
def test_zscore_numpy_length_too_short_raises() -> None:
    """Passing length < 1 raises ValueError (documented contract)."""
    prices = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="length must be >= 1"):
        zscore_numpy(prices, length=0, use_talib=False)


@pytest.mark.statistics
def test_zscore_numpy_nan_input_raises() -> None:
    """NaN input raises via the underlying SMA (nan_policy='raise')."""
    close = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0])
    with pytest.raises(ValueError, match="Input contains NaN"):
        zscore_numpy(close, length=3, ddof=1, use_talib=False)


@pytest.mark.statistics
def test_zscore_numpy_inf_input_raises() -> None:
    """An inf input is converted to NaN by SMA and raises the same way."""
    close = np.array([1.0, np.inf, 3.0, 4.0, 5.0, 6.0, 7.0])
    with pytest.raises(ValueError, match="Input contains NaN"):
        zscore_numpy(close, length=3, ddof=1, use_talib=False)


@pytest.mark.statistics
def test_zscore_monotonic_series_positive() -> None:
    """Regression: a monotonically increasing series gives z = +1.

    The docstrings previously showed -1, which is the wrong sign: at
    each window the current price sits one sample std ABOVE the window
    mean, so z = (x - mean) / std = +1.
    """
    prices = np.arange(1.0, 11.0)
    result = zscore_numpy(
        prices, length=3, multiplier=1.0, ddof=1, use_talib=False
    )
    expected = np.full(10, np.nan)
    expected[2:] = 1.0
    assert_allclose(result, expected, atol=1e-12, equal_nan=True)


@pytest.mark.statistics
def test_zscore_constant_series_nan() -> None:
    """Constant input -> std = 0 -> 0/0 -> NaN (pinned behaviour)."""
    prices = np.ones(30)
    result = zscore_numpy(
        prices, length=3, multiplier=1.0, ddof=1, use_talib=False
    )
    assert np.all(np.isnan(result))


@pytest.mark.skipif(
    not talib_available,
    reason="TA-Lib not installed",
)
@pytest.mark.statistics
def test_zscore_backends_agree_at_ddof0(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Cross-backend consistency: use_talib True vs False at ddof=0."""
    a = zscore_numpy(
        prices_random_walk, length=30, ddof=0, use_talib=True
    )
    b = zscore_numpy(
        prices_random_walk, length=30, ddof=0, use_talib=False
    )
    assert_allclose(a, b, atol=1e-10, equal_nan=True)


@pytest.mark.skipif(
    not talib_available,
    reason="TA-Lib not installed",
)
@pytest.mark.statistics
def test_zscore_ddof1_honoured_on_default_backend(
    prices_random_walk: npt.NDArray[np.float64],
) -> None:
    """Default call (use_talib=True, ddof=1) must return sample-std z.

    Regression: TA-Lib's STDDEV has no ddof parameter, so the old
    code silently produced population-std z-scores on the default
    path -- different numbers than the same call with use_talib=False.
    """
    a = zscore_numpy(prices_random_walk, length=30, ddof=1)  # defaults
    b = zscore_numpy(
        prices_random_walk, length=30, ddof=1, use_talib=False
    )
    assert_allclose(a, b, atol=1e-12, equal_nan=True)
