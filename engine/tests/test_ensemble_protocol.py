"""Protocol integration: ensemble as a drop-in for the WF head.

``train_ensemble_ranker`` mirrors ``train_ranker``'s contract: fit on
past-only rows, score ALL rows in input order - so the replay path
(replay / fit_rule_table / state machine) is unchanged and the
experiments switch heads by config alone.
"""

from __future__ import annotations

import numpy as np

from ens_synth import fast_lgbm_params

from engine.backtest.protocol import (
    ENCODING_ZEROED,
    RankerData,
    assemble_ranker_data,
    train_ensemble_ranker,
)
from engine.ensemble.base import ComponentConfig
from engine.ensemble.combine import EnsembleConfig


def _fake_asset_dict(
    x: np.ndarray, y: np.ndarray, ts: np.ndarray
) -> dict[str, object]:
    """Minimal load_asset-shaped stub for assemble_ranker_data."""
    import pandas as pd
    import polars as pl

    feats = pd.DataFrame(
        x, columns=[f"f{i}" for i in range(x.shape[1])]
    )
    feats["risk_pct"] = 0.01
    feats["cost_R"] = 0.05
    panel_cols = {
        "r_pess": y,
        "ts": ts,
        "_cand": [f"c{i}" for i in range(len(y))],
    }
    return {
        "feats": feats,
        "panel": pl.DataFrame(panel_cols),
        "n": 10,
        "o": np.zeros(10),
        "h": np.zeros(10),
        "l": np.zeros(10),
        "c": np.zeros(10),
        "rows_raw": len(y),
        "tag": "FAKE",
    }


def test_train_ensemble_ranker_scores_all_rows():
    """Contract: scores for ALL rows, finite, input order preserved."""
    from ens_synth import make_synthetic

    x, y, _, ts = make_synthetic(n=1200, d=6, g=200)
    groups = np.repeat(np.arange(200), 6)
    rd = RankerData(
        x=x.astype(np.float64),
        y=y.astype(np.float64),
        ts=ts.astype(np.float64),
        asset_row=np.zeros(len(y), dtype=np.int64),
        row=groups.astype(np.int64),
    )
    cfg = EnsembleConfig(
        components=[
            ComponentConfig(
                "lgbm", params=dict(fast_lgbm_params())
            ),
            ComponentConfig("logreg"),
        ]
    )
    tr = np.arange(0, 900)
    sc = train_ensemble_ranker(rd.x, rd.y, rd.row, rd.ts, tr, cfg)
    assert sc.shape == (len(y),)
    assert np.isfinite(sc).all()
    # past-only contract: train rows scored, test rows scored too
    assert np.isfinite(sc[900:]).all()


def test_assemble_ranker_data_feeds_ensemble():
    """The protocol's own assembler output fits the ensemble directly."""
    import numpy as np

    from ens_synth import make_synthetic

    x, y, _, ts = make_synthetic(n=600, d=5, g=100)
    data = {"FAKE": _fake_asset_dict(x, y, ts)}
    rd = assemble_ranker_data(data, ["FAKE"], ENCODING_ZEROED)
    assert rd.x.shape == (600, 5 + 3)  # + risk_pct, cost_R, asset columns
    cfg = EnsembleConfig(components=[ComponentConfig("logreg")])
    tr = np.where(rd.ts < np.quantile(rd.ts, 0.6))[0]
    sc = train_ensemble_ranker(rd.x, rd.y, rd.row, rd.ts, tr, cfg)
    assert sc.shape == (600,)
    assert np.isfinite(np.asarray(sc)).all()
