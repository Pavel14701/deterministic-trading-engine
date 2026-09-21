# -*- coding: utf-8 -*-
"""Phase 1 (reduced, pre-registered): BTC-only lookback recalibration.

Arms (all with delay [5,10), TP {4R, 6R}, revATR 2.5, zone 0.2):
  A (baseline)  lookback=30 static, cw=36   - prior working point
  B (ablation)  lookback=13 static, cw=36   - isolates the lookback
  C (primary)   lookback=13 static, cw=54   - full pre-registered arm

Decision on train (folds 0-3 + 7d embargo); test folds 4-6 readout.
Usage:  uv run python -m experiments.ob_lookback13
"""

from __future__ import annotations

import dataclasses
import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
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
ARMS = {
    "A: L=30, cw=36 (base)": (30, 36),
    "B: L=13, cw=36 (abl)": (13, 36),
    "C: L=13, cw=54 (prim)": (13, 54),
}
TPS = (4.0, 6.0)
DELAY_CUT = (5, 10)


def _arm(
    df: pl.DataFrame,
    ts: np.ndarray,
    retest_lo: int,
    retest_hi: int,
    lookback: int,
    cw: int,
) -> tuple[int, dict[float, list[float]], list[int]]:
    prefix = int(np.searchsorted(ts, retest_hi))
    dfp = df[:prefix]
    pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
    hp = dfp["high"].to_numpy().astype(np.float64)
    lp = dfp["low"].to_numpy().astype(np.float64)
    cp = dfp["close"].to_numpy().astype(np.float64)
    atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
    base = TIMEFRAME_CONFIGS["15m"]
    cfg = dataclasses.replace(
        base,
        use_dynamic_lookback=False,
        lookback_min=lookback,
        lookback_max=lookback,
        confirmation_window=cw,
    )
    out = identify_order_blocks(dfp, cfg=cfg)
    res: dict[float, list[float]] = {tp: [] for tp in TPS}
    delays: list[int] = []
    for row in out.iter_rows(named=True):
        j = pos[row["retest"]]
        if not (retest_lo <= ts[j] < retest_hi):
            continue
        delay = j - pos[row["break"]]
        if not (DELAY_CUT[0] <= delay < DELAY_CUT[1]):
            continue
        if not np.isfinite(atr[j]):
            continue
        delays.append(delay)
        for tp in TPS:
            sim = _simulate_block(
                hp, lp, cp, j, row["block_type"] == "supply",
                row["zone_low"], row["zone_high"], atr[j], tp,
            )
            if sim is not None:
                res[tp].append(sim[0])
    return len(res[TPS[0]]), res, delays


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    cutoff = folds[4][0] - EMBARGO_DAYS * DAY_MS
    print(
        f"BTC 15m, pre-registered arms {list(ARMS)}, delay {DELAY_CUT}, "
        f"TP {TPS}, gross",
        flush=True,
    )
    for name, (lbk, cw) in ARMS.items():
        for seg, lo, hi in (
            ("TRAIN", 0, cutoff),
            ("TEST ", folds[4][0], folds[-1][1]),
        ):
            n, res, delays = _arm(df, ts, lo, hi, lbk, cw)
            cells = "  ".join(
                f"{tp:.0f}R:{np.mean(res[tp]):+.3f}/"
                f"{np.mean(np.array(res[tp]) > 0):.0%}"
                for tp in TPS
            )
            print(
                f"{name}  {seg}  n={n:>3}  {cells}"
                f"  delay med={np.median(delays):.0f} p90={np.percentile(delays, 90):.0f}",
                flush=True,
            )


if __name__ == "__main__":
    run()