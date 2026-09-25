# -*- coding: utf-8 -*-
"""PUTS-OVERLAY RUNNER -- implements the frozen prereg
(STATUS.md, "PUTS-OVERLAY PRE-REG", 2026-09-25) exactly.

One pass.  Gates: G-P1 DD<=20%, G-P2 EV>=0.8x baseline,
G-P3 Sharpe_NW >= baseline-0.10.  Read-outs as listed.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS, MSEC_4H, NW_LAGS, RISK_PCT, TAKER_FEE,
    collect_trades, read_1h, repo_root, resample_4h, s1_sizes,
)

OUT = Path(repo_root() / "data/deribit")
D0 = int(dt.datetime(2021, 4, 1).timestamp() * 1000)

SKEW_P75_M = np.array([0.60, 0.675, 0.725, 0.775,
                       0.825, 0.875, 0.925, 0.975])
SKEW_P75_V = np.array([12.74, 19.38, 20.64, 18.86,
                       14.09, 13.23, 13.75, 7.00])
SKEW_MED_M = np.array([0.625, 0.675, 0.725, 0.775,
                       0.825, 0.875, 0.925, 0.975])
SKEW_MED_V = np.array([10.585, 10.120, 9.800, 8.200,
                       5.550, 3.880, 2.070, -0.840])


def _np_cdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(
        np.asarray(x, dtype=np.float64) / math.sqrt(2.0)))


def bs_put(S: float, K: float, T: float, vol_pct: float) -> float:
    """Black-Scholes put USD price, r=0, vol in percent points."""
    if T <= 0:
        return max(K - S, 0.0)
    sig = max(vol_pct, 1.0) / 100.0
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / sq
    d2 = d1 - sq
    return float(K * _np_cdf(-d2) - S * _np_cdf(-d1))


def skew(m: float, table: str) -> float:
    if table == "p75":
        mm, vv = SKEW_P75_M, SKEW_P75_V
    elif table == "median":
        mm, vv = SKEW_MED_M, SKEW_MED_V
    else:
        return 0.0
    return float(np.interp(min(max(m, mm[0]), mm[-1]), mm, vv))


class Ctx:
    """Shared frozen data: BTC 4H grid, spot, DVOL, instruments."""

    def __init__(self) -> None:
        self.ts4, hp, lp, cp, vol = resample_4h(
            *read_1h(repo_root(), "BTC"))
        self.ts1, _, _, self.cp1, _ = read_1h(repo_root(), "BTC")
        self.cp4 = cp
        dvol = json.loads((OUT / "dvol_BTC_1D.json").read_text())
        self.dvol_ts = np.array([d[0] for d in dvol], dtype=np.int64)
        self.dvol_v = np.array([d[4] for d in dvol], dtype=np.float64)
        inst = json.loads((OUT / "instruments_BTC.json").read_text())
        puts = sorted((i for i in inst if i["option_type"] == "put"),
                      key=lambda i: (i["expiration_timestamp"],
                                     i["strike"]))
        self.expiries = sorted({p["expiration_timestamp"] for p in puts})
        self.strikes_by: dict[int, list] = {}
        for p in puts:
            self.strikes_by.setdefault(p["expiration_timestamp"],
                                       []).append(p["strike"])

    def spot(self, ts: float) -> float:
        j = int(np.searchsorted(self.ts1, ts, side="right")) - 1
        return float(self.cp1[max(j, 0)])

    def dvol(self, ts: float) -> float:
        j = int(np.searchsorted(self.dvol_ts, ts, side="right")) - 1
        return float(self.dvol_v[max(j, 0)])

    def pick(self, entry_ts: float):
        """(expiry, strike) per the frozen contract-selection rule."""
        want = entry_ts + 27 * 86400_000
        exp = next((e for e in self.expiries if e >= want), None)
        if exp is None:
            return None
        s0 = self.spot(entry_ts)
        k = min(self.strikes_by[exp],
                key=lambda x: abs(x - 0.90 * s0))
        return exp, float(k)


def run_overlay(ctx: Ctx, d: dict, sizes: np.ndarray,
                put_frac: float, table: str) -> dict:
    """Hedge accrual stream on the BTC grid + stats (frozen rules)."""
    g0 = d["g0"]
    hedge = np.zeros(d["n_bars"] + 2)
    prem_tot = 0.0
    n_hedged = 0
    m_list: list[float] = []
    by_year: dict[int, float] = {}
    for t in d["trades"]:
        if not t["long"]:
            continue
        t0 = (g0 + t["e0"]) * MSEC_4H
        if t0 < D0:
            continue
        pick = ctx.pick(t0)
        if pick is None:
            continue
        exp, k = pick
        s0 = ctx.spot(t0)
        risk_frac = 2 * TAKER_FEE / t["fee"]
        n_frac = put_frac * RISK_PCT * sizes[t["e0"]] / risk_frac
        t_x = min((g0 + t["e1"]) * MSEC_4H, exp)
        s_x = ctx.spot(t_x)
        te = (exp - t0) / (365 * 86400_000)
        tx = (t_x - t0) / (365 * 86400_000)
        p_in = bs_put(s0, k, te, ctx.dvol(t0) + skew(k / s0, table))
        if t_x >= exp:
            p_out = max(k - s_x, 0.0)
        else:
            p_out = bs_put(s_x, k, tx, ctx.dvol(t_x)
                           + skew(k / s_x, table))
        pnl_eq = (p_out - p_in) / s0 * n_frac * 100.0   # equity %
        n_hold = max(t["e1"] - t["e0"], 1)
        hedge[t["e0"]:t["e1"] + 1] += pnl_eq / (n_hold + 1) / 100.0
        prem_tot += p_in / s0 * n_frac * 100.0
        n_hedged += 1
        m_list.append(k / s0)
        yr = dt.datetime.utcfromtimestamp(t0 / 1000).year
        by_year[yr] = by_year.get(yr, 0.0) + pnl_eq
    return {"hedge": hedge, "prem": prem_tot, "n": n_hedged,
            "by_year": by_year,
            "m_mean": float(np.mean(m_list)) if m_list else 0.0}


def nw_sharpe(x: np.ndarray, lags: int = NW_LAGS) -> float:
    mu = float(x.mean())
    z = x - mu
    n = len(z)
    v0 = float(z @ z) / n
    s = v0
    for l in range(1, min(lags, n - 1)):
        cov = float(z[l:] @ z[:-l]) / n
        if abs(cov) / v0 < 0.01:
            break
        s += 2.0 * cov
    ann = 6 * 365
    return float((mu * ann) / math.sqrt(max(s, 1e-18) * ann))


def port_dd(stream: np.ndarray, r: float = 0.01) -> float:
    eq = np.cumprod(1.0 + r * stream)
    return float(np.max(1.0 - eq / np.maximum.accumulate(eq)))


def main() -> None:
    ctx = Ctx()
    d = collect_trades("BTC")
    sizes = s1_sizes(ctx.cp4)

    # frozen portfolio stream over the full common grid
    per = {s: collect_trades(s) for s in ASSETS}
    g0_all = min(dd["g0"] for dd in per.values())
    n_g = max(dd["n_bars"] + dd["g0"] for dd in per.values()) - g0_all
    trades = []
    sizes_by = {}
    for s, dd in per.items():
        for tr in dd["trades"]:
            trades.append({**tr, "sym": s})
        sizes_by[s] = s1_sizes(resample_4h(*read_1h(repo_root(), s))[3])
    trades.sort(key=lambda t: (t["e0"], t["sym"]))
    base = np.zeros(n_g + 1)
    for tr in trades:
        hold = max(tr["e1"] - tr["e0"], 1)
        w = sizes_by[tr["sym"]][tr["e0"]] * tr["net"] / (hold + 1)
        base[tr["e0"]:tr["e1"] + 1] += w
    stream = base[:n_g]

    # prereg window: 2021-04-01 .. end
    ts_g0 = g0_all * MSEC_4H
    i0 = max(int((D0 - ts_g0) // MSEC_4H), 0)
    stream = stream[i0:]
    n_w = len(stream)

    off = d["g0"] - g0_all          # BTC grid offset in global grid
    res = run_overlay(ctx, d, sizes, 1.0, "p75")

    def add(h: np.ndarray) -> np.ndarray:
        full = np.zeros(n_g + 1)
        if off >= 0:
            w = min(len(h), n_g + 1 - off)
            full[off:off + w] += h[:w]
        else:
            w = min(len(h) + off, n_g + 1)
            full[:w] += h[-off:-off + w]
        return full

    overlay = stream + add(res["hedge"])[i0:i0 + n_w]

    dd_b, dd_o = port_dd(stream), port_dd(overlay)
    ev_b, ev_o = float(stream.mean()), float(overlay.mean())
    sh_b, sh_o = nw_sharpe(stream), nw_sharpe(overlay)
    print(f"baseline : DD={dd_b:.1%} EV={ev_b:+.6f} Sharpe={sh_b:+.2f}")
    print(f"overlay  : DD={dd_o:.1%} EV={ev_o:+.6f} Sharpe={sh_o:+.2f}")
    print(f"hedge    : n={res['n']} premium={res['prem']:.2f}% equity "
          f"mean_m={res['m_mean']:.3f}")
    print("hedge PnL by year (% equity): "
          f"{ {k: round(v, 2) for k, v in sorted(res['by_year'].items())} }")
    g1 = dd_o <= 0.20
    g2 = ev_o >= 0.80 * ev_b
    g3 = sh_o >= sh_b - 0.10
    print(f"G-P1 DD<=20%: {'PASS' if g1 else 'FAIL'} ({dd_o:.1%})")
    print(f"G-P2 EV>=0.8x baseline: {'PASS' if g2 else 'FAIL'}")
    print(f"G-P3 Sharpe>=base-0.10: {'PASS' if g3 else 'FAIL'}")
    verdict = "PASS" if (g1 and g2 and g3) else "FAIL"
    print(f"VERDICT: {verdict}")

    for label, frac, tab in (("frac0.5/p75", 0.5, "p75"),
                             ("frac1/median", 1.0, "median"),
                             ("frac1/skew0", 1.0, "zero")):
        r2 = run_overlay(ctx, d, sizes, frac, tab)
        o2 = stream + add(r2["hedge"])[i0:i0 + n_w]
        print(f"read-out {label}: DD={port_dd(o2):.1%} "
              f"EV={o2.mean():+.6f} Sharpe={nw_sharpe(o2):+.2f} "
              f"prem={r2['prem']:.2f}% n={r2['n']}")

    ts_g0 = g0_all * MSEC_4H
    i22a = int((dt.datetime(2022, 1, 1).timestamp() * 1000
                - ts_g0) // MSEC_4H)
    i22b = int((dt.datetime(2023, 1, 1).timestamp() * 1000
                - ts_g0) // MSEC_4H)
    print(f"2022 DD: baseline {port_dd(stream[i22a:i22b]):.1%} "
          f"overlay {port_dd(overlay[i22a:i22b]):.1%}")


if __name__ == "__main__":
    main()
