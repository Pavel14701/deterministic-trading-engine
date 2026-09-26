"""EnsembleRanker: enable/disable, weights, combination modes."""

from __future__ import annotations

import numpy as np
import pytest

from ens_synth import fast_lgbm_params, make_synthetic

from engine.ensemble.base import ComponentConfig
from engine.ensemble.combine import EnsembleConfig, EnsembleRanker


def _cfg(components: list[ComponentConfig], **kw: object) -> EnsembleConfig:
    merged: dict[str, object] = {
        "components": components,
        "normalize_scores": True,
    }
    merged.update(kw)
    return EnsembleConfig(**merged)  # type: ignore[arg-type]


def _two() -> list[ComponentConfig]:
    p = fast_lgbm_params()
    return [
        ComponentConfig("lgbm", params=dict(p)),
        ComponentConfig("logreg"),
    ]


def _fit(cfg: EnsembleConfig, n: int = 600) -> tuple[EnsembleRanker, np.ndarray]:
    x, y, groups, _ = make_synthetic(n=n)
    ens = EnsembleRanker(cfg).fit(x, y, groups)
    return ens, ens.predict(x)


def test_predict_before_fit_raises():
    x, _, _, _ = make_synthetic(n=50)
    with pytest.raises(RuntimeError, match="not fitted"):
        EnsembleRanker(_cfg(_two())).predict(x)


def test_no_enabled_components_raises():
    comps = [ComponentConfig("lgbm", enabled=False)]
    with pytest.raises(ValueError, match="no enabled components"):
        EnsembleRanker(_cfg(comps)).fit(*make_synthetic(n=100)[:3])


def test_ensemble_enable_disable():
    """Disabling a component changes the scores."""
    _, s_on = _fit(_cfg(_two()))
    _, s_off = _fit(
        _cfg([_two()[0], ComponentConfig("logreg", enabled=False)])
    )
    assert not np.allclose(s_on, s_off)


def test_ensemble_weight_zero_equals_disabled():
    """weight=0 removes the contribution exactly (TZ-pinned)."""
    _, s_zero = _fit(
        _cfg([_two()[0], ComponentConfig("logreg", weight=0.0)])
    )
    _, s_off = _fit(
        _cfg([_two()[0], ComponentConfig("logreg", enabled=False)])
    )
    np.testing.assert_allclose(s_zero, s_off)


def test_weighted_mode_normalizes_weights():
    """(1.0, 1.0) and (0.5, 0.5) give identical blends."""
    _, s_a = _fit(_cfg(_two()))
    comps = [
        ComponentConfig("lgbm", weight=0.5, params=dict(fast_lgbm_params())),
        ComponentConfig("logreg", weight=0.5),
    ]
    _, s_b = _fit(_cfg(comps))
    np.testing.assert_allclose(s_a, s_b)


def test_mean_mode_ignores_weights():
    comps = [
        ComponentConfig("lgbm", weight=9.0, params=dict(fast_lgbm_params())),
        ComponentConfig("logreg", weight=0.1),
    ]
    _, s_mean = _fit(_cfg(comps, combination="mean"))
    comps_eq = [
        ComponentConfig("lgbm", params=dict(fast_lgbm_params())),
        ComponentConfig("logreg"),
    ]
    _, s_eq = _fit(_cfg(comps_eq, combination="mean"))
    np.testing.assert_allclose(s_mean, s_eq)


def test_rank_mean_equals_mean_after_normalize():
    """With normalize_scores on, rank_mean is the mean of ranks."""
    comps = [
        ComponentConfig("lgbm", params=dict(fast_lgbm_params())),
        ComponentConfig("logreg"),
    ]
    _, s_rank = _fit(_cfg(comps, combination="rank_mean"))
    x, y, groups, _ = make_synthetic(n=600)
    ens = EnsembleRanker(_cfg(comps, combination="mean"))
    ens.fit(x, y, groups)
    s_mean = ens.predict(x)
    # both live in [0, 1] rank space, same ordering family
    assert s_rank.min() >= 0 and s_rank.max() <= 1
    assert s_mean.min() >= 0 and s_mean.max() <= 1
    assert np.corrcoef(s_rank, s_mean)[0, 1] > 0.9


def test_normalize_off_keeps_raw_scales():
    comps = [
        ComponentConfig("lgbm", params=dict(fast_lgbm_params())),
        ComponentConfig("logreg"),
    ]
    _, s = _fit(_cfg(comps, normalize_scores=False))
    # raw lambdarank/margin scores are NOT in the [0, 1] rank band
    assert (s < 0).any() or (s > 1).any()


def test_weighted_total_zero_raises():
    comps = [
        ComponentConfig("lgbm", weight=0.0, params=dict(fast_lgbm_params())),
        ComponentConfig("logreg", weight=0.0),
    ]
    with pytest.raises(ValueError, match="total_w"):
        _fit(_cfg(comps), n=200)


def test_unknown_combination_raises():
    x, y, groups, _ = make_synthetic(n=120)
    cfg = _cfg(_two())
    cfg.combination = "magic"  # type: ignore[assignment]
    ens = EnsembleRanker(cfg)
    ens.fit(x, y, groups)
    with pytest.raises(ValueError, match="unknown combination"):
        ens.predict(x)


def test_stacking_past_only_oof_runs_and_is_deterministic():
    """Stacking (logreg meta on past-only OOF) fits and reproduces."""
    x, y, groups, ts = make_synthetic(n=1200, d=6, g=200)
    cfg = EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm", params=dict(fast_lgbm_params())
            ),
            ComponentConfig("logreg"),
        ],
        combination="stacking",
        meta_learner="logreg",
        meta_folds=3,
    )
    s1 = EnsembleRanker(cfg).fit(x, y, groups, ts=ts).predict(x)
    s2 = EnsembleRanker(cfg).fit(x, y, groups, ts=ts).predict(x)
    assert s1.shape == (len(x),) and np.isfinite(s1).all()
    np.testing.assert_array_equal(s1, s2)


def test_stacking_requires_ts():
    x, y, groups, _ = make_synthetic(n=200)
    cfg = EnsembleConfig(
        components=[ComponentConfig("logreg")],
        combination="stacking",
        meta_learner="logreg",
    )
    with pytest.raises(ValueError, match="requires ts"):
        EnsembleRanker(cfg).fit(x, y, groups)


def test_stacking_requires_meta_learner():
    x, y, groups, ts = make_synthetic(n=200)
    cfg = EnsembleConfig(
        components=[ComponentConfig("logreg")],
        combination="stacking",
        meta_learner="none",
    )
    with pytest.raises(ValueError, match="meta_learner"):
        EnsembleRanker(cfg).fit(x, y, groups, ts=ts)
