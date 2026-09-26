# -*- coding: utf-8 -*-
"""Shared wave-1 options runner infrastructure (frozen helpers).

Conventions follow strangle_carry v1.0.0: NOTIONAL 0.10 per wing,
HAIRCUT 0.25 maker proxy, daily MTM in % equity, hold to expiry,
raw Sharpe * sqrt(365).

Entry pricing (frozen per EXPERIMENT.md): real print-IV (median,
+/-1d of roll) when present, else proxy DVOL + frozen skew
(SKEW_PUT table / runtime call buckets).  MTM always proxy:
sig(t) = DVOL(t) + skew(K / spot(t)).
"""

from __future__ import annotations


__version__ = "1.0.0"

import datetime as dt
import json
import math

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import repo_root
from experiments.options._pricing import bs


MSEC_DAY = 86_400_000
HAIRCUT = 0.25
NOTIONAL = 0.10
SKEW_PUT_M = np.array([0.60, 0.675, 0.725, 0.775,
                       0.825, 0.875, 0.925, 0.975])
SKEW_PUT_V = np.array([12.74, 19.38, 20.64, 18.86,
                       14.09, 13.23, 13.75, 7.00])


def skew_put(m: float) -> float:
    return float(np.interp(min(max(m, SKEW_PUT_M[0]), 1.0),
                           SKEW_PUT_M, SKEW_PUT_V))


def skew_call(m: float, buckets: dict) -> float:
    b = sorted(buckets)
    if not b:
        return 0.0
    meds = [float(np.median(buckets[k])) for k in b]
    return float(np.interp(min(max(m, b[0] / 100.0), (b[-1] + 5) / 100.0),
                           [k / 100.0 for k in b], meds))


def exp_tag(ms: float) -> str:
    d = dt.datetime.utcfromtimestamp(ms / 1000)
    return f"{d.day:02d}{d.strftime('%b').upper()}{d:%y}"


def instrument_name(nxt: float, k: int, is_call: bool) -> str:
    return f"BTC-{exp_tag(nxt)}-{k}-{'C' if is_call else 'P'}"


