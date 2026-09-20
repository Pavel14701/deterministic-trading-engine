"""Build transformer windows aligned to MTF candidates (D.2 step 1).

For every unique MTF candidate ``(entry_idx, side)`` we cut a window of
``--window`` base-TF bars ending at the decision bar ``entry_idx``
(inclusive - the bar whose close is the last known information before
the next-open fill).  Per-bar channels:

- prices: open/high/low/close normalised by the decision-bar close
  (relative moves, comparable across price levels), volume normalised
  by its trailing median;
- indicator: ATR% of the bar;
- signal: side flag (+1 long / -1 short);
- tp/sl: zeros (outcome head is retrained on MTF labels).

Target: ``y = 1`` when the best market-execution r_net over the stop
rule panel for this candidate is > 0 (the "oracle pick wins" event).
Splits are taken from the MTF parquet (same purged boundaries).

Output: ``<out>/<tag>_<base>_win.npz`` (+ json meta).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(REPO))

from ai.src.features import compute_atr  # noqa: E402
from ai.src.mtf import resample_ohlcv  # noqa: E402
from scripts.prepare_okx_dataset import (  # noqa: E402
    get_source,
    resolve_assets,
)

CHANNELS = 9  # o h l c v | atr% | side | tp sl


def build_windows(
    base: pl.DataFrame,
    atr: np.ndarray,
    cands: pl.DataFrame,
    window: int,
) -> dict:
    """Cut normalised windows for unique (entry_idx, side) candidates."""
    o = base["open"].to_numpy()
    h = base["high"].to_numpy()
    l = base["low"].to_numpy()
    c = base["close"].to_numpy()
    v = base["volume"].to_numpy()
    n = len(base)

    vol_med = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - 500)
        seg = v[lo : i + 1]
        m = np.median(seg[np.isfinite(seg)])
        vol_med[i] = m if m and m > 0 else 1.0

    # one row per candidate: entry_idx, side, split, y
    best = (
        cands.filter((pl.col("execution") == "market"))
        .filter(pl.col("r_net").is_not_nan())
        .group_by(["entry_idx", "side"])
        .agg(
            pl.col("r_net").max().alias("best_r"),
            pl.col("split").first().alias("split"),
        )
    )

    xs, ys, idxs, sides, splits = [], [], [], [], []
    for row in best.iter_rows(named=True):
        i = int(row["entry_idx"])
        if i < window - 1 or i >= n:
            continue
        w = slice(i - window + 1, i + 1)
        ref = c[i]
        if not np.isfinite(ref) or ref <= 0:
            continue
        win = np.empty((window, CHANNELS), dtype=np.float32)
        win[:, 0] = o[w] / ref - 1.0
        win[:, 1] = h[w] / ref - 1.0
        win[:, 2] = l[w] / ref - 1.0
        win[:, 3] = c[w] / ref - 1.0
        win[:, 4] = np.log1p(v[w] / max(vol_med[i], 1e-12))
        win[:, 5] = np.where(
            np.isfinite(atr[w]) & (c[w] > 0), atr[w] / c[w] - 0.01, 0.0
        )
        win[:, 6] = 1.0 if row["side"] == "long" else -1.0
        win[:, 7] = 0.0
        win[:, 8] = 0.0
        xs.append(win)
        ys.append(1 if row["best_r"] > 0 else 0)
        idxs.append(i)
        sides.append(row["side"])
        splits.append(row["split"])

    return {
        "X": np.stack(xs) if xs else np.empty((0, window, CHANNELS), np.float32),
        "y": np.asarray(ys, dtype=np.int64),
        "entry_idx": np.asarray(idxs, dtype=np.int64),
        "side": np.asarray(sides),
        "split": np.asarray(splits),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="D.2: transformer windows on MTF candidates"
    )
    ap.add_argument("--data", default="data/okx")
    ap.add_argument("--source", default="okx")
    ap.add_argument("--assets", nargs="+", default=["BTC-USDT"])
    ap.add_argument("--base", default="1h", choices=["1h", "4h"])
    ap.add_argument("--years", type=float, default=1.5)
    ap.add_argument("--mtf", default="data/mtf_dataset")
    ap.add_argument("--window", type=int, default=64)
    ap.add_argument("--out", default="data/trf_dataset")
    args = ap.parse_args()

    src = get_source(args.source)
    resolved = resolve_assets(src, args.assets, ["1m"], args.years)
    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for _name, inst_id, asset_src in resolved:
        df1m = asset_src.fetch_candles(
            inst_id,
            bar="1m",
            max_bars=int(src.bars_per_year("1m") * args.years),
            cache_dir=Path(args.data),
        )
        base = resample_ohlcv(df1m, args.base)
        atr = compute_atr(base)

        tag = inst_id.replace("-", "")
        mtf_file = REPO / args.mtf / f"{tag}_{args.base}.parquet"
        cands = pl.read_parquet(mtf_file)
        pack = build_windows(base, atr, cands, args.window)

        out_npz = out_dir / f"{tag}_{args.base}_win.npz"
        np.savez_compressed(
            out_npz,
            X=pack["X"],
            y=pack["y"],
            entry_idx=pack["entry_idx"],
            side=pack["side"],
            split=pack["split"],
        )
        counts = {s: int((pack["split"] == s).sum()) for s in ("train", "val", "test")}
        meta = {
            "asset": inst_id,
            "base": args.base,
            "window": args.window,
            "channels": CHANNELS,
            "n": int(pack["y"].size),
            "win_rate": float(pack["y"].mean()) if pack["y"].size else 0.0,
            "splits": counts,
        }
        (out_dir / f"{tag}_{args.base}_win.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        print(
            f"{inst_id} [{args.base}]: {meta['n']} windows "
            f"(win rate {meta['win_rate']:.3f}), {counts} -> {out_npz}",
            flush=True,
        )


if __name__ == "__main__":
    main()
