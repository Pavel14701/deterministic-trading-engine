"""Single-command data pipeline for the OKX training dataset.

Runs the full data preparation (fetch year-scale multi-timeframe
history, featurise, detect + pass through ALL order-block fields,
label, chronological train/val/test split) and stops there -
training and evaluation are separate, manually invoked steps:

    uv run python scripts/train_okx.py --data data/okx --device cuda
    uv run python scripts/eval_okx.py --data data/okx

All arguments are forwarded to prepare_okx_dataset.main().
"""

from __future__ import annotations

import sys

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.prepare_okx_dataset import main  # noqa: E402


if __name__ == "__main__":
    main()
