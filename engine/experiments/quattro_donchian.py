# -*- coding: utf-8 -*-
"""Quattro Donchian: DC(20) + SMA(200) + 1.2*ATR break margin + 2.75*ATR trail.

PRE-REGISTERED single-shot test (STATUS.md, QUATTRO DONCHIAN 4H --
PRE-REGISTRATION): 4H, 6 majors, same split as the killed Donchian 4H
run (wf 8x56d, TEST = fold-4 start .. end, WARM=700).  Post-hoc
variant of a killed strategy -- declared, one shot, no tuning.
Params (20 / 200 / 1.2 / 2.75 / 14) come from the external spec as-is.
"""
from __future__ import annotations

import numpy as np

from engine.backtest.protocol import wf_folds
from engine.experiments.avsl_baseline import DAY
from engine.experiments.avsl_trailing import REPO, TAKER_FEE, _read_okx
from engine.experiments.donchian_breakout import ASSETS, _roll
from ta.src.volatility.atr import atr_ind


TRAIL_K = 2.75     # initial + trailing stop distance, x ATR(14), frozen at entry
BREAK_K = 1.2      # decisive-break margin beyond SMA(200), x ATR(14)
SMA_N = 200
DC_N = 20
WARM = 700


def _simulate(cp, op, hp, lp, hh20, ll20, sma, atr, lo, hi, long_only, ts):
    """One segment, starts flat.

    Exits on CLOSE crossing the trailing stop (stop as of the previous
    bar's running extreme -- no intrabar look-ahead).  Entry fill at
    the signal close (comparability with the killed 4H Donchian run).
    Trades: (gross_r, fee_r, hold); R = move / (TRAIL_K * ATR_entry).
    """
    n = len(cp)
    seg_end = min(int(np.searchsorted(ts, hi, side="left")) - 1, n - 1)
    t_start = max(int(np.searchsorted(ts, lo, side="left")), WARM)
    trades = []
    pos = 0
    entry = risk = stop = 0.0
    run_ext = 0.0
    t0 = 0
    for t in range(t_start, seg_end + 1):
        if pos == 1 and cp[t] <= stop:
            trades.append(
                ((cp[t] - entry) / risk, 2 * TAKER_FEE * entry / risk, t - t0)
            )
            pos = 0
        elif pos == -1 and cp[t] >= stop:
            trades.append(
                ((cp[t] - entry) / risk, 2 * TAKER_FEE * entry / risk, t - t0)
            )
            pos = 0
        if pos != 0:
            # trailing update AFTER the exit check (stop lags one bar)
            if pos == 1:
                run_ext = max(run_ext, hp[t])
                stop = max(stop, run_ext - risk)
            else:
                run_ext = min(run_ext, lp[t])
                stop = min(stop, run_ext + risk)
        if pos == 0 and np.isfinite(hh20[t]) and np.isfinite(sma[t]) \
                and np.isfinite(atr[t]) and atr[t] > 0:
            long_ok = (cp[t] > hh20[t]
                       and cp[t] > sma[t] + BREAK_K * atr[t])
            short_ok = (cp[t] < ll20[t]
                        and cp[t] < sma[t] - BREAK_K * atr[t])
            if long_ok or (short_ok and not long_only):
                pos = 1 if long_ok else -1
                entry = cp[t]
                risk = TRAIL_K * atr[t]
                stop = entry - pos * risk
                run_ext = entry
                t0 = t
    if pos != 0:
        trades.append(
            (
                pos * (cp[seg_end] - entry) / risk,
                2 * TAKER_FEE * entry / risk,
                seg_end - t0,
            )
        )
    return trades


def _agg(trades):
    """Summary line + (totR, win, pf, dd) or None."""
    if not trades:
        return "n=0", None
    pnl = np.array([p for p, _f, _h in trades])
    fee = np.array([f for _p, f, _h in trades])
    net = pnl - fee
    eq = np.cumsum(net)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    wins = float(net[net > 0].sum())
    losses = float(-net[net < 0].sum())
    pf = wins / losses if losses > 0 else float("inf")
    hold = np.mean([h for _p, _f, h in trades])
    s = (
        f"n={len(net):>3} evN={net.mean():+.3f} totR={net.sum():+.1f} "
        f"win={(pnl > 0).mean():.0%} pf={pf:.2f} hold={hold:.0f} "
        f"maxDD={dd:.1f}R"
    )
    return s, (float(net.sum()), float((pnl > 0).mean()), pf, dd,
               wins, losses)


