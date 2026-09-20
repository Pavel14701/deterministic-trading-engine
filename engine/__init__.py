"""dte-engine: research library of the trading pipeline.

Layout (subpackages by function):
- ``infra``      - YAML config, core datatypes, parquet I/O, OKX sources;
- ``features``   - indicators, MTF resampling, panel builders, DSL
                   feed/spec/provider, MFE/MAE event collector;
- ``structure``  - zone geometry and entry-candidate detectors;
- ``sim``        - unified event sim, maker entries, state machine,
                   admission policies;
- ``backtest``   - walk-forward protocol (folds, ranker, replay);
- ``model``      - LGBM ranker head, feature builders, rule tables;
- ``metrics``    - per-trade R performance metrics;
- ``datasets``   - dataset assembly pipelines from raw OKX caches;
- ``experiments``- reproducible experiment drivers (runnable modules).
"""

from engine.features.indicators import (
    compute_atr,
    compute_ob_distances,
    compute_tp_sl,
    generate_labels_from_strategy,
)
from engine.infra.config import (
    AIConfig,
    ComputeConfig,
    ModelConfig,
    RiskConfig,
    TrainingConfig,
    load_config,
    risk_kwargs,
    set_seed,
)
from engine.infra.datatypes import OrderBlock
from engine.infra.io import (
    load_features_parquet,
    load_labels_parquet,
    load_order_blocks_parquet,
    merge_features_labels,
    save_labels_parquet,
)


__all__ = [
    "AIConfig",
    "ComputeConfig",
    "ModelConfig",
    "OrderBlock",
    "RiskConfig",
    "TrainingConfig",
    "compute_atr",
    "compute_ob_distances",
    "compute_tp_sl",
    "generate_labels_from_strategy",
    "load_config",
    "load_features_parquet",
    "load_labels_parquet",
    "load_order_blocks_parquet",
    "merge_features_labels",
    "risk_kwargs",
    "save_labels_parquet",
    "set_seed",
]
