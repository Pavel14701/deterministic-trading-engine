"""Train the EntryExitTransformer on the OKX dataset.

Usage (from the repo root, after scripts/prepare_okx_dataset.py):

    uv run python scripts/train_okx.py \
        --data data/okx --epochs 10 --save runs/okx/best.pt

Reads features/labels/order_blocks produced by the preparation script and
the ``ind_cols`` list from meta.json; trains via ai.src.quickstart
(config defaults from configs/ai.yaml, overridable by CLI flags).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PRICE_COLS = ["open", "high", "low", "close", "volume"]
SIG_COLS = ["dist_supply", "dist_demand"]
TP_SL_COLS = ["tp", "sl"]


def main() -> None:
    """Train on the chronological train/val split of the OKX dataset."""
    ap = argparse.ArgumentParser(description="Train on the OKX dataset")
    ap.add_argument("--data", default="data/okx")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--seq-len", type=int, default=None)
    ap.add_argument(
        "--device", default=None, help="'cuda' / 'cpu' (auto if unset)"
    )
    ap.add_argument("--save", default="runs/okx/best.pt")
    ap.add_argument("--log-dir", default="runs/okx/tb")
    args = ap.parse_args()

    # ai.src logs epoch summaries via `logger.info`; without a handler the
    # manual training run would print nothing at all.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from ai.src.quickstart import quick_train  # heavy torch import, keep lazy

    data = REPO / args.data

    # Fail with a clear message when the dataset has not been prepared yet
    # (e.g. run_pipeline.py is still running and train/val/test are empty).
    missing = [
        str(data / seg / f)
        for seg in ("train", "val")
        for f in ("features.parquet", "labels.parquet", "order_blocks.parquet")
        if not (data / seg / f).is_file()
    ]
    if missing:
        import sys

        print(
            "Dataset not ready. Missing files (relative to "
            f"{data}): {missing}. Run scripts/run_pipeline.py first and wait "
            "for it to finish before training."
        )
        sys.exit(1)

    meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    ind_cols = list(meta["ind_cols"])
    sig_cols = list(meta.get("sig_cols") or SIG_COLS)
    print(
        f"assets={list(meta['assets'])} bars={meta.get('bars')} "
        f"train={meta.get('total_bars_train')} "
        f"val={meta.get('total_bars_val')} "
        f"test={meta.get('total_bars_test')} "
        f"indicators={len(ind_cols)} signals={len(sig_cols)} "
        f"ob={meta['n_order_blocks']}"
    )

    save_path = REPO / args.save
    save_path.parent.mkdir(parents=True, exist_ok=True)

    quick_train(
        features=str(data / "train" / "features.parquet"),
        labels=str(data / "train" / "labels.parquet"),
        order_blocks=str(data / "train" / "order_blocks.parquet"),
        price_cols=PRICE_COLS,
        sig_cols=sig_cols,
        tp_sl_cols=TP_SL_COLS,
        ind_cols=ind_cols,
        val_path=str(data / "val" / "features.parquet"),
        val_labels_path=str(data / "val" / "labels.parquet"),
        val_order_blocks=str(data / "val" / "order_blocks.parquet"),
        epochs=args.epochs,
        batch_size=args.batch_size,
        seq_len=args.seq_len,
        device=args.device,
        save_best_path=str(save_path),
        log_dir=str(REPO / args.log_dir) if args.log_dir else None,
    )
    print(f"trained model saved -> {save_path}")


if __name__ == "__main__":
    main()
