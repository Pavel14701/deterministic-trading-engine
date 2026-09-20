"""Component interface and shared score utilities.

Conventions binding every component to the protocol's ``RankerData``:

- ``x`` is the flat ``(n_rows, n_features)`` matrix, one row per
  (candidate, rule) reference-config row - identical for all
  components (assembled once by ``assemble_ranker_data``);
- ``y`` is the pessimistic R label (continuous, ~[-2, 3]); each
  component maps it to its own training target (relevance grades,
  win indicator, raw regression);
- ``groups[i]`` is the candidate id of row ``i`` (the ``row`` column
  of ``RankerData``).  Ranking models need contiguous groups, so a
  component MUST sort internally on ``fit``; ``predict`` preserves
  the row order of the ``x`` it is given;
- ``ts`` (row timestamps, ms) is optional and only needed by
  stacking (past-only out-of-fold meta training).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ComponentConfig:
    """One ensemble member: identity, switch, blend weight, params.

    ``params`` overrides the component's default hyper-parameters
    (shallow merge, keys win).  ``weight=0.0`` keeps the component
    trained but removes its contribution - equivalent to
    ``enabled=False`` on the combined scores (pinned by a test).
    """

    name: str
    enabled: bool = True
    weight: float = 1.0
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 7


class RankerComponent(ABC):
    """A single scoring model: higher score = better candidate."""

    @abstractmethod
    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        ts: np.ndarray | None = None,
    ) -> None:
        """Train on the (possibly unordered) rows of one fold train."""

    @abstractmethod
    def predict(self, x: np.ndarray) -> np.ndarray:
        """Score every row of ``x`` (same order)."""

    @abstractmethod
    def feature_importance(self) -> np.ndarray | None:
        """Per-feature importance, or ``None`` if the model has none."""


def rank_normalize(scores: np.ndarray) -> np.ndarray:
    """Map scores to their rank position in ``[0, 1]`` (higher=better).

    Rank space makes heterogeneous score scales comparable before
    blending (LightGBM lambdarank outputs and logistic margins live
    on different axes).  Ties get distinct positions by stable order -
    deterministic, which is what the determinism gate needs.
    """
    s = np.asarray(scores, dtype=np.float64).ravel()
    n = s.size
    if n < 2:
        return np.zeros_like(s)
    order = np.argsort(s, kind="stable")
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.arange(n, dtype=np.float64)
    return ranks / float(n - 1)
