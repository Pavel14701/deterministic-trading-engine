"""Unit tests for the MTF dataset helpers (stages A.3/A.4).

Covers causal rolling percentile, purged chronological splits with
embargo, pessimistic limit fills, nearest-zone distances and the
SMA-based trend state.
"""

import numpy as np
import numpy.typing as npt
import pytest

from ai.src.mtf_dataset import (
    assign_splits,
    limit_fill,
    nearest_zone_dists,
    rolling_percentile,
    sma,
    trend_state,
)


@pytest.mark.unit
def test_sma_basic() -> None:
    """SMA is NaN until ``n`` samples, then equals the trailing mean."""
    x = np.arange(10, dtype=float)
    out = sma(x, 3)
    assert np.all(np.isnan(out[:2]))
    assert out[2] == pytest.approx(1.0)
    assert out[9] == pytest.approx(8.0)


@pytest.mark.unit
def test_rolling_percentile_causal_and_bounded() -> None:
    """Percentile uses only the trailing window and stays in [0, 1]."""
    x = np.linspace(0, 1, 21)
    out = rolling_percentile(x, window=5)
    assert np.all((out >= 0) & (out <= 1))
    # Last value is the max of its window -> percentile 1.
    assert out[-1] == pytest.approx(1.0)
    # A decreasing series: the current bar is the window minimum, so its
    # percentile is 1/len(window) -> 1/5 once the window is full.
    out_desc = rolling_percentile(np.linspace(1, 0, 21), window=5)
    assert np.allclose(out_desc[4:], 0.2)


@pytest.mark.unit
def test_rolling_percentile_nan_propagates() -> None:
    """NaN inputs yield NaN percentiles."""
    x = np.array([1.0, np.nan, 3.0])
    out = rolling_percentile(x, window=2)
    assert np.isnan(out[1])


def _split_counts(labels: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for lab in labels:
        out[lab] = out.get(lab, 0) + 1
    return out


@pytest.mark.unit
def test_assign_splits_embargo_no_boundary_crossing() -> None:
    """No trade crosses a split boundary; gaps are unused."""
    n, hold = 1000, 10
    idxs = np.arange(0, n, dtype=np.int64)
    labels = assign_splits(idxs, n, hold)
    train_end, val_end = 600, 800
    for idx, lab in zip(idxs, labels):
        if lab == "train":
            assert idx + hold < train_end
        elif lab == "val":
            assert train_end + hold <= idx < val_end - hold
        elif lab == "test":
            assert val_end + hold <= idx
        else:
            # Unused entries only occur inside embargo gaps.
            assert not (idx + hold < train_end)
    counts = _split_counts(labels)
    assert counts["train"] > 0 and counts["val"] > 0 and counts["test"] > 0
    assert counts.get("", 0) >= 2 * hold - 1  # two embargo gaps
    # Sets are disjoint by construction.
    assert all(lab in {"train", "val", "test", ""} for lab in labels)


@pytest.mark.unit
def test_limit_fill_pessimistic_buffer() -> None:
    """A long limit fills only when price trades through it by buffer."""
    n = 6
    high = np.full(n, 101.0)
    low = np.array([100.5, 100.4, 99.9, 99.0, 99.5, 100.0])
    atr = np.ones(n)
    # Limit 100: bar 0 low 100.5 (no), bar 2 low 99.9 <= 100 - 0.1 -> fill@2.
    assert limit_fill("long", 100.0, high, low, atr, 0, buf_atr=0.1, max_wait=5) == 2
    # Buffer 0.5: needs low <= 99.5 -> bar 3.
    assert limit_fill("long", 100.0, high, low, atr, 0, buf_atr=0.5, max_wait=5) == 3
    # Buffer 2.0: never fills within the wait window.
    assert limit_fill("long", 100.0, high, low, atr, 0, buf_atr=2.0, max_wait=5) == -1


@pytest.mark.unit
def test_limit_fill_short_side_and_expiry() -> None:
    """Short limits fill on highs through the level; orders expire."""
    n = 4
    high = np.array([100.2, 100.6, 100.1, 100.3])
    low = np.full(n, 99.0)
    atr = np.ones(n)
    assert limit_fill("short", 100.0, high, low, atr, 0, buf_atr=0.5, max_wait=4) == 1
    # Order placed after the touch never fills within its window.
    assert limit_fill("short", 100.0, high, low, atr, 2, buf_atr=0.5, max_wait=2) == -1
    # Non-finite limit price never fills.
    assert limit_fill("short", np.nan, high, low, atr, 0) == -1


@pytest.mark.unit
def test_nearest_zone_dists() -> None:
    """Distances are measured to the nearest known edges; straddle = 0."""
    zones = [(10.0, 11.0), (15.0, 16.0), (20.0, 21.0)]
    below, above = nearest_zone_dists(zones, 13.0)
    assert below == pytest.approx(2.0)  # 13 -> 11
    assert above == pytest.approx(2.0)  # 13 -> 15
    inside_below, inside_above = nearest_zone_dists(zones, 10.5)
    assert inside_below == 0.0 and inside_above == 0.0
    no_above_below, no_above = nearest_zone_dists(zones[:1], 12.0)
    assert no_above_below == pytest.approx(1.0)
    assert no_above == np.inf
    empty = nearest_zone_dists([], 5.0)
    assert empty == (np.inf, np.inf)


@pytest.mark.unit
def test_trend_state_causal() -> None:
    """Sign flips exactly when close crosses its own trailing SMA."""
    up = np.concatenate([np.full(60, 100.0), np.linspace(100, 110, 60)])
    atr = np.ones(len(up))
    z, slope, sign = trend_state(up, atr, n=50, slope_bars=10)
    assert sign[:49].tolist() == [0] * 49  # SMA undefined -> sign 0
    assert sign[49] == 1  # first defined SMA equals the flat close
    assert (sign[50:60] == 1).all()  # flat period: close >= sma
    assert (sign[95:] == 1).all()  # uptrend keeps price above SMA
    assert np.all(np.isnan(z[:49]))
    assert slope[70] > 0  # SMA rising 10 bars into the ramp
