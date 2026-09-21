# -*- coding: utf-8 -*-
"""Phase-0 structural diagnostics: do assets differ in microstructure
timing, without running the OB pipeline decision machinery?

Pre-registered metric set (per asset, 15m):

- bars_per_ATR     median(ATR / |dClose|) - bars needed for one ATR move
- half_life_ar1    AR(1) on |log ret|, rolling 500, median phi;
                   HL = ln(0.5)/ln(phi)  (the Phase-1 ``impulse`` input)
- half_life_acf    literal spec: first lag with ACF(log ret) < 0.5
- pivot_lag_p50/90 confirm_idx - pivot_idx from OnlineZigZag with the
                   pipeline reversal threshold (revATR x median ATR)
- retest_p90       p90(retest - break) from default-cfg validation on
                   train folds 0-3 (+7d embargo), causal prefix
- spread_ratio     median((high-low) / close / ATR)
- volume_irreg     p90(volume) / p10(volume)
- gap_freq         share of bars with |open - prev_close| > 0.5 ATR

EV columns are the measured holdout gross EVs (fixed working point,
runs/ob_holdout_assets.log) - used only for Spearman correlation.

Usage:  uv run python -m experiments.ob_struct_diagnostics
"""

from __future__ import annotations

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
from ta.src.custom.market_structure import identify_order_blocks, online_zigzag
from ta.src.custom.market_structure.blocks import effective_online_reversal
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


ASSETS = (
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "BNB-USDT",
    "AVAX-USDT",
    "DOGE-USDT",
    "XRP-USDT",
    "LINK-USDT",
    "LTC-USDT",
    "NEAR-USDT",
)
# measured holdout gross EV at the fixed working point
# (delay [5,10), L=30, TP 4R/6R); see runs/ob_holdout_assets.log
EV4 = {
    "BTC-USDT": 0.348,
    "ETH-USDT": 0.178,
    "SOL-USDT": -0.069,
    "BNB-USDT": -0.177,
    "AVAX-USDT": 0.024,
    "DOGE-USDT": 0.270,
    "XRP-USDT": 0.105,
    "LINK-USDT": 0.044,
    "LTC-USDT": -0.155,
    "NEAR-USDT": -0.119,
}
EV6 = {
    "BTC-USDT": 0.405,
    "ETH-USDT": 0.139,
    "SOL-USDT": -0.120,
    "BNB-USDT": -0.191,
    "AVAX-USDT": -0.038,
    "DOGE-USDT": 0.265,
    "XRP-USDT": 0.186,
    "LINK-USDT": -0.008,
    "LTC-USDT": -0.135,
    "NEAR-USDT": -0.096,
}
ROLL = 500


def _half_life_acf(ret: np.ndarray) -> int:
    r = ret - ret.mean()
    denom = float(r @ r)
    for lag in range(1, 50):
        num = float(r[lag:] @ r[:-lag])
        if num / denom < 0.5:
            return lag
    return 50


def _half_life_ar1(absret: np.ndarray) -> float:
    phis: list[float] = []
    for k in range(ROLL, len(absret)):
        y, x = absret[k - ROLL : k], absret[k - ROLL + 1 : k + 1]
        vx = float(np.var(y))
        if vx <= 0:
            continue
        phi = float(np.cov(y, x)[0, 1] / vx)
        if 0.05 < phi < 0.995:
            phis.append(phi)
    if not phis:
        return np.nan
    phi = float(np.median(phis))
    return float(np.log(0.5) / np.log(phi))


def _pivot_lags(hp: np.ndarray, lp: np.ndarray, rev: float) -> tuple[float, float]:
    zz = online_zigzag.OnlineZigZag(reversal=rev)
    for i in range(len(hp)):
        zz.update(float(hp[i]), float(lp[i]))
    lags = [p.confirm_idx - p.idx for p in zz.confirmed]
    if not lags:
        return np.nan, np.nan
    return float(np.percentile(lags, 50)), float(np.percentile(lags, 90))


def _retest_p90(df: pl.DataFrame, ts: np.ndarray, cutoff: int) -> float:
    prefix = int(np.searchsorted(ts, cutoff))
    dfp = df[:prefix]
    pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
    out = identify_order_blocks(dfp, cfg=TIMEFRAME_CONFIGS["15m"])
    delays = [
        pos[r["retest"]] - pos[r["break"]] for r in out.iter_rows(named=True)
    ]
    if not delays:
        return np.nan
    return float(np.percentile(delays, 90))


def run() -> None:
    folds = None
    rows: list[dict] = []
    for asset in ASSETS:
        df = pl.read_parquet(REPO / f"data/okx21/raw_{asset}_15m.parquet").rename(
            {"ts": "date"}
        )
        ts = df["date"].to_numpy().astype(np.int64)
        hp = df["high"].to_numpy().astype(np.float64)
        lp = df["low"].to_numpy().astype(np.float64)
        op = df["open"].to_numpy().astype(np.float64)
        cp = df["close"].to_numpy().astype(np.float64)
        vol = df["volume"].to_numpy().astype(np.float64)
        atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
        if folds is None:
            folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
        cutoff = folds[4][0] - EMBARGO_DAYS * DAY_MS
        ret = np.diff(np.log(cp))
        p50, p90 = _pivot_lags(
            hp, lp, effective_online_reversal(TIMEFRAME_CONFIGS["15m"], atr)
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            bpa = float(np.nanmedian(atr[1:] / np.abs(np.diff(cp))))
            spr = float(np.nanmedian((hp - lp)[1:] / cp[1:] / atr[1:]))
            rng = float(np.nanmedian((hp - lp)[1:] / atr[1:]))
        gaps = np.abs(op[1:] - cp[:-1])
        rows.append(
            {
                "asset": asset,
                "bars_per_ATR": bpa,
                "half_life_ar1": _half_life_ar1(np.abs(ret)),
                "half_life_acf": _half_life_acf(ret),
                "pivot_lag_p50": p50,
                "pivot_lag_p90": p90,
                "retest_p90": _retest_p90(df, ts, cutoff),
                "spread_ratio": spr,
                "range_atr": rng,
                "volume_irreg": float(
                    np.percentile(vol, 90) / np.percentile(vol, 10)
                ),
                "gap_freq": float(np.mean(gaps > 0.5 * atr[1:])),
                "EV4R": EV4[asset],
                "EV6R": EV6[asset],
            }
        )
    cols = [c for c in rows[0] if c != "asset"]
    print(f"{'asset':<10}" + "".join(f"{c[:9]:>10}" for c in cols), flush=True)
    for r in rows:
        print(f"{r['asset']:<10}" + "".join(f"{r[c]:>10.3g}" for c in cols), flush=True)
    print("\nSpearman vs EV4R / EV6R (n=10):", flush=True)

    def spearman(x: list[float], y: list[float]) -> float:
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        return float(np.corrcoef(rx, ry)[0, 1])

    for c in cols:
        if c in ("EV4R", "EV6R"):
            continue
        vals = [r[c] for r in rows]
        print(
            f"  {c:<16} {spearman(vals, [r['EV4R'] for r in rows]):+.2f}  "
            f"{spearman(vals, [r['EV6R'] for r in rows]):+.2f}",
            flush=True,
        )


if __name__ == "__main__":
    run()