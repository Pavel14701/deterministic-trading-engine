"""Component interface, config semantics, rank normalization."""

from __future__ import annotations

import numpy as np
import pytest

from ens_synth import make_synthetic

from engine.ensemble.base import (
    ComponentConfig,
    RankerComponent,
    rank_normalize,
)
from engine.ensemble.combine import build_component


class _Const(RankerComponent):
    """Minimal concrete component for interface-level tests."""

    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    def fit(self, x, y, groups, ts=None) -> None:
        self.value = float(np.mean(y))

    def predict(self, x) -> np.ndarray:
        return np.full(len(x), self.value)

    def feature_importance(self) -> np.ndarray | None:
        return None


def test_component_config_defaults():
    c = ComponentConfig("lgbm")
    assert c.enabled and c.weight == 1.0 and c.seed == 7
    assert c.params == {}


def test_ranker_component_is_abstract():
    with pytest.raises(TypeError):
        RankerComponent()  # type: ignore[abstract]


def test_component_fit_changes_prediction():
    x, y, groups, _ = make_synthetic(n=200)
    comp = _Const()
    comp.fit(x, y, groups)
    out = comp.predict(x)
    assert out.shape == (len(x),)
    np.testing.assert_allclose(out, float(np.mean(y)))


def test_rank_normalize_maps_to_unit_interval():
    s = np.array([3.0, -1.0, 0.0, 10.0])
    r = rank_normalize(s)
    assert r.min() == 0.0 and r.max() == 1.0
    # monotone in the input: every higher score gets a higher rank
    i, j = 1, 3  # s[1] = -1 (min), s[3] = 10 (max)
    assert r[i] == 0.0 and r[j] == 1.0
    assert r[2] < r[0]  # 0.0 < 3.0 in scores -> rank below


def test_rank_normalize_is_monotone_and_deterministic():
    rng = np.random.default_rng(3)
    s = rng.normal(size=500)
    r1, r2 = rank_normalize(s), rank_normalize(s)
    np.testing.assert_array_equal(r1, r2)
    lo, hi = np.argmin(s), np.argmax(s)
    assert r1[lo] == 0.0 and r1[hi] == 1.0


def test_rank_normalize_ties_get_distinct_positions():
    s = np.ones(5)
    r = rank_normalize(s)
    assert len(set(r.tolist())) == 5  # deterministic tie-breaking


def test_rank_normalize_degenerate_inputs():
    """0- and 1-row inputs: zeros, no crash."""
    assert rank_normalize(np.array([])).tolist() == []
    assert rank_normalize(np.array([3.0])).tolist() == [0.0]


def test_build_component_registry():
    x, y, groups, _ = make_synthetic(n=120)
    for name, cls in (
        ("lgbm", "LGBMComponent"),
        ("logreg", "LogRegComponent"),
    ):
        comp = build_component(ComponentConfig(name))
        assert type(comp).__name__ == cls
        comp.fit(x, y, groups)
        assert comp.predict(x).shape == (len(x),)


def test_build_component_unknown_name_raises():
    with pytest.raises(ValueError, match="unknown component"):
        build_component(ComponentConfig("xgboost"))
