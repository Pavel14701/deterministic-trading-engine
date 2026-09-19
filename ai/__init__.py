"""dte-ai: research library of the trading pipeline.

Live modules (everything else lives in ``legacy/``):
- ``config``     - YAML config, seeds, risk kwargs;
- ``datatypes``  - OrderBlock dataclass;
- ``features``   - ATR, order-block features, strategy label simulator;
- ``io``         - parquet I/O for features / labels / order blocks;
- ``candidates`` - stop/TP candidate grid;
- ``mtf``        - OHLCV resampling (1m -> higher timeframes);
- ``mtf_dataset``- multi-timeframe panel builder;
- ``mtf_model``  - LGBM ranker, feature builders, rule tables;
- ``state_machine``- portfolio slot state machine (FCFS / REPLACE);
- ``transformer``- EntryExitTransformer (parked, kept for D.8 evidence);
- ``marketdata`` - OKX candle sources.
"""

from .config import (
    AIConfig,
    ComputeConfig,
    ModelConfig,
    RiskConfig,
    TrainingConfig,
    load_config,
    risk_kwargs,
    set_seed,
)
from .datatypes import OrderBlock
from .features import (
    compute_atr,
    compute_ob_distances,
    compute_tp_sl,
    generate_labels_from_strategy,
)
from .io import (
    load_features_parquet,
    load_labels_parquet,
    load_order_blocks_parquet,
    merge_features_labels,
    save_labels_parquet,
)
from .transformer import EntryExitTransformer


__all__ = [
    "AIConfig",
    "ComputeConfig",
    "EntryExitTransformer",
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
