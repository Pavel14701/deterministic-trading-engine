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

Usage:  uv run python -m experiments.avsl_trailing
"""

from __future__ import annotations

import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent

from engine.backtest.protocol import FOLD_DAYS, N_FOLDS, wf_folds
from experiments.avsl_baseline import DAY, WARMUP
from experiments.load_yf import TICKERS
from ta.src.custom.avs_base import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import get_order_block_config
from ta.src.momentum.rsi import rsi_ind
from ta.src.momentum.stoch import stoch_ind
from ta.src.overlap.ema import ema_ind
from ta.src.overlap.sma import sma_ind
from ta.src.trend.adx import adx_ind
from ta.src.volatility.atr import atr_ind


def _fast_line_fs(lp, cp, vol, fast: int, slow: int, sd: float = 2.0):
    """NaN-safe AVSL(fast, slow) -- generalization of baseline's 70/345."""
    vpc, vpr, _vm, vpci, dev = _avs_base(cp, vol, fast, slow, sd, False)
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(lp, vpr, len_v, vpcc)
    adjusted = lp - price_v + dev
    return np.asarray(
        sma_ind(adjusted, slow, use_talib=False, nan_policy="ffill"),
        dtype=np.float64,
    )


def _read_okx(sym: str, tf: str = "15m"):
    df = pl.read_parquet(REPO / f"data/okx21/raw_{sym}_{tf}.parquet").rename(
        {"ts": "date"}
    )
    return (
        df["date"].to_numpy().astype(np.int64),
        df["open"].to_numpy().astype(np.float64),
        df["low"].to_numpy().astype(np.float64),
        df["high"].to_numpy().astype(np.float64),
        df["close"].to_numpy().astype(np.float64),
        df["volume"].to_numpy().astype(np.float64),
    )


def _read_yf(sym: str, tf: str):
    df = pl.read_parquet(REPO / f"data/yf/raw_{sym}_{tf}.parquet")
    # yfinance intraday volume is ~half zeros -> AVSL (VWMA/VM) breaks.
    # Documented fill: forward-fill zeros, leading NaNs -> median.
    vol = (
        df.select(
            pl.when(pl.col("volume") <= 0)
            .then(None)
            .otherwise(pl.col("volume"))
            .alias("v")
        )
        .select(pl.col("v").forward_fill().fill_null(pl.col("v").median()))
        .to_series()
        .to_numpy()
        .astype(np.float64)
    )
    cp = df["close"].to_numpy().astype(np.float64)
    # Yahoo bad-tick spikes: |1-bar logret| > 50%.  Replace the corrupt
    # bar's OHLC with the previous close; iterate while spikes remain
    # (handles multi-bar corrupt stretches by flatlining them).
    lp = df["low"].to_numpy().astype(np.float64)
    hp = df["high"].to_numpy().astype(np.float64)
    op = df["open"].to_numpy().astype(np.float64)
    for _ in range(64):
        lr = np.abs(np.diff(np.log(cp, where=cp > 0, out=np.full_like(cp, np.nan))))
        bad = np.where(lr > np.log(1.5))[0] + 1
        if not len(bad):
            break
        for i in bad:
            op[i] = lp[i] = hp[i] = cp[i] = cp[i - 1]
    return (
        df["ts"].to_numpy().astype(np.int64),
        op,
        lp,
        hp,
        cp,
        vol,
    )


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


def _agg(trades):
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


