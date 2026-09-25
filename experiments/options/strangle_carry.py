# -*- coding: utf-8 -*-
"""VOL-CARRY SHORT-STRANGLE RUNNER -- frozen prereg
(STATUS.md, "VOL-CARRY SHORT-STRANGLE PRE-REG", 2026-09-25).

One pass.  Gates G-V1..G-V4 (see prereg).  Read-outs: haircut
sensitivity 0/15%, notional scaling 0.05x/0.20x, call-skew
table, per-year PnL.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import repo_root

OUT = Path(repo_root() / "data/deribit")
MSEC_DAY = 86_400_000
HAIRCUT = 0.25          # frozen maker proxy
NOTIONAL = 0.10         # frozen fixed fraction per wing


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(S: float, K: float, T: float, vol_pct: float,
       is_call: bool) -> float:
    if T <= 0:
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    sig = max(vol_pct, 1.0) / 100.0
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / sq
    d2 = d1 - sq
    if is_call:
        return float(S * _cdf(d1) - K * _cdf(-d2))
    return float(K * _cdf(-d2) - S * _cdf(-d1))


SKEW_PUT_M = np.array([0.60, 0.675, 0.725, 0.775,
                       0.825, 0.875, 0.925, 0.975])
SKEW_PUT_V = np.array([12.74, 19.38, 20.64, 18.86,
                       14.09, 13.23, 13.75, 7.00])


def load_ctx():
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    exp_of = {i["instrument_name"]: i["expiration_timestamp"]
              for i in inst}
    _df = pl.read_parquet(repo_root()
                          / "data/binance/kl_BTCUSDT_1h.parquet")
    ts1 = _df["ts"].to_numpy().astype(np.int64)
    cp1 = _df["close"].to_numpy().astype(np.float64)
    dvol = json.loads((OUT / "dvol_BTC_1D.json").read_text())
    dvol_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dvol_v = np.array([d[4] for d in dvol], dtype=np.float64)
    rolls = json.loads((OUT / "strangle_rolls.json").read_text())
    subset = json.loads((OUT / "strangle_subset.json").read_text())

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    def dvol(ts: float) -> float:
        j = int(np.searchsorted(dvol_ts, ts, side="right")) - 1
        return float(dvol_v[max(j, 0)])

    # daily closes for RV30 and the daily equity stream
    b = ts1 // MSEC_DAY
    df = pl.DataFrame({"b": b, "cp": cp1})
    g = df.group_by("b", maintain_order=True).agg(pl.last("cp"))
    day_close = g["cp"].to_numpy().astype(np.float64)
    return (exp_of, ts1, cp1, spot, dvol, rolls, subset,
            day_close, dvol_ts)


def daily_logret(ts1, cp1, j, n=30):
    """Log returns of the last n+1 daily closes ending at bar j."""
    idx = []
    last = None
    for i in range(j, -1, -1):
        d = ts1[i] // MSEC_DAY
        if d != last:
            idx.append(i)
            last = d
            if len(idx) == n + 1:
                break
    idx = idx[::-1]
    closes = cp1[idx]
    return np.diff(np.log(closes)) if len(closes) > n else np.array([])


def calibrate_call_skew(subset, exp_of, spot, dvol) -> tuple:
    """Print-iv minus DVOL by moneyness bucket, call side only."""
    buckets: dict[int, list] = {}
    for name, meta in subset.items():
        if meta["option_type"] != "call":
            continue
        p = OUT / "strangle_trades" / f"{name}.json"
        if not p.exists():
            continue
        try:
            tr = json.loads(p.read_text())["result"]["trades"]
        except Exception:
            continue
        for x in tr:
            iv = x.get("iv")
            if not iv:
                continue
            s0 = spot(x["timestamp"])
            m = meta["strike"] / s0
            if m < 0.95 or m > 1.45:
                continue
            buckets.setdefault(int(m / 0.05) * 5,
                               []).append(iv - dvol(x["timestamp"]))
    print("CALL skew table (frozen): moneyness% -> median, n")
    for bkt in sorted(buckets):
        v = np.array(buckets[bkt])
        if len(v) < 5:
            continue
        print(f"  [{bkt},{bkt + 5}): med {np.median(v):+.2f} "
              f"n={len(v)}")
    return buckets


def skew_call(m: float, buckets: dict) -> float:
    """Frozen rule: per-bucket median, linear extrapolation from
    the two extreme buckets, flat outside [0.95, 1.45]."""
    b = sorted(buckets)
    if not b:
        return 0.0
    meds = [float(np.median(buckets[k])) for k in b]
    return float(np.interp(min(max(m, b[0] / 100.0),
                               (b[-1] + 5) / 100.0),
                           [k / 100.0 for k in b], meds))


def skew_put(m: float) -> float:
    return float(np.interp(min(max(m, SKEW_PUT_M[0]), 1.0),
                           SKEW_PUT_M, SKEW_PUT_V))


def main() -> None:
    exp_of, ts1, cp1, spot, dvol, rolls, subset, day_close, dvol_ts \
        = load_ctx()
    buckets = calibrate_call_skew(subset, exp_of, spot, dvol)

    # strike map per roll (frozen wing selection)
    leg_specs = []   # (roll_ts, nxt, otype, K)
    for roll in rolls:
        t_r, nxt, s0 = roll["roll_ts"], roll["next_exp"], roll["spot"]
        for otype, tgt in (("put", 0.90), ("call", 1.10)):
            ks = sorted({int(m["strike"]) for m in subset.values()
                         if m["option_type"] == otype
                         and m["expiration_timestamp"] == nxt})
            if not ks:
                continue
            leg_specs.append((t_r, nxt, otype,
                              min(ks, key=lambda x: abs(x - tgt * s0))))
    print(f"legs: {len(leg_specs)}")

    def leg_value(t: float, s: float, k: float, nxt: float,
                  otype: str, hc: float) -> float:
        """Short-leg MTM in % equity (negative = liability)."""
        ttm = max((nxt - t) / (365 * MSEC_DAY), 0.0)
        m_mid = k / s
        sig = (dvol(t) + skew_put(m_mid) if otype == "put"
               else dvol(t) + skew_call(m_mid, buckets))
        p = bs(s, k, ttm, sig, otype == "call")
        return -p * (1 + hc) / s * NOTIONAL * 100.0

    for scale_mult, hc in ((1.0, HAIRCUT), (1.0, 0.15), (1.0, 0.0),
                           (0.5, HAIRCUT), (2.0, HAIRCUT)):
        daily = {}
        leg_pnls = []
        iv_rv = []
        for (t_r, nxt, otype, k) in leg_specs:
            s0 = spot(t_r)
            iv30 = dvol(t_r)
            j = int(np.searchsorted(ts1, t_r, side="right")) - 1
            lr = daily_logret(ts1, cp1, j, 30)
            rv30 = (float(np.std(lr) * math.sqrt(365) * 100)
                    if len(lr) == 30 else float("nan"))
            iv_rv.append(iv30 - rv30)
            m_mid = k / s0
            sig0 = (dvol(t_r) + skew_put(m_mid) if otype == "put"
                    else dvol(t_r) + skew_call(m_mid, buckets))
            ttm = (nxt - t_r) / (365 * MSEC_DAY)
            credit = (bs(s0, k, ttm, sig0, otype == "call")
                      * (1 - hc) / s0 * NOTIONAL * 100.0 * scale_mult)
            # daily MTM walk: value(t) = credit - liability(t)
            d0 = int(t_r // MSEC_DAY)
            d1 = int(nxt // MSEC_DAY)
            day_bars = {}
            lo, hi = int(np.searchsorted(ts1, d0 * MSEC_DAY)), \
                int(np.searchsorted(ts1, d1 * MSEC_DAY))
            for i in range(lo, hi):
                day_bars.setdefault(int(ts1[i] // MSEC_DAY), i)
            prev_v = credit
            for d in sorted(day_bars):
                i = day_bars[d]
                if ts1[i] >= nxt:
                    break
                s_t = cp1[i]
                v = credit + leg_value(ts1[i], s_t, k, nxt, otype,
                                       hc) * scale_mult
                daily[d] = daily.get(d, 0.0) + v - prev_v
                prev_v = v
            s_t = spot(nxt)
            v_final = credit + leg_value(nxt, s_t, k, nxt, otype,
                                         hc) * scale_mult
            daily[d1] = daily.get(d1, 0.0) + v_final - prev_v
            leg_pnls.append(v_final)
        days = sorted(daily)
        v = np.array([daily[k] for k in days])
        eq = np.cumprod(1.0 + v / 100.0)
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
        mu, sd = v.mean(), v.std()
        sharpe = mu / sd * math.sqrt(365) if sd > 0 else 0.0
        iv_med = float(np.nanmedian(iv_rv))
        iv_share = float(np.mean([x > 0 for x in iv_rv]))
        yr_pnl = {}
        for k_i, d_i in enumerate(days):
            y = dt.datetime.utcfromtimestamp(
                d_i * MSEC_DAY / 1000).year
            yr_pnl[y] = yr_pnl.get(y, 0.0) + v[k_i]
        print(f"\nscale x{scale_mult} haircut={hc}: "
              f"Sharpe={sharpe:+.2f} DD={dd:.1%} "
              f"total={float(eq[-1] - 1):+.1%} "
              f"| worst leg {min(leg_pnls):+.1f}% "
              f"| IV-RV med {iv_med:+.1f} share {iv_share:.0%}")
        print(f"  by year: "
              f"{ {k: round(x, 1) for k, x in yr_pnl.items()} }")
        if scale_mult == 1.0 and hc == HAIRCUT:
            p1 = sharpe >= 1.0
            p2 = dd <= 0.20
            p3 = bool(iv_med > 2.0 and iv_share >= 0.60)
            p4 = min(leg_pnls) >= -15.0
            y2022 = yr_pnl.get(2022, 0.0)
            p5 = y2022 >= -20.0
            print(f"G-V1 Sharpe>=1: {'PASS' if p1 else 'FAIL'}")
            print(f"G-V2 DD<=20%: {'PASS' if p2 else 'FAIL'}")
            print(f"G-V3 IV>RV: {'PASS' if p3 else 'FAIL'}")
            print(f"G-V4 worst leg>=-15%: {'PASS' if p4 else 'FAIL'}"
                  f"; 2022 PnL>=-20%: {'PASS' if p5 else 'FAIL'} "
                  f"({y2022:+.1f}%)")
            verdict = "PASS" if all([p1, p2, p3, p4, p5]) else "FAIL"
            print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
