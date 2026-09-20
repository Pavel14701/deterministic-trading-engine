# -*- coding: utf-8 -*-
"""Pre-close diagnostics for the OB track:

1. L x delay grid: L in {13,20,25,30,35} x delay in
   {[3,7), [5,10), [8,15)}, BTC 15m, gross R, train folds 0-3 +
   7d embargo vs test folds 4-6.  Is the EV surface coherent?
2. Per-fold EV4R, L=13 vs L=30 (delay [5,10)) - regime or structural?
3. Validated-block age distribution per segment, L=30 vs L=13 -
   why did test n drop from 31 to 23?
4. Null bootstrap of the "4 of 10 assets positive" holdout pattern.

Usage:  uv run python -m engine.experiments.ob_ldgrid
"""

from __future__ import annotations

import dataclasses
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
from engine.experiments.ob_raw_ev import _simulate_block
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


FILE = "data/okx/raw_BTC-USDT_15m.parquet"
LOOKBACKS = (13, 20, 25, 30, 35)
DELAYS = ((3, 7), (5, 10), (8, 15))
TPS = (4.0, 6.0)


def _prep(df: pl.DataFrame, ts: np.ndarray, prefix_end: int, lbk: int):
    prefix = int(np.searchsorted(ts, prefix_end))
    dfp = df[:prefix]
    pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
    hp = dfp["high"].to_numpy().astype(np.float64)
    lp = dfp["low"].to_numpy().astype(np.float64)
    cp = dfp["close"].to_numpy().astype(np.float64)
    atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
    cfg = dataclasses.replace(
        TIMEFRAME_CONFIGS["15m"],
        use_dynamic_lookback=False,
        lookback_min=lbk,
        lookback_max=lbk,
    )
    out = identify_order_blocks(dfp, cfg=cfg)
    blocks = []
    for row in out.iter_rows(named=True):
        j = pos[row["retest"]]
        blocks.append((j, row, j - pos[row["break"]], j - pos[row["start"]]))
    return pos, hp, lp, cp, atr, blocks


def _grid_cell(
    blocks: list,
    hp: np.ndarray,
    lp: np.ndarray,
    cp: np.ndarray,
    atr: np.ndarray,
    lo: int,
    hi: int,
    ts: np.ndarray,
) -> dict:
    res = {d: {tp: [] for tp in TPS} for d in DELAYS}
    for j, row, delay, _age in blocks:
        d = next((x for x in DELAYS if x[0] <= delay < x[1]), None)
        if d is None or not (lo <= ts[j] < hi) or not np.isfinite(atr[j]):
            continue
        for tp in TPS:
            sim = _simulate_block(
                hp, lp, cp, j, row["block_type"] == "supply",
                row["zone_low"], row["zone_high"], atr[j], tp,
            )
            if sim is not None:
                res[d][tp].append(sim[0])
    return res


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    cutoff = folds[4][0] - EMBARGO_DAYS * DAY_MS

    print("== 1. L x delay grid, n / EV4R / EV6R, gross ==", flush=True)
    for seg, lo, hi in (("TRAIN", 0, cutoff), ("TEST", folds[4][0], folds[-1][1])):
        print(f"-- {seg} --", flush=True)
        for lbk in LOOKBACKS:
            _pos, hp, lp, cp, atr, blocks = _prep(df, ts, hi, lbk)
            res = _grid_cell(blocks, hp, lp, cp, atr, lo, hi, ts)
            cells = []
            for d in DELAYS:
                v = res[d]
                if not v[4.0]:
                    cells.append(f"{d}: n=0")
                    continue
                cells.append(
                    f"{d}: n={len(v[4.0]):>3} "
                    f"{np.mean(v[4.0]):+.3f}/{np.mean(v[6.0]):+.3f}"
                )
            print(f"  L={lbk:<3} " + " | ".join(cells), flush=True)

    print("\n== 2. per-fold EV4R, delay [5,10) ==", flush=True)
    for lbk in (13, 30):
        evs = []
        for fi, (fs, fe) in enumerate(folds):
            _pos, hp, lp, cp, atr, blocks = _prep(df, ts, fe, lbk)
            pnl, cnt = [], 0
            for j, row, delay, _age in blocks:
                if not (fs <= ts[j] < fe) or not (5 <= delay < 10):
                    continue
                if not np.isfinite(atr[j]):
                    continue
                cnt += 1
                sim = _simulate_block(
                    hp, lp, cp, j, row["block_type"] == "supply",
                    row["zone_low"], row["zone_high"], atr[j], 4.0,
                )
                if sim is not None:
                    pnl.append(sim[0])
            ev = float(np.mean(pnl)) if pnl else np.nan
            evs.append(ev)
            print(f"  L={lbk:<3} fold {fi}: n={cnt:>3} EV4R={ev:+.3f}", flush=True)
        pos_n = int(np.nansum(np.array(evs) > 0))
        print(f"  L={lbk:<3} positive folds: {pos_n}/7", flush=True)

    print("\n== 3. validated blocks in segment, age stats (L=30 vs L=13) ==", flush=True)
    for lbk in (30, 13):
        for seg, lo, hi in (("TRAIN", 0, cutoff), ("TEST", folds[4][0], folds[-1][1])):
            _pos, _hp, _lp, _cp, atr, blocks = _prep(df, ts, hi, lbk)
            all_ages, cut_n = [], 0
            for j, _row, delay, age in blocks:
                if not (lo <= ts[j] < hi) or not np.isfinite(atr[j]):
                    continue
                all_ages.append(age)
                if 5 <= delay < 10:
                    cut_n += 1
            if all_ages:
                print(
                    f"  L={lbk:<3} {seg}: validated n={len(all_ages):>3} "
                    f"age med={np.median(all_ages):.0f} "
                    f"range [{min(all_ages)},{max(all_ages)}] "
                    f"| delay-cut survivors n={cut_n}",
                    flush=True,
                )

    print("\n== 4. null bootstrap of the holdout pattern ==", flush=True)
    ns = np.array([197, 109, 237, 275, 217, 100, 229, 191, 85], dtype=float)
    se = 1.5 / np.sqrt(ns)
    rng = np.random.default_rng(7)
    draws = rng.normal(0.0, se[:, None], size=(len(ns), 20000))
    npos = (draws > 0).sum(axis=0)
    for k in range(2, 8):
        print(f"  P({k}+ of 9 positive | true EV=0) = {np.mean(npos >= k):.2f}", flush=True)
    print("  observed on the 9 holdout assets (EV4R): 3 of 9 positive", flush=True)


if __name__ == "__main__":
    run()