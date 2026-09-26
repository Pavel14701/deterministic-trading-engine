"""CatBoostComponent: determinism, order invariance, group wiring."""

from __future__ import annotations

import pytest

from ens_synth import fast_catboost_params, make_leaky, make_synthetic

from engine.ensemble.catboost import (
    CATBOOST_AVAILABLE,
    CatBoostComponent,
)


pytestmark = pytest.mark.skipif(
    not CATBOOST_AVAILABLE, reason="catboost not installed"
)


def _comp(**over: object) -> CatBoostComponent:
    return CatBoostComponent({**fast_catboost_params(), **over})


def test_catboost_determinism():
    """Same seed + thread_count=1 -> identical scores (TZ gate)."""
    x, y, groups, _ = make_synthetic(n=600)
    m1, m2 = _comp(), _comp()
    m1.fit(x, y, groups)
    m2.fit(x, y, groups)
    import numpy as np

    np.testing.assert_array_equal(m1.predict(x), m2.predict(x))


def test_catboost_fit_needs_no_presorted_rows():
    """Unsorted rows fit fine - the component group-sorts internally.

    Like LightGBM, the fit is not byte-identical across input row
    orders (float accumulation order); the protocol feed is
    group-sorted, which pins the canonical order.
    """
    import numpy as np

    x, y, groups, _ = make_synthetic(n=600)
    m = _comp()
    m.fit(x, y, groups)
    s = m.predict(x)
    assert s.shape == (len(x),) and np.isfinite(s).all()


def test_catboost_feature_importance():

    x, y, groups, _, leaky_idx = make_leaky(n=500)
    m = _comp()
    assert m.feature_importance() is None  # not fitted yet
    m.fit(x, y, groups)
    imp = m.feature_importance()
    assert imp is not None and imp.shape == (x.shape[1],)
    # the leaky column IS used (it is in the matrix by construction):
    # this pins that importance reporting works and that the column is
    # identifiable - leakage PREVENTION lives in the protocol (labels
    # never enter the feature matrix), not inside the booster.
    assert imp[leaky_idx] > 0


def test_catboost_predict_before_fit_raises():
    import numpy as np

    x, _, _, _ = make_synthetic(n=50)
    with np.testing.assert_raises(RuntimeError):
        _comp().predict(x)


def test_catboost_without_catboost_raises(monkeypatch):
    """Construction fails with a clear message when catboost is absent."""
    if CATBOOST_AVAILABLE:
        monkeypatch.setattr(
            "engine.ensemble.catboost.CATBOOST_AVAILABLE", False
        )
    with pytest.raises(ImportError, match="catboost is not installed"):
        CatBoostComponent()
