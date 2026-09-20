"""Stacking meta-learner: OOF geometry, guards, both meta kinds."""

from __future__ import annotations

import numpy as np
import pytest

from ens_synth import fast_lgbm_params, make_synthetic

from engine.ensemble.base import ComponentConfig
from engine.ensemble.meta import StackingMeta, oof_score_matrix


def _comps() -> list[ComponentConfig]:
    return [
        ComponentConfig("lgbm", params=dict(fast_lgbm_params())),
        ComponentConfig("logreg"),
    ]


def test_stacking_meta_predict_before_fit_raises():
    meta = StackingMeta("logreg")
    with pytest.raises(RuntimeError, match="not fitted"):
        meta.predict(np.zeros((3, 2)))


def test_stacking_meta_unknown_kind_raises():
    meta = StackingMeta("none")
    with pytest.raises(ValueError, match="meta_learner"):
        meta.fit(np.zeros((5, 2)), np.zeros(5))


def test_stacking_meta_logreg_blend():
    """logreg meta: margins monotone in the dominant score column."""
    oof = np.column_stack([np.linspace(-2, 2, 40), np.zeros(40)])
    y = (oof[:, 0] > 0).astype(np.float32) * 2 - 1
    meta = StackingMeta("logreg")
    meta.fit(oof, y)
    s = meta.predict(np.column_stack([np.linspace(-2, 2, 40),
                                      np.zeros(40)]))
    assert s.shape == (40,) and np.all(np.diff(s) > 0)


def test_stacking_meta_ridge_blend():
    """ridge meta: blended score rises with the positive column.

    alpha=1.0 shrinks the weights, so the assertion is directional
    (monotone in col 0), not an exact linear recovery.
    """
    oof = np.column_stack([np.linspace(-1, 1, 30), np.linspace(1, -1, 30)])
    y = 2.0 * oof[:, 0] - oof[:, 1]
    meta = StackingMeta("ridge")
    meta.fit(oof, y)
    grid = np.column_stack([np.linspace(-1, 1, 30), np.zeros(30)])
    s = meta.predict(grid)
    assert s.shape == (30,)
    assert np.all(np.diff(s) > 0)  # rises with col 0
    assert s[-1] > s[0] + 1.0  # and the spread survives shrinkage


def test_oof_needs_two_folds():
    x, y, groups, ts = make_synthetic(n=300)
    with pytest.raises(ValueError, match="n_folds >= 2"):
        oof_score_matrix(_comps(), x, y, groups, ts, n_folds=1)


def test_oof_degenerate_time_span_raises():
    """All rows at one instant: no past-only tiles can be cut."""
    x, y, groups, ts = make_synthetic(n=300)
    flat = np.full(len(ts), ts[0])
    with pytest.raises(ValueError, match="time span too short"):
        oof_score_matrix(_comps(), x, y, groups, flat, n_folds=3)


def test_oof_matrix_geometry_and_past_only():
    """OOF covers only rows after the first boundary, all columns."""
    x, y, groups, ts = make_synthetic(n=1200, d=5, g=200)
    n_folds = 4
    oof, row_ix = oof_score_matrix(
        _comps(), x, y, groups, ts, n_folds=n_folds
    )
    boundary = np.quantile(ts, 1.0 / n_folds)
    # rows strictly before the first tile boundary are never scored
    assert (ts[row_ix] >= boundary).all()
    # scored rows are exactly the rows after it
    expected = np.where(ts >= boundary)[0]
    np.testing.assert_array_equal(row_ix, expected)
    assert oof.shape == (len(expected), 2)
    assert np.isfinite(oof).all()


def test_oof_is_deterministic():
    x, y, groups, ts = make_synthetic(n=600, d=5, g=100)
    o1, r1 = oof_score_matrix(_comps(), x, y, groups, ts, n_folds=3)
    o2, r2 = oof_score_matrix(_comps(), x, y, groups, ts, n_folds=3)
    np.testing.assert_array_equal(o1, o2)
    np.testing.assert_array_equal(r1, r2)