def _gate_long(op, lp, hp, cp, vol, ts, tf, filters):
    """Causal per-bar permission for LONG entries; AND of selected filters.

    adx: ADX(14)>25 and +DI>-DI (trend).  ob: price inside an
    unmitigated demand block (online-zigzag, no repaint) at bar t.
    stoch: %K(14,3,3) > %D.  rsi: RSI-clouds MACD hist > 0.
    """
    n = len(cp)
    gate = np.ones(n, dtype=bool)
    if "adx" in filters:
        adx, _dxr, dmp, dmn = adx_ind(
            hp, lp, cp, 14, use_talib=False, nan_policy="ffill"
        )
        gate &= (np.nan_to_num(adx, nan=0.0) > 25.0) & (dmp > dmn)
    if "stoch" in filters:
        k, d = stoch_ind(hp, lp, cp, 14, 3, use_talib=False)
        gate &= k > d  # NaN comparisons -> False (blocked during warm-up)
    if "rsi" in filters:
        # RSI Clouds (rsi_length=14, MACD 12/26/9 ema on RSI of ohlc4).
        # rsi_clouds_ind is unusable here: rsi_ind leaves 13 leading
        # NaNs and the ema path poisons the whole MACD with them
        # (all-NaN out).  Manual replicate: seed warm-up NaNs with the
        # first valid RSI (causal -- only past values used).
        avg = (op + hp + lp + cp) / 4.0
        rsi = rsi_ind(
            avg, length=14, use_talib=False, nan_policy="ffill"
        ).astype(np.float64)
        bad = ~np.isfinite(rsi)
        if bad.any():
            first = np.argmax(~bad)
            rsi[bad] = rsi[first]
        f = ema_ind(rsi, 12, use_talib=False, nan_policy="raise")
        s_ = ema_ind(rsi, 26, use_talib=False, nan_policy="raise")
        macd = f - s_
        badm = ~np.isfinite(macd)
        if badm.any():
            macd[badm] = macd[np.argmax(~badm)]
        sig = ema_ind(macd, 9, use_talib=False, nan_policy="raise")
        gate &= (macd - sig) > 0.0
    if "rsi50" in filters:  # control: plain momentum, RSI(close) > 50
        r = rsi_ind(cp, length=14, use_talib=False, nan_policy="ffill")
        gate &= np.nan_to_num(r, nan=0.0) > 50.0
    if "rand" in filters:  # control: random gate, same ~50% capacity
        rng = np.random.default_rng(42)
        gate &= rng.random(n) < 0.5
    if "ob" in filters:
        df = pl.DataFrame(
            {
                "date": pl.from_epoch(ts, time_unit="ms"),
                "low": lp,
                "high": hp,
                "close": cp,
                "volume": vol,
            }
        )
        blocks = identify_order_blocks(df, cfg=get_order_block_config(tf))
        ogate = np.zeros(n, dtype=bool)
        for row in blocks.iter_rows(named=True):
            if row["block_type"] != "demand":
                continue
            b_ms = np.datetime64(row["break"], "ms").astype(np.int64)
            t = int(np.searchsorted(ts, b_ms, side="left")) + 1
            zl, zh = row["zone_low"], row["zone_high"]
            while t < n:  # valid until a close through the zone floor
                if cp[t] < zl:
                    break
                if lp[t] <= zh and cp[t] >= zl:
                    ogate[t] = True
                t += 1
        gate &= ogate
    return gate


def _run_arm(
    cp, lp, hp, ts, atr, line, up, dn, lo, hi, variant, rev=False,
    long_only=False, warm=WARMUP, gate=None,
):
    n = len(cp)
    crosses = np.nonzero(up | dn)[0] + 1
    trades = []  # (pnl_gross_r, fee_r, hold_bars)
    seg_end = int(np.searchsorted(ts, hi, side="left")) - 1
    seg_end = min(seg_end, n - 1)
    if variant == 0 and gate is not None:
        # gated benchmark: always-in long while the gate is on
        t = int(np.searchsorted(ts, lo, side="left"))
        in_pos = False
        entry = risk = 0.0
        t0p = 0
        while t <= seg_end:
            on = gate[t] and t >= warm
            if not in_pos and on:
                risk = K_ATR * atr[t]
                if np.isfinite(risk) and risk > 0:
                    in_pos = True
                    entry = cp[t]
                    t0p = t
            elif in_pos and not on:
                pnl = (cp[t] - entry) / risk
                trades.append((pnl, 2 * TAKER_FEE * entry / risk, t - t0p))
                in_pos = False
            t += 1
        if in_pos:
            pnl = (cp[seg_end] - entry) / risk
            trades.append(
                (pnl, 2 * TAKER_FEE * entry / risk, seg_end - t0p)
            )
        return _agg(trades)
    i = 0
    while i < len(crosses) and (
        crosses[i] < warm or ts[crosses[i]] < lo
    ):
        i += 1
    while i < len(crosses):
        t0 = int(crosses[i])
        if ts[t0] >= hi or t0 >= n - 2:
            break
        side = bool(up[t0 - 1]) != rev  # rev flips entry orientation
        if long_only and not side:
            i += 1  # long-only: skip short entries (stay flat)
            continue
        if gate is not None and not gate[t0]:
            i += 1  # filter veto: stay flat, await next cross
            continue
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
    return _agg(trades)


