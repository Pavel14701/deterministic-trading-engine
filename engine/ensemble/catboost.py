"""CatBoost YetiRank component (optional dependency).

Ordered boosting + oblivious trees: the inductive bias opposite to
LightGBM's leaf-wise growth.  Grouping goes through ``Pool(group_id=)``
(rows are group-sorted before the pool is built so the group ids are
contiguous - CatBoost requires that).  Determinism: ``random_seed``
plus ``thread_count=1``; a different fixed ``thread_count`` is still
run-to-run deterministic but slower/faster - pin it deliberately.

``catboost`` is an optional dependency: constructing this component
without it raises ``ImportError`` with the install hint; experiments
gate on :data:`CATBOOST_AVAILABLE`.
"""

from __future__ import annotations

import numpy as np

from engine.ensemble.base import RankerComponent
from engine.ensemble.lgbm import group_sort_order


try:  # optional dependency - keep importing this module cheap
    from catboost import CatBoostRanker, Pool
except ImportError:  # pragma: no cover - exercised without catboost
    CatBoostRanker = None  # type: ignore[assignment,misc]
    Pool = None  # type: ignore[assignment,misc]

CATBOOST_AVAILABLE = CatBoostRanker is not None

CATBOOST_PARAMS: dict[str, object] = {
    "loss_function": "YetiRank",
    "iterations": 300,
    "depth": 6,
    "learning_rate": 0.05,
    "l2_leaf_reg": 3.0,
    "random_seed": 7,
    "thread_count": 1,
    "verbose": False,
    "allow_writing_files": False,
}


class CatBoostComponent(RankerComponent):
    """CatBoost ranker trained on raw pessimistic R (YetiRank)."""

    def __init__(
        self, params: dict[str, object] | None = None, seed: int = 7
    ) -> None:
        if not CATBOOST_AVAILABLE:  # pragma: no cover
            raise ImportError(
                "catboost is not installed; "
                "install it or drop the component from the config"
            )
        merged: dict[str, object] = {**CATBOOST_PARAMS, **(params or {})}
        merged["random_seed"] = seed
        self.params = merged
        self.model: CatBoostRanker | None = None

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None = None,
    ) -> None:
        """Fit on a group-sorted ``Pool`` (contiguous ``group_id``)."""
        order = group_sort_order(groups)
        pool = Pool(
            x[order],
            label=y[order].astype(np.float64),
            group_id=groups[order],
        )
        model = CatBoostRanker(**self.params)
        model.fit(pool)
        self.model = model

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Raw YetiRank scores; row order of ``x`` is preserved."""
        if self.model is None:
            raise RuntimeError("CatBoostComponent is not fitted")
        return np.asarray(self.model.predict(x), dtype=np.float64)

    def feature_importance(self) -> np.ndarray | None:
        """PredictionValuesChange importance; ``None`` before ``fit``."""
        if self.model is None:
            return None
        return np.asarray(
            self.model.get_feature_importance(
                type="PredictionValuesChange"
            ),
            dtype=np.float64,
        )
