# -*- coding: utf-8 -*-
"""AVSL cross baseline (pre-registered): BTC 15m, no filters.

fast line = avsl_ind(low, close, volume, 70, 345); slow line =
sma_ind(close, 345).  Long: close crosses above fast; short: below.
Stop = slow line at entry (skip signals where slow is on the wrong
side: risk undefined).  TP {3,5,8}R, horizon 192 bars, MTM exit,
conservative within-bar (stop wins).  Segments: train folds 0-3,
test folds 4-7 (protocol 8x56d on 916d history).

Usage:  uv run python -m engine.experiments.avsl_baseline
"""

from __future__ import annotations

import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import FOLD_DAYS, N_FOLDS, wf_folds
from ta.src.custom.avs_base import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)
from ta.src.overlap.sma import sma_ind


FILE = "data/okx21/raw_BTC-USDT_15m.parquet"
FAST, SLOW = 70, 345
TPS = (3.0, 5.0, 8.0)
HORIZON = 192
TAKER_FEE = 0.0005
WARMUP = 400
DAY = 86_400_000


def _sim(hp, lp, cp, t, is_long, stop, tp_r):
    risk = cp[t] - stop if is_long else stop - cp[t]
    if risk <= 0:
        return None
    entry = cp[t]
    tp = entry + tp_r * risk if is_long else entry - tp_r * risk
    sign = 1.0 if is_long else -1.0
    n = len(cp)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                return -1.0
            if hp[k] >= tp:
                return tp_r
        else:
            if hp[k] >= stop:
                return -1.0
            if lp[k] <= tp:
                return tp_r
    return sign * (cp[min(t + HORIZON, n - 1)] - entry) / risk


def _fast_line(lp, cp, vol):
    """NaN-safe AVSL(70, 345), mirroring mtf._anchors_nan_safe.

    The talib SMA path poisons the whole series with warm-up NaNs.
    """
    vpc, vpr, _vm, vpci, dev = _avs_base(cp, vol, FAST, SLOW, 1.0, False)
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(lp, vpr, len_v, vpcc)
    adjusted = lp - price_v + dev
    return np.asarray(
        sma_ind(adjusted, SLOW, use_talib=False, nan_policy="ffill"),
        dtype=np.float64,
    )


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    lp = df["low"].to_numpy().astype(np.float64)
    hp = df["high"].to_numpy().astype(np.float64)
    cp = df["close"].to_numpy().astype(np.float64)
    vol = df["volume"].to_numpy().astype(np.float64)
    fast = _fast_line(lp, cp, vol)
    slow = sma_ind(cp, SLOW, use_talib=False, nan_policy="ffill")
    up = (cp[1:] > fast[1:]) & (cp[:-1] < fast[:-1])
    dn = (cp[1:] < fast[1:]) & (cp[:-1] > fast[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    segs = (
        ("TRAIN", 0, folds[4][0] - 7 * DAY),
        ("TEST", folds[4][0], folds[-1][1]),
    )
    print(
        f"AVSL cross baseline: fast=avsl(70,345), slow=sma(345), "
        f"TP {TPS}, horizon {HORIZON}, taker 5bp x2",
        flush=True,
    )
    for name, lo, hi in segs:
        stats = {tp: {"long": [], "short": []} for tp in TPS}
        n_tot = n_skipped = 0
        for t in cross_idx:
            if not (lo <= ts[t] < hi) or t < WARMUP:
                continue
            n_tot += 1
            is_long = bool(up[t - 1])
            stop = slow[t]
            risk = cp[t] - stop if is_long else stop - cp[t]
            if risk <= 0:
                n_skipped += 1
                continue
            side = "long" if is_long else "short"
            fee_r = 2 * TAKER_FEE * cp[t] / abs(risk)
            for tp_r in TPS:
                pnl = _sim(hp, lp, cp, t, is_long, stop, tp_r)
                if pnl is not None:
                    stats[tp_r][side].append((pnl, fee_r))
        print(
            f"-- {name} (raw crosses {n_tot}, skipped {n_skipped}) --",
            flush=True,
        )
        for tp_r in TPS:
            allv = stats[tp_r]["long"] + stats[tp_r]["short"]
            if not allv:
                print(f"  TP={tp_r:.0f}R n=0", flush=True)
                continue
            pnls = np.array([p for p, _ in allv])
            fees = np.array([f for _, f in allv])
            parts = []
            for side in ("long", "short"):
                sv = stats[tp_r][side]
                if sv:
                    sp = np.array([p for p, _ in sv])
                    parts.append(
                        f"{side} n={len(sv)} "
                        f"{sp.mean():+.3f}/{np.mean(sp > 0):.0%}"
                    )
            print(
                f"  TP={tp_r:.0f}R ALL n={len(pnls):>3} "
                f"gross={pnls.mean():+.3f} net={(pnls - fees).mean():+.3f} "
                f"win={np.mean(pnls > 0):.0%}  [{'; '.join(parts)}]",
                flush=True,
            )


if __name__ == "__main__":
    run()