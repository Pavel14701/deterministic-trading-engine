"""Mini walk-forward: a signal-carrying panel must be ranked well.

The TZ acceptance gate in miniature: expanding past-only train, two
time folds, decile spread of the test-fold scores.  The synthetic
signal is strong enough that a healthy ensemble clears it by a wide
margin; a broken pipeline (leak, shuffled time, dropped component)
does not reproduce the spread.
"""

from __future__ import annotations

import numpy as np

from ens_synth import fast_lgbm_params, make_synthetic

from engine.ensemble.base import ComponentConfig
from engine.ensemble.combine import EnsembleConfig, EnsembleRanker


def _decile_spread(scores: np.ndarray, y: np.ndarray) -> float:
    """mean(y | top score decile) - mean(y | bottom score decile)."""
    n = len(y)
    order = np.argsort(scores)
    bottom = y[order[: n // 10]].mean()
    top = y[order[-(n // 10) :]].mean()
    return float(top - bottom)


def test_ensemble_walkforward_regression():
    """Past-only fit on fold 1 -> positive decile spread on fold 2."""
    x, y, groups, ts = make_synthetic(
        n=6000, d=10, g=600, signal=2.0, seed=11
    )
    edge = np.quantile(ts, 0.6)
    train, test = ts < edge, ts >= edge
    cfg = EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm", weight=0.5, params=dict(fast_lgbm_params())
            ),
            ComponentConfig("logreg", weight=0.5),
        ],
        combination="weighted",
    )
    ens = EnsembleRanker(cfg).fit(
        x[train], y[train], groups[train], ts=ts[train]
    )
    spread = _decile_spread(ens.predict(x[test]), y[test])
    assert spread > 0.1, f"decile spread {spread:.3f} <= 0.1"


def test_ensemble_beats_random_ranking():
    """Sanity anchor: the ensemble is better than a random ordering."""
    x, y, groups, ts = make_synthetic(
        n=6000, d=10, g=600, signal=2.0, seed=5
    )
    edge = np.quantile(ts, 0.6)
    train, test = ts < edge, ts >= edge
    cfg = EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm", weight=0.5, params=dict(fast_lgbm_params())
            ),
            ComponentConfig("logreg", weight=0.5),
        ]
    )
    ens = EnsembleRanker(cfg).fit(
        x[train], y[train], groups[train], ts=ts[train]
    )
    spread = _decile_spread(ens.predict(x[test]), y[test])
    rng = np.random.default_rng(0)
    rand_spread = _decile_spread(
        rng.normal(size=int(test.sum())), y[test]
    )
    assert spread > rand_spread


def test_single_component_switch_end_to_end():
    """Each component alone runs the same mini-WF (ablation path)."""
    x, y, groups, ts = make_synthetic(n=3000, d=8, signal=2.0)
    edge = np.quantile(ts, 0.6)
    train, test = ts < edge, ts >= edge
    for name, params in (
        ("lgbm", dict(fast_lgbm_params())),
        ("logreg", {}),
    ):
        cfg = EnsembleConfig(components=[ComponentConfig(name, params=params)])
        ens = EnsembleRanker(cfg).fit(
            x[train], y[train], groups[train], ts=ts[train]
        )
        s = ens.predict(x[test])
        assert s.shape == (int(test.sum()),)
        assert np.isfinite(s).all()
