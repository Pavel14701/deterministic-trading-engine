# -*- coding: utf-8 -*-
"""Fresh-asset holdout: run the pre-registered working point as-is.

Working point fixed BEFORE the run (BTC train folds only):
delay in [5, 10), lookback 30 static (use_dynamic_lookback=False -
dynamic would be per-asset adaptation), revATR 2.5, cw 36 (presets),
TP {4R, 6R} only, stop = zone edge + 0.25 ATR, horizon 48, gross R.
No tuning on holdout assets, no pooling before per-asset readout.

Usage:  uv run python -m engine.experiments.ob_holdout_assets
"""

from __future__ import annotations

import dataclasses
import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from engine.experiments.ob_raw_ev import _simulate_block
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


PRIMARY = ("AVAX-USDT", "BNB-USDT", "SOL-USDT", "ETH-USDT")
SECONDARY = (
    "DOGE-USDT",
    "LINK-USDT",
    "LTC-USDT",
    "NEAR-USDT",
    "XRP-USDT",
)
TPS = (4.0, 6.0)
DELAY_CUT = (5, 10)


def run_asset(asset: str) -> None:
    path = REPO / f"data/okx21/raw_{asset}_15m.parquet"
    df = pl.read_parquet(path).rename({"ts": "date"})
    pos = {d: i for i, d in enumerate(df["date"].to_list())}
    hp = df["high"].to_numpy().astype(np.float64)
    lp = df["low"].to_numpy().astype(np.float64)
    cp = df["close"].to_numpy().astype(np.float64)
    atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
    cfg = dataclasses.replace(
        TIMEFRAME_CONFIGS["15m"],
        use_dynamic_lookback=False,
        lookback_min=30,
        lookback_max=30,
    )
    out = identify_order_blocks(df, cfg=cfg)
    res: dict[float, list[float]] = {tp: [] for tp in TPS}
    delays: list[float] = []
    for row in out.iter_rows(named=True):
        j = pos[row["retest"]]
        delay = j - pos[row["break"]]
        if not (DELAY_CUT[0] <= delay < DELAY_CUT[1]):
            continue
        if not np.isfinite(atr[j]):
            continue
        delays.append(float(delay))
        for tp in TPS:
            sim = _simulate_block(
                hp, lp, cp, j, row["block_type"] == "supply",
                row["zone_low"], row["zone_high"], atr[j], tp,
            )
            if sim is not None:
                res[tp].append(sim[0])
    n = len(res[TPS[0]])
    days = (ts_last_ms(df) - ts_first_ms(df)) / DAY
    if n == 0:
        print(f"{asset:<11} n=0 (skipped, {days:.0f}d)", flush=True)
        return
    cells = "  ".join(
        f"{tp:.0f}R:{np.mean(res[tp]):+.3f}/{np.mean(np.array(res[tp]) > 0):.0%}"
        for tp in TPS
    )
    print(
        f"{asset:<11} n={n:>3} ({days:.0f}d)  {cells}"
        f"  delay med={np.median(delays):.0f}",
        flush=True,
    )


DAY = 86_400_000


def ts_first_ms(df: pl.DataFrame) -> float:
    return float(df["date"][0])


def ts_last_ms(df: pl.DataFrame) -> float:
    return float(df["date"][-1])


def run() -> None:
    print(
        "fixed working point: delay [5,10), L=30 static, revATR=2.5, "
        f"cw=36, TP {TPS}, gross R (no taker)",
        flush=True,
    )
    print("\nPRIMARY (pre-registered criterion >=3/4 gross>0):", flush=True)
    for a in PRIMARY:
        run_asset(a)
    print("\nSECONDARY (bonus, same fixed point):", flush=True)
    for a in SECONDARY:
        run_asset(a)


if __name__ == "__main__":
    run()