def _fmt(s: dict) -> str:
    if s.get("n", 0) == 0:
        return "n=0"
    return (
        f"n={s['n']:>4} evG={s['ev_g']:+.3f} evN={s['ev_n']:+.3f} "
        f"win={s['win']:.0%} hold={s['hold']:>4.0f} maxDD={s['maxdd']:.1f}R"
    )


def run() -> None:
    rev = False
    long_only = False
    tf = "15m"
    fast, slow = 70, 345
    filters = set()
    for a in sys.argv[1:]:
        if a == "rev":
            rev = True
        elif a in ("long", "longonly"):
            long_only = True
        elif a in ("5m", "15m", "1H", "4H", "1D"):
            tf = a
        elif a.startswith("cfg="):
            fast, slow = (int(x) for x in a[4:].split("/"))
        elif a in ("adx", "ob", "stoch", "rsi", "rsi50", "rand"):
            filters.add(a)
    tag = "REVERSED" if rev else "NORMAL"
    if long_only:
        tag += " LONG-ONLY"
    if filters:
        tag += " FILTER[" + "+".join(sorted(filters)) + "]"
        if not long_only:
            print("filters are defined for the long side; add 'long'", flush=True)
            return
    warm = max(WARMUP, slow + 100)  # entry-skip horizon scales with line
    src = "yf" if "yf" in sys.argv[1:] else "okx21"
    read = _read_yf if src == "yf" else _read_okx
    if src == "yf":
        # TON excluded from yf stats: corrupt Yahoo series (636 bars
        # stuck at $0.017 after a fake -99.5% 1H print, Aug 2025).
        universe = [t for t in TICKERS if t != "TON"]
    else:
        from experiments.load_okx import ALL  # 34 okx spot assets

        universe = [f"{s}-USDT" for s in ALL]
    syms = [
        a
        for a in universe
        if (REPO / f"data/{src}/raw_{a}_{tf}.parquet").exists()
    ]
    print(
        f"AVSL cross-entry + immediate AVSL trailing (config {fast}/{slow}, "
        f"{tag}, tf={tf}, assets={len(syms)}): entry=cross, "
        "initSL=2xATR14, trail=AVSL-0.3ATR monotonic causal from bar 1; "
        "bench=always-in same orientation; exit=SL|reverse-cross; R=2xATR"
        + ("; LONG-ONLY: short entries skipped, long exits at SL|cross" if long_only else ""),
        flush=True,
    )
    for sym in syms:
        ts, op, lp, hp, cp, vol = read(sym, tf)
        if len(cp) < warm + 110:  # AVSL(slow) needs history; skip shorts
            print(f"{sym:>10} SKIP: {len(cp)} bars < warm-up", flush=True)
            continue
        line = _fast_line_fs(lp, cp, vol, fast, slow, 2.0)
        atr = atr_ind(hp, lp, cp, 14, use_talib=False)
        gate = (
            _gate_long(op, lp, hp, cp, vol, ts, tf, filters)
            if filters
            else None
        )
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
                    cp, lp, hp, ts, atr, line, up, dn, lo, hi, variant, rev,
                    long_only=long_only, warm=warm, gate=gate,
                )
                print(f"{sym:>10} {name} {label:>8}: {_fmt(s)}", flush=True)


if __name__ == "__main__":
    run()
