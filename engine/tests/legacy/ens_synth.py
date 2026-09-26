"""Synthetic ranking data shared by the ensemble test suite.

Every generator returns ``(x, y, groups, ts)`` in the ensemble
convention: ``groups[i]`` is the candidate id of row ``i`` (row order
is intentionally NOT group-sorted - components must handle that),
``y`` is a continuous R-like label, ``ts`` is a sorted time axis.
"""

from __future__ import annotations

import numpy as np


def make_synthetic(
    n: int = 1000,
    d: int = 8,
    g: int = 100,
    signal: float = 1.0,
    seed: int = 7,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Group-structured panel: informative col 0, group effect, noise.

    ``y`` depends on the per-group latent effect and column 0 - both
    recoverable by rankers, so a healthy fit yields positive decile
    spread on held-out rows.
    """
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, d))
    groups = np.arange(n) % max(1, min(g, n))
    effect = rng.normal(size=max(1, min(g, n))) * signal
    y = (
        effect[groups]
        + 0.7 * signal * x[:, 0]
        + 0.3 * signal * rng.normal(size=n)
    )
    ts = np.sort(rng.integers(0, 10**9, size=n)).astype(np.int64)
    return x.astype(np.float32), y.astype(np.float32), groups, ts


def make_leaky(
    n: int = 800, d: int = 6, seed: int = 7
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Panel whose LAST column is the label plus tiny noise."""
    x, y, groups, ts = make_synthetic(n=n, d=d - 1, seed=seed)
    rng = np.random.default_rng(seed + 1)
    leaky = np.column_stack(
        [x, y + 0.01 * rng.normal(size=n)]
    ).astype(np.float32)
    return leaky, y, groups, ts, d - 1


def fast_lgbm_params() -> dict[str, object]:
    """Tiny-but-deterministic LGBM overrides for unit tests."""
    return {
        "n_estimators": 25,
        "num_leaves": 7,
        "min_child_samples": 10,
        "learning_rate": 0.1,
    }


def fast_catboost_params() -> dict[str, object]:
    """Tiny-but-deterministic CatBoost overrides for unit tests."""
    return {"iterations": 25, "depth": 4, "learning_rate": 0.1}
