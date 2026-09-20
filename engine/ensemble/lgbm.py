"""LightGBM lambdarank component.

Pinned defaults follow the walk-forward head (lambdarank, relevance
grades from pessimistic R) plus the byte-for-byte determinism kit:
``deterministic=True``, ``force_row_wise=True``, ``num_threads=1``.
Dtype discipline: LightGBM bins float32 and float64 differently, so
the caller pins the matrix dtype once (see ``protocol.ENCODING_*``)
- never mix dtypes between fit and predict of one model.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np

from engine.ensemble.base import RankerComponent


LGBM_PARAMS: dict[str, Any] = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "n_estimators": 300,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "label_gain": list(range(13)),
    # determinism kit: byte-for-byte reproducible scores
    "random_state": 7,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbosity": -1,
}


def relevance_grades(y: np.ndarray) -> np.ndarray:
    """Pessimistic R -> 13 lambdarank grades (protocol mapping)."""
    return np.clip(np.round((y + 2.0) * 2.0), 0, 12).astype(np.int32)


def group_sort_order(groups: np.ndarray) -> np.ndarray:
    """Row order making groups contiguous and ascending (stable)."""
    return np.lexsort((np.arange(len(groups)), groups))


class LGBMComponent(RankerComponent):
    """LightGBM ranker over relevance grades of the R label."""

    def __init__(
        self, params: dict[str, Any] | None = None, seed: int = 7
    ) -> None:
        merged: dict[str, Any] = {**LGBM_PARAMS, **(params or {})}
        merged["random_state"] = seed
        self.params = merged
        self.model: lgb.LGBMRanker | None = None

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None = None,
    ) -> None:
        """Fit on group-sorted rows (LightGBM needs contiguous groups)."""
        order = group_sort_order(groups)
        counts = np.unique(groups, return_counts=True)[1]
        model = lgb.LGBMRanker(**self.params)
        model.fit(
            x[order],
            relevance_grades(y[order]),
            group=counts.tolist(),
            callbacks=[],
        )
        self.model = model

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Raw lambdarank scores; row order of ``x`` is preserved."""
        if self.model is None:
            raise RuntimeError("LGBMComponent is not fitted")
        return np.asarray(self.model.predict(x), dtype=np.float64)

    def feature_importance(self) -> np.ndarray | None:
        """Gain importance; ``None`` before ``fit``."""
        if self.model is None:
            return None
        return np.asarray(
            self.model.booster_.feature_importance(importance_type="gain"),
            dtype=np.float64,
        )
