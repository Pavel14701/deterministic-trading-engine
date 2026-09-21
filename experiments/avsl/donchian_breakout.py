# -*- coding: utf-8 -*-
"""Donchian(20) breakout + EMA(200) trend + 2xATR stop + Donchian(10) exit.

Pre-registered single-shot test (STATUS.md, DONCHIAN BREAKOUT --
PRE-REGISTRATION): no tuning, 4H, 6 majors, standard walk-forward
train 224d / test 224d, both sides primary, buy-and-hold benchmark.
"""
from __future__ import annotations

import numpy as np

from engine.backtest.protocol import wf_folds
from experiments.avsl.avsl_baseline import DAY
from experiments.avsl.avsl_trailing import REPO, TAKER_FEE, _read_okx
from ta.src.overlap.ema import ema_ind
from ta.src.volatility.atr import atr_ind


ASSETS = ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE")
RISK_K = 2.0
WARM = 700


def _roll(x: np.ndarray, w: int, fn):
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        sw = np.lib.stride_tricks.sliding_window_view(x, w)
        out[w - 1 :] = fn(sw, axis=1)
    return out


def _atr_gate(atr: np.ndarray, lookback: int = 500, q: float = 0.3):
    """ATR percentile rank within the prior `lookback` bars > q."""
    n = len(atr)
    ok = np.zeros(n, dtype=bool)
    for t in range(lookback, n):
        a, w = atr[t], atr[t - lookback : t]
        ok[t] = bool(np.isfinite(a) and (w < a).mean() > q)
    return ok


def _simulate(cp, op, hh20, ll20, hh10, ll10, ema, atrok, atr, lo, hi,
              long_only, ts):
    """One segment, starts flat.  Close-based exits, no same-bar re-entry."""
    n = len(cp)
    seg_end = min(int(np.searchsorted(ts, hi, side="left")) - 1, n - 1)
    t_start = max(int(np.searchsorted(ts, lo, side="left")), WARM)
    trades = []  # (gross_r, fee_r, hold)
    pos = 0
    entry = risk = 0.0
    t0 = 0
    for t in range(t_start, seg_end + 1):
        if pos == 1 and (cp[t] < ll10[t] or cp[t] < entry - risk):
            trades.append(
                ((cp[t] - entry) / risk, 2 * TAKER_FEE * entry / risk, t - t0)
            )
            pos = 0
        elif pos == -1 and (cp[t] > hh10[t] or cp[t] > entry + risk):
            trades.append(
                ((cp[t] - entry) / risk, 2 * TAKER_FEE * entry / risk, t - t0)
            )
            pos = 0
        if pos == 0 and np.isfinite(hh20[t]) and np.isfinite(ema[t]) \
                and np.isfinite(atr[t]) and atr[t] > 0 and atrok[t]:
            long_ok = cp[t] > hh20[t] and cp[t] > ema[t] and cp[t] > op[t]
            short_ok = cp[t] < ll20[t] and cp[t] < ema[t] and cp[t] < op[t]
            if long_ok or (short_ok and not long_only):
                pos = 1 if long_ok else -1
                entry = cp[t]
                risk = RISK_K * atr[t]
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
    if not trades:
        return "n=0", None
    pnl = np.array([p for p, _f, _h in trades])
    fee = np.array([f for _p, f, _h in trades])
    net = pnl - fee
    eq = np.cumsum(net)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    hold = np.mean([h for _p, _f, h in trades])
    s = (
        f"n={len(net):>3} evN={net.mean():+.3f} totR={net.sum():+.1f} "
        f"win={(pnl > 0).mean():.0%} hold={hold:.0f} maxDD={dd:.1f}R"
    )
    return s, float(net.sum())