def run() -> None:
    """Quattro Donchian pre-registered run (6 majors, 4H)."""
    import sys

    args = sys.argv[1:]
    long_only = "longonly" in args
    universe = tuple(a for a in args if a != "longonly") or ASSETS
    print(
        "QUATTRO DONCHIAN 4H: DC(20)+SMA200+1.2ATR break margin, "
        "2.75ATR frozen trail, no TP; 6 majors; split identical to the "
        "killed Donchian 4H run; pre-registered gates G1-G4 (STATUS.md); "
        "one shot, no tuning.  POST-HOC variant of a killed strategy -- "
        "declared.", flush=True,
    )
    pos_counts = {"TRAIN": 0, "TEST": 0}
    dd_test, recov_ok, n_seen = [], 0, 0
    pf_wins = pf_losses = 0.0
    for sym in universe:
        if not (REPO / f"data/okx21/raw_{sym}-USDT_4H.parquet").exists():
            print(f"{sym:>10} SKIP: no 4H data", flush=True)
            continue
        n_seen += 1
        ts, op, lp, hp, cp, _vol = _read_okx(f"{sym}-USDT", "4H")
        sma = _roll(cp, SMA_N, np.mean)
        atr = atr_ind(hp, lp, cp, 14, use_talib=False)
        hh20 = np.concatenate(([np.nan], _roll(hp, DC_N, np.max)[:-1]))
        ll20 = np.concatenate(([np.nan], _roll(lp, DC_N, np.min)[:-1]))
        folds = wf_folds(int(ts[0]), int(ts[-1]), 8, 56)
        segs = (
            ("TRAIN", int(ts[0]), folds[4][0] - 7 * DAY),
            ("TEST", folds[4][0], int(ts[-1])),
        )
        test_stats = None
        for name, lo, hi in segs:
            tr = _simulate(cp, op, hp, lp, hh20, ll20, sma, atr, lo, hi,
                           long_only, ts)
            s_full, stats_full = _agg(tr)
            i0 = int(np.searchsorted(ts, lo, side="left"))
            i1 = min(int(np.searchsorted(ts, hi, side="left")) - 1,
                     len(cp) - 1)
            risk0 = TRAIL_K * atr[i0]
            bh = f"B&H={(cp[i1] / cp[i0] - 1):+.1%}"
            if np.isfinite(risk0) and risk0 > 0:
                bh += f" ({(cp[i1] - cp[i0]) / risk0:+.1f}R)"
            print(f"{sym:>10} {name}: [{s_full}] {bh}", flush=True)
            if stats_full is not None and stats_full[0] > 0:
                pos_counts[name] += 1
            if name == "TEST" and stats_full is not None:
                tot, _win, _pf, dd, wins, losses = stats_full
                dd_test.append(dd)
                pf_wins += wins
                pf_losses += losses
                if tot > 0 and dd > 0 and tot / dd >= 1.0:
                    recov_ok += 1
    med_dd = float(np.median(dd_test)) if dd_test else float("nan")
    pooled_pf = (pf_wins / pf_losses) if pf_losses > 0 else float("inf")
    g1 = pos_counts["TEST"] >= 4
    g2 = med_dd <= 20.0
    g3 = recov_ok >= 4
    g4 = pooled_pf >= 1.3
    print(
        f"PREREG GATES (test): "
        f"G1 positive {pos_counts['TEST']}/{n_seen} (need >=4): "
        f"{'PASS' if g1 else 'FAIL'}; "
        f"G2 med DD {med_dd:.1f}R (need <=20): {'PASS' if g2 else 'FAIL'}; "
        f"G3 recov>=1 {recov_ok}/{n_seen} (need >=4): "
        f"{'PASS' if g3 else 'FAIL'}; "
        f"G4 pooled PF {pooled_pf:.2f} (need >=1.3): "
        f"{'PASS' if g4 else 'FAIL'}; "
        f"OVERALL: {'PASS' if (g1 and g2 and g3 and g4) else 'FAIL'}",
        flush=True,
    )


if __name__ == "__main__":
    run()

