# -*- coding: utf-8 -*-
"""AVSL price-cross: entry on price crossing the AVSL line itself.

No SMA.  Line = avsl_ind(low, close, volume, 70, 345) (donor mult
2.0, NaN-safe path).  Entry: close crosses the line; stop = line at
entry; risk = |close - line| (skips non-finite / non-positive).
Two arms: normal (long on up-cross) and reverse (long on down-cross,
fade).  TP {3,5,8}R, horizon 192 bars, MTM exit, conservative
within-bar (stop wins).  Per-asset readout (BTC + 9 holdout, no
pooling): train = folds 0-3, test = folds 4-7 (protocol 8x56d).

Usage:  uv run python -m engine.experiments.avsl_price_cross
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent

from engine.backtest.protocol import FOLD_DAYS, N_FOLDS, wf_folds
from engine.experiments.avsl_baseline import DAY, TPS, WARMUP, _fast_line, _sim


ASSETS = (
    "BTC-USDT",
    "AVAX-USDT",
    "BNB-USDT",
    "DOGE-USDT",
    "ETH-USDT",
    "LINK-USDT",
    "LTC-USDT",
    "NEAR-USDT",
    "SOL-USDT",
    "XRP-USDT",
)
TAKER_FEE = 0.0005


def _read(sym: str):
    df = pl.read_parquet(REPO / f"data/okx21/raw_{sym}_15m.parquet").rename(
        {"ts": "date"}
    )
    return (
        df["date"].to_numpy().astype(np.int64),
        df["low"].to_numpy().astype(np.float64),
        df["high"].to_numpy().astype(np.float64),
        df["close"].to_numpy().astype(np.float64),
        df["volume"].to_numpy().astype(np.float64),
    )


def _arm_stats(hp, lp, cp, ts, line, up, dn, lo, hi, reverse: bool):
    stats = {tp: [] for tp in TPS}
    n_tot = n_skipped = 0
    for t in np.nonzero((up | dn))[0] + 1:
        if not (lo <= ts[t] < hi) or t < WARMUP:
            continue
        n_tot += 1
        is_long = bool(dn[t - 1]) if reverse else bool(up[t - 1])
        stop = line[t]
        risk = cp[t] - stop if is_long else stop - cp[t]
        if not np.isfinite(risk) or risk <= 0:
            n_skipped += 1
            continue
        fee_r = 2 * TAKER_FEE * cp[t] / risk
        for tp_r in TPS:
            pnl = _sim(hp, lp, cp, t, is_long, stop, tp_r)
            if pnl is not None:
                stats[tp_r].append((pnl, fee_r))
    return stats, n_tot, n_skipped


def run() -> None:
    print(
        "AVSL price-cross (no SMA): entry=close crossing avsl(70,345), "
        f"stop=avsl@entry, TP {TPS}, horizon 192, taker 5bp x2",
        flush=True,
    )
    for sym in ASSETS:
        ts, lp, hp, cp, vol = _read(sym)
        line = _fast_line(lp, cp, vol, 2.0)
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
        segs = (
            ("TRAIN", 0, folds[4][0] - 7 * DAY),
            ("TEST", folds[4][0], folds[-1][1]),
        )
        for name, lo, hi in segs:
            for label, rev in (("normal", False), ("reverse", True)):
                stats, n_tot, n_skipped = _arm_stats(
                    hp, lp, cp, ts, line, up, dn, lo, hi, rev
                )
                parts = []
                for tp_r in TPS:
                    v = stats[tp_r]
                    if not v:
                        parts.append(f"TP={tp_r:.0f}R n=0")
                        continue
                    pnls = np.array([p for p, _ in v])
                    fees = np.array([f for _, f in v])
                    parts.append(
                        f"TP={tp_r:.0f}R n={len(pnls):>3} "
                        f"gross={pnls.mean():+.3f} "
                        f"net={(pnls - fees).mean():+.3f} "
                        f"win={np.mean(pnls > 0):.0%}"
                    )
                print(
                    f"{sym:>10} {name} {label:>7}: crosses={n_tot} "
                    f"skip={n_skipped} | {' | '.join(parts)}",
                    flush=True,
                )


if __name__ == "__main__":
    run()
