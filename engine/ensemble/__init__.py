"""Ensemble ranking over heterogeneous components.

Replaces the monolithic LightGBM head with a configurable blend of
three members trained on the SAME feature matrix (``RankerData``):

- ``lgbm``     - LightGBM lambdarank (leaf-wise, NaN-native);
- ``catboost`` - CatBoost YetiRank (ordered boosting, oblivious trees);
- ``logreg``   - L2 logistic regression on the win label (linear
  baseline: if it matches the boosters, the signal is simple).

Components are switched on/off and weighted independently
(:class:`ComponentConfig`); scores are combined by
:class:`~engine.ensemble.combine.EnsembleRanker` (mean / weighted /
rank_mean / stacking).  The public surface is re-exported here; the
per-engine modules are importable directly for tests and ablations.
"""

from __future__ import annotations

from engine.ensemble.base import (
    ComponentConfig,
    RankerComponent,
    rank_normalize,
)
from engine.ensemble.combine import (
    EnsembleConfig,
    EnsembleRanker,
    build_component,
)


__all__ = [
    "ComponentConfig",
    "EnsembleConfig",
    "EnsembleRanker",
    "RankerComponent",
    "build_component",
    "rank_normalize",
]
