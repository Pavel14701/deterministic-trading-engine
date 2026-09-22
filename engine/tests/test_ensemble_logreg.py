"""LogRegComponent: scaling, convergence, linearity diagnostics."""

from __future__ import annotations

import numpy as np

from ens_synth import make_synthetic

from engine.ensemble.logreg import LogRegComponent


def _comp(**kw: object) -> LogRegComponent:
    params = {"max_iter": 200}
    params.update(kw.pop("params", {}))
    return LogRegComponent(params, **kw)


def test_logreg_scaled_converges():
    """With the scaler the solver converges (TZ: scaler is mandatory)."""
    x, y, groups, _ = make_synthetic(n=800)
    m = _comp()
    m.fit(x * 1000.0, y, groups)  # brutal scale, scaler rescues it
    assert m.converged_ is True


def test_logreg_scaler_what_it_buys():
    """Scaler buys convergence under a tiny iteration budget.

    On brutal-scale features lbfgs cannot converge in 10 iterations
    without the scaler (TZ: scaler is mandatory); with it - it can.
    """
    x, y, groups, _ = make_synthetic(n=800)
    big = x * 1000.0
    m_raw = LogRegComponent({"max_iter": 10}, use_scaler=False)
    m_raw.fit(big, y, groups)
    m_scaled = LogRegComponent({"max_iter": 10}, use_scaler=True)
    m_scaled.fit(big, y, groups)
    assert m_scaled.converged_ is True
    assert m_raw.converged_ is False


def test_logreg_scores_rank_align_with_signal():
    """Decision margins rank rows by the linear signal."""
    x, y, groups, _ = make_synthetic(n=800, signal=2.0)
    m = _comp()
    m.fit(x, y, groups)
    s = m.predict(x)
    assert s.shape == (len(x),)
    top = x[:, 0] > 1.0
    assert s[top].mean() > s[~top].mean()


def test_logreg_feature_importance_is_signed():
    """Coefficients: sign matters (diagnostic contract)."""
    x, y, groups, _ = make_synthetic(n=800, signal=2.0)
    m = _comp()
    m.fit(x, y, groups)
    imp = m.feature_importance()
    assert imp is not None and imp.shape == (x.shape[1],)
    assert imp[0] > 0  # signal column gets a positive weight
    assert imp[1] < imp[0]


def test_logreg_determinism():
    x, y, groups, _ = make_synthetic(n=600)
    m1, m2 = _comp(), _comp()
    m1.fit(x, y, groups)
    m2.fit(x, y, groups)
    np.testing.assert_array_equal(m1.predict(x), m2.predict(x))