def load_ctx() -> dict:
    out = repo_root() / "data/deribit"
    df = pl.read_parquet(repo_root()
                         / "data/binance/kl_BTCUSDT_1h.parquet")
    ts1 = df["ts"].to_numpy().astype(np.int64)
    cp1 = df["close"].to_numpy().astype(np.float64)

    dvol = json.loads((out / "dvol_BTC_1D.json").read_text())
    dv_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dv_v = np.array([d[4] for d in dvol], dtype=np.float64)
    order = np.argsort(dv_v)
    ranks = np.empty(len(dv_v))
    ranks[order] = np.arange(len(dv_v)) / len(dv_v)

    # daily closes + RV30 (% ann, sqrt365), как vol_readout
    b = ts1 // MSEC_DAY
    g = pl.DataFrame({"b": b, "cp": cp1}).group_by(
        "b", maintain_order=True).agg(pl.last("cp"))
    day_b = g["b"].to_numpy().astype(np.int64)
    day_cp = g["cp"].to_numpy().astype(np.float64)
    rv = np.full(len(day_cp), np.nan)
    for i in range(30, len(day_cp)):
        rv[i] = float(np.std(np.diff(np.log(day_cp[i - 30:i + 1])))
                      * math.sqrt(365) * 100)

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    def dvol(ts: float) -> float:
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(dv_v[max(j, 0)])

    def rv30(ts: float) -> float:
        j = int(np.searchsorted(day_b, ts // MSEC_DAY, side="right")) - 1
        return float(rv[j]) if j >= 0 else float("nan")

    def pct_at(ts: float) -> float:
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(ranks[max(j, 0)])

    rolls = json.loads((out / "strangle_rolls.json").read_text())
    subset = json.loads((out / "strangle_subset.json").read_text())
    return dict(out=out, ts1=ts1, cp1=cp1, spot=spot, dvol=dvol,
                rv30=rv30, pct_at=pct_at, rolls=rolls, subset=subset)


def calibrate_call_skew(ctx: dict) -> dict:
    """Print-iv minus DVOL by moneyness bucket, call side (frozen
    rule of strangle_carry)."""
    buckets: dict[int, list] = {}
    for name, meta in ctx["subset"].items():
        if meta["option_type"] != "call":
            continue
        p = ctx["out"] / "strangle_trades" / f"{name}.json"
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
            m = meta["strike"] / ctx["spot"](x["timestamp"])
            if m < 0.95 or m > 1.45:
                continue
            buckets.setdefault(int(m / 0.05) * 5,
                               []).append(iv - ctx["dvol"](x["timestamp"]))
    return buckets


def leg_specs(ctx: dict, put_tgt: float = 0.90,
              call_tgt: float = 1.10) -> list[tuple]:
    """Frozen wing selection of strangle_carry:
    (roll_ts, next_exp, otype, K)."""
    specs = []
    for roll in ctx["rolls"]:
        t_r, nxt, s0 = roll["roll_ts"], roll["next_exp"], roll["spot"]
        for otype, tgt in (("put", put_tgt), ("call", call_tgt)):
            ks = sorted({int(m["strike"]) for m in ctx["subset"].values()
                         if m["option_type"] == otype
                         and m["expiration_timestamp"] == nxt})
            if not ks:
                continue
            specs.append((t_r, nxt, otype,
                          min(ks, key=lambda x: abs(x - tgt * s0))))
    return specs


def entry_iv(ctx: dict, name: str, t_r: float) -> float | None:
    """Median real print-IV within +/-1d of t_r, else None."""
    p = ctx["out"] / "strangle_trades" / f"{name}.json"
    try:
        tr = json.loads(p.read_text())["result"]["trades"]
    except Exception:
        return None
    ivs = [float(x["iv"]) for x in tr
           if x.get("iv") and abs(x["timestamp"] - t_r) <= MSEC_DAY]
    return float(np.median(ivs)) if ivs else None


def simulate(ctx: dict, specs: list, sides: dict,
             min_dvol_pct: float | None = None,
             cbuckets: dict | None = None) -> dict:
    """Daily-MTM leg engine.  sides: otype -> +1 long / -1 short.

    Entry: real print-IV when available, else proxy.  Short legs
    transact at (1-hc) and carry MTM liability at (1+hc); long legs
    mirrored.  Returns dict(daily={day_id: pct}, legs=[leg dicts]).
    """
    if cbuckets is None:
        cbuckets = {}
    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    daily: dict[int, float] = {}
    legs = []
    for (t_r, nxt, otype, k) in specs:
        if min_dvol_pct is not None and ctx["pct_at"](t_r) < min_dvol_pct:
            continue
        side = sides[otype]
        is_call = otype == "call"
        s0 = ctx["spot"](t_r)
        ttm0 = max((nxt - t_r) / (365 * MSEC_DAY), 1e-9)
        iv = entry_iv(ctx, instrument_name(nxt, k, is_call), t_r)
        if iv is not None:
            mode, sig0 = "real", iv
        else:
            mode = "proxy"
            sk = skew_call(k / s0, cbuckets) if is_call else skew_put(k / s0)
            sig0 = ctx["dvol"](t_r) + sk
        p0 = bs(s0, k, ttm0, sig0, is_call)
        cash0 = (-side * p0 * (1 + side * HAIRCUT) / s0
                 * NOTIONAL * 100.0)

        d0, d1 = int(t_r // MSEC_DAY), int(nxt // MSEC_DAY)
        day_bars: dict[int, int] = {}
        lo = int(np.searchsorted(ts1, d0 * MSEC_DAY))
        hi = int(np.searchsorted(ts1, d1 * MSEC_DAY))
        for i in range(lo, hi):
            day_bars.setdefault(int(ts1[i] // MSEC_DAY), i)

        def val(t: float, s: float, nxt: float = nxt, k: int = k,
                is_call: bool = is_call, side: float = side,
                cash0: float = cash0) -> float:
            ttm = max((nxt - t) / (365 * MSEC_DAY), 0.0)
            sk = skew_call(k / s, cbuckets) if is_call else skew_put(k / s)
            p = bs(s, k, ttm, ctx["dvol"](t) + sk, is_call)
            return cash0 + side * p * (1 - side * HAIRCUT) \
                / s * NOTIONAL * 100.0

        prev = cash0
        leg_daily: dict[int, float] = {}
        for d in sorted(day_bars):
            i = day_bars[d]
            if ts1[i] >= nxt:
                break
            v = val(ts1[i], cp1[i])
            leg_daily[d] = leg_daily.get(d, 0.0) + v - prev
            prev = v
        s_t = ctx["spot"](nxt)
        p_in = max(s_t - k, 0.0) if is_call else max(k - s_t, 0.0)
        v_fin = cash0 + side * p_in * (1 - side * HAIRCUT) \
            / s_t * NOTIONAL * 100.0
        leg_daily[d1] = leg_daily.get(d1, 0.0) + v_fin - prev
        for d, v in leg_daily.items():
            daily[d] = daily.get(d, 0.0) + v
        legs.append(dict(t_r=t_r, nxt=nxt, otype=otype, k=k, pnl=v_fin,
                         mode=mode, side=side, cash0=cash0,
                         ivrv=ctx["dvol"](t_r) - ctx["rv30"](t_r)))
    return dict(daily=daily, legs=legs)


def perf(daily: dict) -> dict:
    days = sorted(daily)
    v = np.array([daily[d] for d in days])
    if len(v) == 0:
        return dict(n=0)
    eq = np.cumprod(1.0 + v / 100.0)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    mu, sd = float(v.mean()), float(v.std())
    sharpe = mu / sd * math.sqrt(365) if sd > 0 else 0.0
    yr: dict[int, float] = {}
    for d, x in zip(days, v):
        y = dt.datetime.utcfromtimestamp(d * MSEC_DAY / 1000).year
        yr[y] = yr.get(y, 0.0) + float(x)
    return dict(n=len(v), sharpe=float(sharpe), dd=dd,
                total=float(eq[-1] - 1), by_year=yr)

