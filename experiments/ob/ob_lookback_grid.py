# -*- coding: utf-8 -*-
"""Lookback calibration grid (train-fold diagnostics, step 2).

Pre-registered: lookback L in {15, 20, 25, 30, 35, 40} (static,
``use_dynamic_lookback=False``), delay-cut [5, 10) from step 1 fixed,
TP grid {2, 2.5, 3, 3.5, 4, 5}R.  Train = WF folds 0-3 + 7d embargo
(decision segment), test = folds 4-6 held out, same a priori cells.
L=30 static ~ the dynamic preset (2 * median ATR clamps to 30).

Usage:  uv run python -m experiments.ob_lookback_grid
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import polars as pl

from experiments import REPO


sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    DAY_MS,
    EMBARGO_DAYS,
    FOLD_DAYS,
    N_FOLDS,
    wf_folds,
)
from experiments.ob.ob_raw_ev import _simulate_block
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


FILE = "data/okx/raw_BTC-USDT_15m.parquet"
LOOKBACKS = (15, 20, 25, 30, 35, 40)
TPS = (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
DELAY_CUT = (5, 10)
N_TRAIN_FOLDS = 4


def _grid(
    df: pl.DataFrame,
    ts: np.ndarray,
    retest_lo: int,
    retest_hi: int,
) -> dict[int, dict[float, list[float]]]:
    """{L: {tp: [pnl_R, ...]}} for blocks with retest in [lo, hi)."""
    prefix = int(np.searchsorted(ts, retest_hi))
    dfp = df[:prefix]
    pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
    hp = dfp["high"].to_numpy().astype(np.float64)
    lp = dfp["low"].to_numpy().astype(np.float64)
    cp = dfp["close"].to_numpy().astype(np.float64)
    atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
    res: dict[int, dict[float, list[float]]] = {}
    base = TIMEFRAME_CONFIGS["15m"]
    for lbk in LOOKBACKS:
        cfg = dataclasses.replace(
            base,
            use_dynamic_lookback=False,
            lookback_min=lbk,
            lookback_max=lbk,
        )
        out = identify_order_blocks(dfp, cfg=cfg)
        res[lbk] = {tp: [] for tp in TPS}
        for row in out.iter_rows(named=True):
            j = pos[row["retest"]]
            if not (retest_lo <= ts[j] < retest_hi):
                continue
            delay = j - pos[row["break"]]
            if not (DELAY_CUT[0] <= delay < DELAY_CUT[1]):
                continue
            if not np.isfinite(atr[j]):
                continue
            for tp in TPS:
                sim = _simulate_block(
                    hp, lp, cp, j, row["block_type"] == "supply",
                    row["zone_low"], row["zone_high"], atr[j], tp,
                )
                if sim is not None:
                    res[lbk][tp].append(sim[0])
    return res


def _print_table(title: str, res: dict[int, dict[float, list[float]]]) -> None:
    print(f"\n{title}", flush=True)
    header = f"{'L':>3} {'n':>4} " + " ".join(f"{'EV' + format(t):>7}" for t in TPS) + "  win3R"
    print(header, flush=True)
    for lbk in LOOKBACKS:
        tp_map = res[lbk]
        n = len(tp_map[3.0])
        if n == 0:
            print(
                f"{lbk:>3} {0:>4} " + " ".join(f"{'-':>7}" for _ in TPS),
                flush=True,
            )
            continue
        cells = []
        for tp in TPS:
            v = tp_map[tp]
            cells.append(f"{np.mean(v):+7.3f}" if v else f"{'-':>7}")
        win3 = float(np.mean(np.array(tp_map[3.0]) > 0))
        print(f"{lbk:>3} {n:>4} " + " ".join(cells) + f"  {win3:.1%}", flush=True)


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    cutoff = folds[N_TRAIN_FOLDS][0] - EMBARGO_DAYS * DAY_MS
    test_lo = folds[N_TRAIN_FOLDS][0]
    test_hi = folds[-1][1]
    print(
        f"delay-cut {DELAY_CUT}, L grid {LOOKBACKS}, TP {TPS}; "
        f"train retest < {cutoff}, test folds {N_TRAIN_FOLDS}-{len(folds) - 1}",
        flush=True,
    )
    _print_table("TRAIN (decide here)", _grid(df, ts, 0, cutoff))
    _print_table("TEST (held out, same cells)", _grid(df, ts, test_lo, test_hi))


if __name__ == "__main__":
    run()