def run() -> None:
    import sys

    args = sys.argv[1:]
    all34 = "all34" in args
    tfs = [a for a in args if a != "all34"] or ["4H"]
    universe = ASSETS
    if all34:
        from experiments.loaders.load_okx import ALL

        universe = tuple(ALL)
    print(
        "DONCHIAN(20)+EMA200+2xATR stop+Donchian(10) exit, 6 majors; "
        "walk-forward train 224d / test 224d; both sides primary "
        "(long-only secondary); bench=buy&hold; pre-registered, no "
        "tuning; kill per TF: <=2/6 positive net R on test.  Fixed "
        "WARM=700 bars: on 1D this exceeds the train span (declared "
        "consequence, not tuning).",
        flush=True,
    )
    for tf in tfs:
        print(f"=== TF {tf} ===", flush=True)
        pos_counts = {"TRAIN": 0, "TEST": 0}
        dd_test = []
        recov_ok = 0
        tot_ok = 0
        n_seen = 0
        for sym in universe:
            if not (REPO / f"data/okx21/raw_{sym}-USDT_{tf}.parquet").exists():
                print(f"{sym:>10} SKIP: no {tf} data", flush=True)
                continue
            n_seen += 1
            ts, op, lp, hp, cp, _vol = _read_okx(f"{sym}-USDT", tf)
            ema = ema_ind(cp, 200, use_talib=False, nan_policy="ffill")
            atr = atr_ind(hp, lp, cp, 14, use_talib=False)
            # rolling windows END at t-1 (no same-bar look-ahead)
            hh20 = np.concatenate(([np.nan], _roll(hp, 20, np.max)[:-1]))
            ll20 = np.concatenate(([np.nan], _roll(lp, 20, np.min)[:-1]))
            hh10 = np.concatenate(([np.nan], _roll(hp, 10, np.max)[:-1]))
            ll10 = np.concatenate(([np.nan], _roll(lp, 10, np.min)[:-1]))
            atrok = _atr_gate(atr)
            folds = wf_folds(int(ts[0]), int(ts[-1]), 8, 56)
            segs = (
                ("TRAIN", int(ts[0]), folds[4][0] - 7 * DAY),
                ("TEST", folds[4][0], int(ts[-1])),
            )
            for name, lo, hi in segs:
                s_full, tot_full = _agg(
                    _simulate(cp, op, hh20, ll20, hh10, ll10, ema, atrok,
                              atr, lo, hi, False, ts)
                )
                s_long, _tot_long = _agg(
                    _simulate(cp, op, hh20, ll20, hh10, ll10, ema, atrok,
                              atr, lo, hi, True, ts)
                )
                i0 = int(np.searchsorted(ts, lo, side="left"))
                i1 = min(
                    int(np.searchsorted(ts, hi, side="left")) - 1, len(cp) - 1
                )
                risk0 = RISK_K * atr[i0]
                bh = f"B&H={(cp[i1] / cp[i0] - 1):+.1%}"
                if np.isfinite(risk0) and risk0 > 0:
                    bh += f" ({(cp[i1] - cp[i0]) / risk0:+.1f}R)"
                print(
                    f"{sym:>10} {name}: full[{s_full}] long[{s_long}] {bh}",
                    flush=True,
                )
                if tot_full is not None and tot_full > 0:
                    pos_counts[name] += 1
            # pre-registered risk gate stats from the TEST segment
            tr = _simulate(cp, op, hh20, ll20, hh10, ll10, ema, atrok, atr,
                           segs[1][1], segs[1][2], False, ts)
            if tr:
                pnl = np.array([p for p, _f, _h in tr])
                fee = np.array([f for _p, f, _h in tr])
                net = pnl - fee
                eq = np.cumsum(net)
                dd = float(np.max(np.maximum.accumulate(eq) - eq))
                tot = float(net.sum())
                dd_test.append(dd)
                if tot > 0:
                    tot_ok += 1
                    if dd > 0 and tot / dd >= 1.0:
                        recov_ok += 1
        med_dd = float(np.median(dd_test)) if dd_test else float("nan")
        print(
            f"TF {tf}: POSITIVE net-R TRAIN {pos_counts['TRAIN']}/{n_seen}, "
            f"TEST {pos_counts['TEST']}/{n_seen} (kill <= 2/6 on test)",
            flush=True,
        )
        if all34:
            g1 = pos_counts["TEST"] >= 0.5 * n_seen
            g2 = med_dd <= 20.0
            g3 = recov_ok >= 0.5 * n_seen
            print(
                f"PREREG GATES (34): positive {tot_ok}/{n_seen} "
                f"(need >=17): {'PASS' if g1 else 'FAIL'}; "
                f"med test DD {med_dd:.1f}R (need <=20): "
                f"{'PASS' if g2 else 'FAIL'}; "
                f"recov>=1 {recov_ok}/{n_seen} (need >=17): "
                f"{'PASS' if g3 else 'FAIL'}; "
                f"OVERALL: {'PASS' if (g1 and g2 and g3) else 'FAIL'}",
                flush=True,
            )


if __name__ == "__main__":
    run()
