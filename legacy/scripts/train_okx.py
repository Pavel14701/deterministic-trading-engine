"""Train the EntryExitTransformer on the OKX dataset.

Usage (from the repo root, after scripts/prepare_okx_dataset.py):

    uv run python scripts/train_okx.py \
        --data data/okx --epochs 10 --save runs/okx/best.pt

Multi-timeframe training: when the dataset was prepared with several
``--base`` grids (``meta["bases"]``), the per-base segment files are
merged into one training table - signal columns a smaller grid does not
have (higher-timeframe context of larger bases) are filled with neutral
values - and training windows are drawn through per-timeframe weights so
the 1m grid cannot drown the 15m/1H data (every base contributes ~the
same number of sampled windows per epoch).

``--bases`` selects a subset of the prepared grids.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PRICE_COLS = ["open", "high", "low", "close", "volume"]
SIG_COLS = ["dist_supply", "dist_demand"]
TP_SL_COLS = ["tp", "sl"]


def _seg_dir(data: Path, split: str, base: str | None) -> Path:
    """Segment directory for ``split``: per-base subdir in multi-TF mode."""
    return data / split / base if base else data / split


def _merge_bases(
    data: Path,
    split: str,
    bases: list[str],
    sig_union: list[str],
) -> tuple[Path, Path, Path, np.ndarray, dict[str, float]]:
    """Concatenate per-base segment files into one merged table.

    Missing signal columns are filled with neutral values: 10.0 ("zone
    far away", the feature cap) for ``dist_*`` columns, 0.0 for the rest.
    Returns merged features/labels/obs parquet paths, the per-bar
    sample-weight array balancing the timeframes, and a base->weight map.
    """
    feats: list[pl.DataFrame] = []
    labels: list[pl.DataFrame] = []
    obs_frames: list[pl.DataFrame] = []
    counts: list[int] = []
    for base in bases:
        seg = _seg_dir(data, split, base)
        f = pl.read_parquet(seg / "features.parquet")
        missing = [c for c in sig_union if c not in f.columns]
        if missing:
            f = f.hstack(
                pl.DataFrame(
                    {
                        c: pl.Series(
                            np.full(
                                f.height,
                                10.0 if "dist" in c else 0.0,
                                dtype=np.float32,
                            )
                        )
                        for c in missing
                    }
                )
            )
        feats.append(f)
        labels.append(pl.read_parquet(seg / "labels.parquet"))
        obs_frames.append(pl.read_parquet(seg / "order_blocks.parquet"))
        counts.append(f.height)

    # canonical column order: non-signal columns (identical across
    # bases) first, then the signal union - polars vstack requires the
    # very same order in every frame, and hstack appends at the end
    ref = feats[0].columns
    order = [c for c in ref if c not in sig_union] + list(sig_union)
    feats = [f.select(order) for f in feats]

    total = sum(counts)
    # Balanced tf weights: base b occupies a w_b*n_b/total share of the
    # sampler, and w_b = total/(K*n_b) gives every base an equal share.
    w_by_base = {
        b: total / (len(counts) * n)
        for b, n in zip(bases, counts, strict=True)
    }
    weights = np.concatenate(
        [np.full(n, w_by_base[b], dtype=np.float32)
         for b, n in zip(bases, counts, strict=True)]
    )

    merged = data / "_merged"
    merged.mkdir(exist_ok=True)
    f_path = merged / f"{split}_features.parquet"
    l_path = merged / f"{split}_labels.parquet"
    o_path = merged / f"{split}_order_blocks.parquet"
    pl.concat(feats, how="vertical").write_parquet(f_path)
    pl.concat(labels, how="vertical").write_parquet(l_path)
    pl.concat(obs_frames, how="vertical").write_parquet(o_path)
    return f_path, l_path, o_path, weights, w_by_base


def main() -> None:
    """Train on the chronological train/val split of the OKX dataset."""
    ap = argparse.ArgumentParser(description="Train on the OKX dataset")
    ap.add_argument("--data", default="data/okx")
    ap.add_argument(
        "--bases",
        nargs="+",
        default=None,
        help="subset of prepared base grids to train on (default: all)",
    )
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument(
        "--max-ob",
        type=int,
        default=64,
        help=(
            "cap on order blocks attached to each window (newest kept); "
            "0 disables the cap (slow on merged multi-base sets)"
        ),
    )
    ap.add_argument(
        "--epoch-windows",
        type=int,
        default=200_000,
        help=(
            "cap on training windows drawn per epoch (tf-balanced "
            "sampling keeps the base shares; 0 = full dataset per epoch)"
        ),
    )
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
    meta_path = data / "meta.json"
    if not meta_path.is_file():
        print(
            f"No meta.json under {data}: dataset not prepared yet. Run "
            "scripts/run_pipeline.py first and wait for it to finish."
        )
        sys.exit(1)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    all_bases = list(meta.get("bases") or [None])
    bases = args.bases or all_bases
    unknown = [b for b in bases if b not in all_bases]
    if unknown:
        print(f"Unknown bases {unknown}; prepared bases: {all_bases}")
        sys.exit(1)

    # Fail with a clear message when the dataset has not been prepared yet
    # (e.g. run_pipeline.py is still running and segments are not written).
    missing = [
        str(_seg_dir(data, seg, b) / f)
        for b in bases
        for seg in ("train", "val")
        for f in ("features.parquet", "labels.parquet", "order_blocks.parquet")
        if not (_seg_dir(data, seg, b) / f).is_file()
    ]
    if missing:
        print(
            f"Dataset not ready. Missing files: {missing}. Run "
            "scripts/run_pipeline.py first and wait for it to finish."
        )
        sys.exit(1)

    ind_cols = list(meta["ind_cols"])
    sig_cols = list(meta["sig_cols"] or SIG_COLS)
    per_base = meta.get("per_base") or {}
    for b in bases:
        info = per_base.get(b, {})
        print(
            f"base={b or 'default'} train={info.get('total_bars_train')} "
            f"val={info.get('total_bars_val')} "
            f"ob={info.get('n_order_blocks')}"
        )
    print(
        f"assets={list(meta['assets'])} bars={meta.get('bars')} "
        f"bases={bases} train={meta.get('total_bars_train')} "
        f"val={meta.get('total_bars_val')} "
        f"test={meta.get('total_bars_test')} "
        f"indicators={len(ind_cols)} signals={len(sig_cols)} "
        f"ob={meta['n_order_blocks']}"
    )

    weights: np.ndarray | None = None
    if len(all_bases) > 1:
        tf, tl, to, weights, w_by_base = _merge_bases(
            data, "train", bases, sig_cols
        )
        vf, vl, vo, _, _ = _merge_bases(data, "val", bases, sig_cols)
        print(
            "tf-weighted sampling: "
            + ", ".join(f"{b}={w:.2f}" for b, w in w_by_base.items())
        )
    else:
        b = bases[0]
        seg = _seg_dir(data, "train", b)
        tf, tl, to = (
            seg / "features.parquet",
            seg / "labels.parquet",
            seg / "order_blocks.parquet",
        )
        vseg = _seg_dir(data, "val", b)
        vf, vl, vo = (
            vseg / "features.parquet",
            vseg / "labels.parquet",
            vseg / "order_blocks.parquet",
        )

    save_path = REPO / args.save
    save_path.parent.mkdir(parents=True, exist_ok=True)

    quick_train(
        features=str(tf),
        labels=str(tl),
        order_blocks=str(to),
        price_cols=PRICE_COLS,
        sig_cols=sig_cols,
        tp_sl_cols=TP_SL_COLS,
        ind_cols=ind_cols,
        val_path=str(vf),
        val_labels_path=str(vl),
        val_order_blocks=str(vo),
        train_sample_weights=weights,
        epoch_windows=args.epoch_windows or None,
        max_ob=args.max_ob or None,
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
