# -*- coding: utf-8 -*-
"""Delay-curve diagnostic on train folds: EV vs break->retest delay.

Pre-registered buckets ``[0,5) [5,10) [10,20) [20,36)`` and TPs
{3R, 4R}.  Train = WF folds 0-3 (retest strictly before
``folds[4].start - 7d embargo``), test = folds 4-6, held out.  The
train table decides whether a delay-cut passes the criterion
(bucket EV > pooled train EV + 0.03R); the test table is shown for
the SAME a priori buckets only - no re-selection.

Detection runs on the causal prefix up to each segment's end, so the
ATR median used for ``reversal_atr_multiple`` never sees beyond it.

Usage:  uv run python -m experiments.ob_delay_curve
"""

from __future__ import annotations

import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    DAY_MS,
    EMBARGO_DAYS,
    FOLD_DAYS,
    N_FOLDS,
    wf_folds,
)
from experiments.ob_raw_ev import _simulate_block
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


FILE = "data/okx/raw_BTC-USDT_15m.parquet"
TPS = (3.0, 4.0)
BUCKETS = ((0, 5), (5, 10), (10, 20), (20, 36))
N_TRAIN_FOLDS = 4


def _segment_stats(
    df: pl.DataFrame,
    ts: np.ndarray,
    retest_lo: int,
    retest_hi: int,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """Gross R at each TP for blocks with retest ts in [lo, hi)."""
    prefix = int(np.searchsorted(ts, retest_hi))
    dfp = df[:prefix]
    pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
    hp = dfp["high"].to_numpy().astype(np.float64)
    lp = dfp["low"].to_numpy().astype(np.float64)
    cp = dfp["close"].to_numpy().astype(np.float64)
    atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
    out = identify_order_blocks(dfp, cfg=TIMEFRAME_CONFIGS["15m"])
    buckets: dict[tuple[int, int], list[tuple[float, float]]] = {
        b: [] for b in BUCKETS
    }
    for row in out.iter_rows(named=True):
        j = pos[row["retest"]]
        t = ts[j]
        if not (retest_lo <= t < retest_hi):
            continue
        delay = j - pos[row["break"]]
        bk = next((b for b in BUCKETS if b[0] <= delay < b[1]), None)
        if bk is None or not np.isfinite(atr[j]):
            continue
        sim3 = _simulate_block(
            hp, lp, cp, j, row["block_type"] == "supply",
            row["zone_low"], row["zone_high"], atr[j], TPS[0],
        )
        sim4 = _simulate_block(
            hp, lp, cp, j, row["block_type"] == "supply",
            row["zone_low"], row["zone_high"], atr[j], TPS[1],
        )
        if sim3 is None or sim4 is None:
            continue
        buckets[bk].append((sim3[0], sim4[0]))
    return buckets


def _print_table(
    title: str,
    buckets: dict[tuple[int, int], list[tuple[float, float]]],
) -> None:
    print(f"\n{title}", flush=True)
    print(
        f"{'delay':>9} {'n':>5} {'EV3R':>8} {'win3R':>7} "
        f"{'EV4R':>8} {'win4R':>7}",
        flush=True,
    )
    pool: list[tuple[float, float]] = []
    for lo, hi in BUCKETS:
        v = buckets[lo, hi]
        pool.extend(v)
        if v:
            a = np.array(v)
            print(
                f"[{lo:>2},{hi:>2}) {len(v):>5} "
                f"{a[:, 0].mean():+8.3f} {np.mean(a[:, 0] > 0):>7.1%} "
                f"{a[:, 1].mean():+8.3f} {np.mean(a[:, 1] > 0):>7.1%}",
                flush=True,
            )
        else:
            print(f"[{lo:>2},{hi:>2}) {0:>5} {'-':>8} {'-':>7} {'-':>8} {'-':>7}", flush=True)
    a = np.array(pool)
    print(
        f"{'pooled':>9} {len(a):>5} "
        f"{a[:, 0].mean():+8.3f} {np.mean(a[:, 0] > 0):>7.1%} "
        f"{a[:, 1].mean():+8.3f} {np.mean(a[:, 1] > 0):>7.1%}",
        flush=True,
    )
    for k, tp in enumerate(TPS):
        best = max(
            (b for b in BUCKETS if buckets[b]),
            key=lambda b: float(np.mean(np.array(buckets[b])[:, k])),
        )
        ev_best = float(np.mean(np.array(buckets[best])[:, k]))
        ev_pool = float(a[:, k].mean())
        print(
            f"criterion TP={tp:.0f}R: best bucket {best} "
            f"EV={ev_best:+.3f} vs pooled {ev_pool:+.3f} "
            f"-> {'PASS' if ev_best > ev_pool + 0.03 else 'FAIL'} (need > +0.03)",
            flush=True,
        )


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    cutoff = folds[N_TRAIN_FOLDS][0] - EMBARGO_DAYS * DAY_MS
    test_lo = folds[N_TRAIN_FOLDS][0]
    test_hi = folds[-1][1]
    print(
        f"train: retest < {cutoff} (folds 0-{N_TRAIN_FOLDS - 1} + "
        f"{EMBARGO_DAYS}d embargo), test: folds "
        f"{N_TRAIN_FOLDS}-{len(folds) - 1}",
        flush=True,
    )
    _print_table(
        "TRAIN (decide here)",
        _segment_stats(df, ts, 0, cutoff),
    )
    _print_table(
        "TEST (held out, same buckets)",
        _segment_stats(df, ts, test_lo, test_hi),
    )


if __name__ == "__main__":
    run()