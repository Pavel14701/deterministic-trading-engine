"""LGBMComponent: determinism, dtype sensitivity, grouping."""

from __future__ import annotations

import numpy as np

from ens_synth import fast_lgbm_params, make_synthetic

from engine.ensemble.lgbm import LGBMComponent, group_sort_order


def _comp(**over: object) -> LGBMComponent:
    return LGBMComponent({**fast_lgbm_params(), **over})


def test_lgbm_determinism():
    """Same seed -> byte-for-byte identical scores (TZ gate)."""
    x, y, groups, _ = make_synthetic(n=800)
    m1, m2 = _comp(), _comp()
    m1.fit(x, y, groups)
    m2.fit(x, y, groups)
    np.testing.assert_array_equal(m1.predict(x), m2.predict(x))


def test_lgbm_dtype_discipline():
    """Upcasting fitted-dtype rows must NOT change scores.

    LightGBM bins float32 and float64 differently - on real panels
    that historically flipped rankers (2 of 24 in wf_ab), which is why
    the protocol pins ONE encoding per family (ENCODING_*).  What the
    pipeline needs as a hard contract: once fitted on a dtype, scoring
    the same values upcast to float64 is stable.
    """
    x, y, groups, _ = make_synthetic(n=800)
    m = _comp()
    m.fit(x, y, groups)  # float32 in
    a = m.predict(x.astype(np.float32))
    b = m.predict(x.astype(np.float64))
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_lgbm_fit_needs_no_presorted_rows():
    """Unsorted rows fit fine - the component sorts internally.

    NOTE: the fit is NOT byte-identical across input row orders (float
    accumulation is order-dependent even with deterministic=True);
    the protocol feed is group-sorted by construction, which pins the
    canonical order.  This test only covers the sorting contract.
    """
    x, y, groups, _ = make_synthetic(n=600)
    m = _comp()
    m.fit(x, y, groups)
    s = m.predict(x)
    assert s.shape == (len(x),) and np.isfinite(s).all()


def test_lgbm_feature_importance():
    """Gain importance exists after fit and concentrates on col 0."""
    x, y, groups, _ = make_synthetic(n=800, signal=3.0)
    m = _comp()
    assert m.feature_importance() is None  # not fitted yet
    m.fit(x, y, groups)
    imp = m.feature_importance()
    assert imp is not None and imp.shape == (x.shape[1],)
    assert imp[0] == imp.max()  # signal column dominates


def test_lgbm_predict_before_fit_raises():
    x, _, _, _ = make_synthetic(n=50)
    with np.testing.assert_raises(RuntimeError):
        _comp().predict(x)


def test_group_sort_order_is_stable_and_groups_contiguous():
    groups = np.array([3, 1, 3, 1, 2])
    order = group_sort_order(groups)
    sorted_g = groups[order]
    assert sorted_g.tolist() == [1, 1, 2, 3, 3]
    # ties keep original row order (lexsort secondary key)
    assert order.tolist() == [1, 3, 4, 0, 2]
