# -*- coding: utf-8 -*-
"""AVSL stop-flip trailing exit (pre-registered: 3 variants + benchmark).

Entry: close crosses fast_AVSL(70,345,sigma=2) up=long / down=short.
Initial SL = entry -/+ 2*ATR(14); risk unit R = 2*ATR.  Trailing SL
= AVSL -/+ 0.3*ATR, monotonic, causal (set on bar t, active t+1),
activation: v1 = after 10 bars; v2 = close beyond entry by 1R;
v3 = AVSL beyond entry (parameter-free).  Exit: SL hit (intrabar,
stop wins, conservative vs same-bar reverse cross) OR reverse
cross (exit at that close, flip into new side).  Benchmark:
always-in, exit at next cross, same R unit.  Metrics: n, EV
gross/net (R), win%, avg hold bars, maxDD (R).  Train = folds 0-3,
test = folds 4-7.  Fixed constants per pre-registration: k=2.0,
buffer=0.3, N=10.  No tuning.

Usage:  uv run python -m engine.experiments.avsl_trailing
"""

from __future__ import annotations

import sys

from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parent.parent.parent

from engine.backtest.protocol import FOLD_DAYS, N_FOLDS, wf_folds
from engine.experiments.avsl_baseline import DAY, WARMUP, _fast_line
from engine.experiments.avsl_price_cross import ASSETS, _read
from ta.src.volatility.atr import atr_ind


TAKER_FEE = 0.0005
K_ATR = 2.0
BUFFER = 0.3
N_TIME = 10


def _active(variant, t, t0, cp, entry, line, sign, risk):
    if variant == 1:
        return t - t0 >= N_TIME
    if variant == 2:
        return sign * (cp[t] - entry) >= risk
    if variant == 3:
        return sign * (line[t] - entry) > 0
    if variant == 4:
        return True  # immediate trailing, initial SL is ATR-based
    return False


def _run_arm(cp, lp, hp, ts, atr, line, up, dn, lo, hi, variant, rev=False):
    n = len(cp)
    crosses = np.nonzero(up | dn)[0] + 1
    trades = []  # (pnl_gross_r, fee_r, hold_bars)
    i = 0
    while i < len(crosses) and (
        crosses[i] < WARMUP or ts[crosses[i]] < lo
    ):
        i += 1
    seg_end = int(np.searchsorted(ts, hi, side="left")) - 1
    seg_end = min(seg_end, n - 1)
    while i < len(crosses):
        t0 = int(crosses[i])
        if ts[t0] >= hi or t0 >= n - 2:
            break
        side = bool(up[t0 - 1]) != rev  # rev flips entry orientation
        sign = 1.0 if side else -1.0
        entry = cp[t0]
        risk = K_ATR * atr[t0]
        if not np.isfinite(risk) or risk <= 0:
            i += 1
            continue
        if variant == 0:  # benchmark: always-in, exit at next cross
            if i + 1 >= len(crosses):
                break
            t1 = int(crosses[i + 1])
            exit_bar = min(t1, seg_end)
            pnl = sign * (cp[exit_bar] - entry) / risk
            trades.append((pnl, 2 * TAKER_FEE * entry / risk, exit_bar - t0))
            i += 1
            continue
        # find reverse-cross bar (opposite direction, inside segment)
        rev_i = None
        j = i + 1
        while j < len(crosses):
            tj = int(crosses[j])
            if ts[tj] >= hi:
                break
            if bool(up[tj - 1]) != side:
                rev_i = j
                break
            j += 1
        rev_bar = int(crosses[rev_i]) if rev_i is not None else None
        stop_bar = seg_end if rev_bar is None else min(rev_bar, seg_end)
        # bar-by-bar: SL (causal) vs reverse cross; SL wins ties
        sl = entry - sign * risk
        t_sl = None
        t = t0 + 1
        while t <= stop_bar:
            if (side and lp[t] <= sl) or (not side and hp[t] >= sl):
                t_sl = t
                break
            if _active(variant, t, t0, cp, entry, line, sign, risk):
                buf = BUFFER * atr[t]
                if side and line[t] < cp[t] - buf:
                    sl = max(sl, line[t] - buf)
                elif not side and line[t] > cp[t] + buf:
                    sl = min(sl, line[t] + buf)
            t += 1
        if t_sl is not None and (rev_bar is None or t_sl <= rev_bar):
            exit_bar = t_sl
            pnl = sign * (sl - entry) / risk
            trades.append((pnl, 2 * TAKER_FEE * entry / risk, exit_bar - t0))
            # next entry: first cross strictly after exit
            i += 1
            while i < len(crosses) and int(crosses[i]) <= exit_bar:
                i += 1
            continue
        if rev_i is not None:
            exit_bar = rev_bar
            pnl = sign * (cp[exit_bar] - entry) / risk
            trades.append((pnl, 2 * TAKER_FEE * entry / risk, exit_bar - t0))
            i = rev_i  # flip: this cross is the next entry
            continue
        # no reverse cross in segment: MTM at segment end
        pnl = sign * (cp[seg_end] - entry) / risk
        trades.append((pnl, 2 * TAKER_FEE * entry / risk, seg_end - t0))
        break
    if not trades:
        return {"n": 0}
    pnl = np.array([p for p, _f, _h in trades])
    fee = np.array([f for _p, f, _h in trades])
    hold = np.array([h for _p, _f, h in trades])
    eq = np.cumsum(pnl - fee)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return {
        "n": len(pnl),
        "ev_g": float(pnl.mean()),
        "ev_n": float((pnl - fee).mean()),
        "win": float(np.mean(pnl > 0)),
        "hold": float(hold.mean()),
        "maxdd": dd,
    }


def _fmt(s: dict) -> str:
    if s.get("n", 0) == 0:
        return "n=0"
    return (
        f"n={s['n']:>4} evG={s['ev_g']:+.3f} evN={s['ev_n']:+.3f} "
        f"win={s['win']:.0%} hold={s['hold']:>4.0f} maxDD={s['maxdd']:.1f}R"
    )


def run() -> None:
    rev = False
    tf = "15m"
    for a in sys.argv[1:]:
        if a == "rev":
            rev = True
        elif a in ("15m", "1H", "4H"):
            tf = a
    tag = "REVERSED" if rev else "NORMAL"
    syms = [a for a in ASSETS if (REPO / f"data/okx21/raw_{a}_{tf}.parquet").exists()]
    print(
        f"AVSL cross-entry + immediate AVSL trailing (config 70/345, "
        f"{tag}, tf={tf}, assets={len(syms)}): entry=cross, "
        "initSL=2xATR14, trail=AVSL-0.3ATR monotonic causal from bar 1; "
        "bench=always-in same orientation; exit=SL|reverse-cross; R=2xATR",
        flush=True,
    )
    for sym in syms:
        ts, lp, hp, cp, vol = _read(sym, tf)
        line = _fast_line(lp, cp, vol, 2.0)
        atr = atr_ind(hp, lp, cp, 14, use_talib=False)
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
        segs = (
            ("TRAIN", 0, folds[4][0] - 7 * DAY),
            ("TEST", folds[4][0], folds[-1][1]),
        )
        for name, lo, hi in segs:
            for variant, label in ((4, "trail"), (0, "bench")):
                s = _run_arm(
                    cp, lp, hp, ts, atr, line, up, dn, lo, hi, variant, rev
                )
                print(f"{sym:>10} {name} {label:>8}: {_fmt(s)}", flush=True)


if __name__ == "__main__":
    run()
