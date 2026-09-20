"""Shared pytest fixtures for the research test suite."""


from datetime import datetime

import numpy as np
import polars as pl
import pytest

from engine.features.indicators import compute_atr
from engine.infra.datatypes import OrderBlock


@pytest.fixture
def sample_dataframe() -> pl.DataFrame:
    """Create a synthetic DataFrame with OHLCV and other columns."""
    n = 200
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 1.5
    low = close - np.random.rand(n) * 1.5
    open_ = close - np.random.rand(n) * 0.5
    volume = np.random.randint(1000, 10000, n)
    tp = close + np.abs(np.random.rand(n) * 2) + 1.0
    sl = np.maximum(close - np.abs(np.random.rand(n) * 2) - 1.0, 1.0)
    return pl.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "tp": tp,
            "sl": sl,
            "bar_index": np.arange(n),
        }
    )


@pytest.fixture
def sample_order_blocks() -> list[OrderBlock]:
    """Create a list of synthetic order blocks."""
    obs = []
    for i in range(5):
        start = i * 40 + 10
        end = start + 15
        zone_low = 95 + i * 2
        zone_high = zone_low + 2
        ob = OrderBlock(
            id=i,
            block_type="demand" if i % 2 == 0 else "supply",
            start=datetime.now(),
            break_=datetime.now(),
            retest=datetime.now(),
            zone_low=zone_low,
            zone_high=zone_high,
            strength=1.0 + i * 0.5,
            structure_label="valid" if i % 2 == 0 else None,
            trend_direction="up" if i < 3 else "down",
            start_idx=start,
            end_idx=end,
        )
        obs.append(ob)
    return obs


@pytest.fixture
def sample_atr(sample_dataframe: pl.DataFrame) -> np.ndarray:
    """Compute ATR for the sample dataframe."""
    return compute_atr(sample_dataframe, period=14)


@pytest.fixture
def large_dataframe() -> pl.DataFrame:
    """Large synthetic DataFrame for slow integration tests."""
    n = 10000
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 1.5
    low = close - np.random.rand(n) * 1.5
    open_ = close - np.random.rand(n) * 0.5
    volume = np.random.randint(1000, 10000, n)
    tp = close + np.abs(np.random.rand(n) * 2) + 1.0
    sl = np.maximum(close - np.abs(np.random.rand(n) * 2) - 1.0, 1.0)
    return pl.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "tp": tp,
            "sl": sl,
            "bar_index": np.arange(n),
        }
    )


@pytest.fixture
def large_order_blocks() -> list[OrderBlock]:
    """Large list of order blocks for slow tests."""
    obs = []
    for i in range(100):
        start = i * 80 + 10
        end = start + 30
        zone_low = 95 + i * 0.5
        zone_high = zone_low + 2
        ob = OrderBlock(
            id=i,
            block_type="demand" if i % 2 == 0 else "supply",
            start=datetime.now(),
            break_=datetime.now(),
            retest=datetime.now(),
            zone_low=zone_low,
            zone_high=zone_high,
            strength=1.0 + i * 0.1,
            structure_label="valid" if i % 2 == 0 else None,
            trend_direction="up" if i < 50 else "down",
            start_idx=start,
            end_idx=end,
        )
        obs.append(ob)
    return obs
