"""Stacking meta-learner over per-component scores.

The meta-learner must NOT be trained on in-sample component scores -
on the rows the components were fitted on the scores are overfit and
the meta weights learn garbage (TZ item 8: no stacking without
nesting).  :func:`oof_score_matrix` builds an honest out-of-fold
matrix PAST-ONLY: time is sliced into ``n_folds`` tiles and each
tile's rows are scored by fresh components trained strictly before
the tile starts.  The ensemble's expanding-window walk-forward is the
outer nesting level; this inner past-only OOF is the second one.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from sklearn.linear_model import LogisticRegression, Ridge

from engine.ensemble.base import ComponentConfig, RankerComponent
from engine.ensemble.combine import build_component


MetaKind = Literal["logreg", "ridge", "none"]


class StackingMeta:
    """Linear blend of per-component scores -> final score."""

    def __init__(self, kind: MetaKind = "logreg", seed: int = 7) -> None:
        self.kind: MetaKind = kind
        self.seed = seed
        self.model: LogisticRegression | Ridge | None = None

    def fit(self, oof: np.ndarray, y: np.ndarray) -> None:
        """Fit on the OOF score matrix (``n_rows x n_components``)."""
        if self.kind == "logreg":
            self.model = LogisticRegression(C=1.0, max_iter=1000)
            self.model.fit(oof, (y > 0).astype(np.int32))
        elif self.kind == "ridge":
            self.model = Ridge(alpha=1.0)
            self.model.fit(oof, y.astype(np.float64))
        else:
            raise ValueError(f"meta_learner must not be {self.kind!r}")

    def predict(self, scores: np.ndarray) -> np.ndarray:
        """Blend one row of per-component scores per panel row."""
        if self.model is None:
            raise RuntimeError("StackingMeta is not fitted")
        if self.kind == "logreg":
            return np.asarray(
                self.model.decision_function(scores), dtype=np.float64
            )
        return np.asarray(self.model.predict(scores), dtype=np.float64)


def oof_score_matrix(
    components: list[ComponentConfig],
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    ts: np.ndarray,
    n_folds: int,
    seed: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    """Past-only OOF component scores, ``(scores, row_ix)``.

    Time is cut into ``n_folds`` equal-quantile tiles; tile ``k``'s
    rows are scored by fresh copies of every component trained on
    everything strictly before the tile starts.  Returns the stacked
    ``(n_scored, n_components)`` matrix and the indices of the scored
    rows (everything strictly after the first tile boundary - the
    earliest history has no honest past-tile training window).
    """
    if n_folds < 2:
        raise ValueError("stacking needs n_folds >= 2")
    bounds = np.quantile(ts, np.linspace(0.0, 1.0, n_folds + 1))
    interior = bounds[1:-1]
    per_comp: list[list[np.ndarray]] = [[] for _ in components]
    row_ix: list[np.ndarray] = []
    for i, lo in enumerate(interior):
        hi = interior[i + 1] if i + 1 < interior.size else np.inf
        train = ts < lo
        test = (ts >= lo) & (ts < hi)
        if not train.any() or not test.any():
            raise ValueError(
                "empty OOF fold: time span too short for stacking"
            )
        scores = _fit_predict_all(
            components, x, y, groups, seed, train, test
        )
        for j in range(len(components)):
            per_comp[j].append(scores[:, j])
        row_ix.append(np.where(test)[0])
    matrix = np.column_stack(
        [np.concatenate(c) for c in per_comp]
    ) if components else np.empty((0, 0))
    return matrix, np.concatenate(row_ix)


def _fit_predict_all(
    components: list[ComponentConfig],
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    seed: int,
    train: np.ndarray,
    test: np.ndarray,
) -> np.ndarray:
    """Fit every component on ``train``, score the ``test`` rows."""
    tr_ix = np.where(train)[0]
    te_ix = np.where(test)[0]
    out = np.empty((te_ix.size, len(components)), dtype=np.float64)
    for j, cfg in enumerate(components):
        comp: RankerComponent = build_component(
            ComponentConfig(
                name=cfg.name,
                enabled=True,
                weight=1.0,
                params=cfg.params,
                seed=seed,
            )
        )
        comp.fit(x[tr_ix], y[tr_ix], groups[tr_ix])
        out[:, j] = comp.predict(x[te_ix])
    return out

