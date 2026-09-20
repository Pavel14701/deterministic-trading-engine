"""Ensemble assembly: configuration, blending, stacking hook.

``EnsembleRanker`` owns the active component set, optional rank
normalization and the score combination rule.  All combination modes
are deterministic: components are built and queried in the config's
order, ``rank_normalize`` is tie-stable, and the weighted sum is a
plain left-to-right accumulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from engine.ensemble.base import (
    ComponentConfig,
    RankerComponent,
    rank_normalize,
)


if TYPE_CHECKING:
    from engine.ensemble.meta import StackingMeta

Combination = Literal["mean", "weighted", "rank_mean", "stacking"]
MetaLearner = Literal["logreg", "ridge", "none"]


@dataclass
class EnsembleConfig:
    """Ensemble blueprint: members + how to blend their scores."""

    components: list[ComponentConfig]
    combination: Combination = "weighted"
    meta_learner: MetaLearner = "none"
    normalize_scores: bool = True
    #: past-only OOF tiles for stacking meta training
    meta_folds: int = 3
    seed: int = 7
    meta_params: dict[str, object] = field(default_factory=dict)

    def active(self) -> list[ComponentConfig]:
        """Enabled members, in config order (build/query order)."""
        return [c for c in self.components if c.enabled]


def build_component(cfg: ComponentConfig) -> RankerComponent:
    """Instantiate a component by its registered name.

    Local imports keep ``catboost`` optional: importing the registry
    (or :mod:`engine.ensemble`) never pulls the heavy libs; only
    building a concrete member does.
    """
    if cfg.name == "lgbm":
        from engine.ensemble.lgbm import LGBMComponent

        return LGBMComponent(cfg.params, cfg.seed)
    if cfg.name == "catboost":
        from engine.ensemble.catboost import CatBoostComponent

        return CatBoostComponent(cfg.params, cfg.seed)
    if cfg.name == "logreg":
        from engine.ensemble.logreg import LogRegComponent

        return LogRegComponent(cfg.params, cfg.seed)
    raise ValueError(f"unknown component: {cfg.name!r}")


class EnsembleRanker:
    """Blend of enabled components over one shared feature matrix."""

    def __init__(self, config: EnsembleConfig) -> None:
        self.config = config
        self.components: dict[str, RankerComponent] = {}
        self.meta: StackingMeta | None = None
        self._fitted = False

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None = None,
    ) -> "EnsembleRanker":
        """Fit every enabled component; stack via past-only OOF.

        ``ts`` is required for ``combination="stacking"`` (the OOF
        tiles are time slices); ignored by the other modes.
        """
        active = self.config.active()
        if not active:
            raise ValueError("ensemble config has no enabled components")
        for cfg in active:
            comp = build_component(cfg)
            comp.fit(x, y, groups, ts=ts)
            self.components[cfg.name] = comp
        if self.config.combination == "stacking":
            self._fit_meta(x, y, groups, ts)
        self._fitted = True
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Combined scores for every row of ``x`` (higher = better)."""
        if not self._fitted:
            raise RuntimeError("EnsembleRanker is not fitted")
        scores: dict[str, np.ndarray] = {}
        for name, comp in self.components.items():
            s = comp.predict(x)
            if self.config.normalize_scores:
                s = rank_normalize(s)
            scores[name] = s
        return self._combine(scores)

    def _combine(self, scores: dict[str, np.ndarray]) -> np.ndarray:
        """Apply the configured combination rule to component scores."""
        names = list(scores)
        if self.config.combination == "mean":
            return np.asarray(
                np.mean(list(scores.values()), axis=0), dtype=np.float64
            )
        if self.config.combination == "weighted":
            weights = {c.name: c.weight for c in self.config.active()}
            total_w = sum(weights[n] for n in names)
            if total_w <= 0:
                raise ValueError("weighted combination needs total_w > 0")
            out = np.zeros_like(next(iter(scores.values())))
            for n in names:
                out = out + scores[n] * (weights[n] / total_w)
            return out
        if self.config.combination == "rank_mean":
            ranks = {n: rank_normalize(s) for n, s in scores.items()}
            return np.asarray(
                np.mean(list(ranks.values()), axis=0), dtype=np.float64
            )
        if self.config.combination == "stacking":
            meta = self._meta_model()
            return meta.predict(np.column_stack(list(scores.values())))
        raise ValueError(  # pragma: no cover - Literal-guarded
            f"unknown combination: {self.config.combination}"
        )

    def _fit_meta(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None,
    ) -> None:
        """Train the meta-learner on past-only OOF component scores."""
        if self.config.meta_learner == "none":
            raise ValueError(
                "stacking requires meta_learner ('logreg' or 'ridge')"
            )
        if ts is None:
            raise ValueError(
                "stacking requires ts (past-only OOF is time-based)"
            )
        from engine.ensemble.meta import StackingMeta, oof_score_matrix

        oof, row_ix = oof_score_matrix(
            self.config.active(),
            x,
            y,
            groups,
            ts,
            self.config.meta_folds,
            self.config.seed,
        )
        meta = StackingMeta(self.config.meta_learner, self.config.seed)
        meta.fit(oof, y[row_ix])
        self.meta = meta

    def _meta_model(self) -> StackingMeta:
        """The fitted :class:`~engine.ensemble.meta.StackingMeta`."""
        if self.meta is None:  # pragma: no cover - guarded by fit()
            raise RuntimeError("stacking meta is not fitted")
        return self.meta
