"""End-to-end ensemble determinism (byte-for-byte, TZ gate)."""

from __future__ import annotations

import numpy as np
import pytest

from ens_synth import fast_lgbm_params, make_synthetic

from engine.ensemble.base import ComponentConfig
from engine.ensemble.catboost import CATBOOST_AVAILABLE
from engine.ensemble.combine import EnsembleConfig, EnsembleRanker


def _config() -> EnsembleConfig:
    return EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm", weight=0.6, params=dict(fast_lgbm_params())
            ),
            ComponentConfig("logreg", weight=0.4),
        ],
        combination="weighted",
        normalize_scores=True,
    )


@pytest.mark.skipif(
    not CATBOOST_AVAILABLE, reason="catboost not installed"
)
def test_all_three_components_deterministic():
    """LGBM + CatBoost + LogReg: identical scores across two runs."""

    def full() -> EnsembleConfig:
        return EnsembleConfig(
            components=[
                ComponentConfig(
                    "lgbm", weight=0.4, params=dict(fast_lgbm_params())
                ),
                ComponentConfig(
                    "catboost",
                    weight=0.4,
                    params={"iterations": 20, "depth": 4},
                ),
                ComponentConfig("logreg", weight=0.2),
            ],
            combination="weighted",
        )

    x, y, groups, _ = make_synthetic(n=600)
    s1 = EnsembleRanker(full()).fit(x, y, groups).predict(x)
    s2 = EnsembleRanker(full()).fit(x, y, groups).predict(x)
    np.testing.assert_array_equal(s1, s2)


def test_two_component_ensemble_byte_identical():
    x, y, groups, _ = make_synthetic(n=600)
    s1 = EnsembleRanker(_config()).fit(x, y, groups).predict(x)
    s2 = EnsembleRanker(_config()).fit(x, y, groups).predict(x)
    np.testing.assert_array_equal(s1, s2)


def test_seed_change_runs_deterministically():
    """A different component seed still yields a stable pipeline."""
    x, y, groups, _ = make_synthetic(n=600)
    seeded = EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm",
                weight=0.6,
                params=dict(fast_lgbm_params()),
                seed=11,
            ),
            ComponentConfig("logreg", weight=0.4),
        ],
        combination="weighted",
        normalize_scores=True,
    )
    s1 = EnsembleRanker(seeded).fit(x, y, groups).predict(x)
    s2 = EnsembleRanker(seeded).fit(x, y, groups).predict(x)
    np.testing.assert_array_equal(s1, s2)

