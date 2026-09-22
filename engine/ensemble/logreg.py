"""Logistic-regression component: the linear-signal baseline.

Trains on the win indicator (``y > 0``) and scores with
``decision_function`` (monotone in P(win), so the ranking order is
the probability order).  ``StandardScaler`` is part of the pipeline
by default - without it L2 coefficients are scale-dominated and
lbfgs converges poorly (pinned by a test).  ``class_weight=
"balanced"`` is on by default: winners are the minority class in the
protocol panel.
"""

from __future__ import annotations

import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from engine.ensemble.base import RankerComponent


LOGREG_PARAMS: dict[str, object] = {
    "C": 0.1,
    # penalty: L2 is lbfgs' default (explicit 'penalty' is deprecated
    # in sklearn 1.8); keep the rest explicit.
    "solver": "lbfgs",
    "max_iter": 1000,
    "class_weight": "balanced",
    "random_state": 7,
}


class LogRegComponent(RankerComponent):
    """(Optional scaler) + L2 logistic regression, margin scores."""

    def __init__(
        self,
        params: dict[str, object] | None = None,
        seed: int = 7,
        use_scaler: bool = True,
    ) -> None:
        merged: dict[str, object] = {**LOGREG_PARAMS, **(params or {})}
        merged["random_state"] = seed
        self.params = merged
        self.use_scaler = use_scaler
        steps: list[tuple[str, object]] = []
        if use_scaler:
            steps.append(("scaler", StandardScaler()))
        steps.append(("lr", LogisticRegression(**merged)))
        self.pipe = Pipeline(steps)
        self.converged_: bool | None = None

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None = None,
    ) -> None:
        """Fit on the win indicator; rows may come in any order."""
        label = (np.asarray(y) > 0).astype(np.int32)
        self.pipe.fit(x, label)
        lr: LogisticRegression = self.pipe.named_steps["lr"]
        self.converged_ = bool(np.all(lr.n_iter_ < lr.max_iter))

    def predict(self, x: np.ndarray) -> np.ndarray:
        """``decision_function`` margins; higher = more likely a win."""
        return np.asarray(
            self.pipe.decision_function(x), dtype=np.float64
        )

    def feature_importance(self) -> np.ndarray | None:
        """Signed L2 coefficients (diagnostic: sign and relative size)."""
        lr: LogisticRegression = self.pipe.named_steps["lr"]
        return np.asarray(lr.coef_, dtype=np.float64).ravel().copy()
