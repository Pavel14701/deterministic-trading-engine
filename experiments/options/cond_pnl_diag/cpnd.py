# -*- coding: utf-8 -*-
"""Conditional P&L diagnostic -- frozen one-shot run.

See experiments/options/cond_pnl_diag/EXPERIMENT.md (v1.0.0).
Terciles of entry variables vs realized leg P&L; verdicts
ALIVE / TRAP / NULL per frozen rules.  Output: runs/cond_pnl_diag.log
"""

from __future__ import annotations


__version__ = "1.0.0"

import datetime as dt
import math

import numpy as np

from experiments.options._hedge import delta_hedge
from experiments.options._runner import (
    entry_iv,
    instrument_name,
    leg_specs,
    load_ctx,
    simulate,
)


MSEC_DAY = 86_400_000


def pct_rank(vals: np.ndarray) -> np.ndarray:
    order = np.argsort(vals)
    r = np.empty(len(vals))
    r[order] = np.arange(len(vals)) / max(len(vals) - 1, 1)
    return r


def build_universe(ctx: dict, otype: str) -> list[dict]:
    """U1/U2: all legs of one wing, unhedged P&L + entry variables."""
    res = simulate(ctx, [s for s in leg_specs(ctx) if s[2] == otype],
                   {"put": -1.0, "call": +1.0})
    rows = []
    for leg in res["legs"]:
        t_r, nxt, k = leg["t_r"], leg["nxt"], leg["k"]
        iv = entry_iv(ctx, instrument_name(nxt, k, otype == "call"), t_r)
        dvol = ctx["dvol"](t_r)
        rows.append(dict(t_r=t_r, pnl=leg["pnl"], mode=leg["mode"],
                         vrp=dvol - ctx["rv30"](t_r), dvol_pct=None,
                         rv_pct=None, skew=(iv - dvol) if iv else None,
                         slope=None, dte=(nxt - t_r) / MSEC_DAY,
                         iv=iv if iv else dvol))
    return rows


def hedge_universe(ctx: dict) -> list[dict]:
    """U3: put legs with real prints, delta-hedged P&L (as 1.1)."""
    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    rows = []
    for (t_r, nxt, otype, k) in leg_specs(ctx):
        if otype != "put":
            continue
        iv = entry_iv(ctx, instrument_name(nxt, k, False), t_r)
        if iv is None:
            continue
        s0 = ctx["spot"](t_r)
        lo = int(np.searchsorted(ts1, t_r, side="left"))
        hi = int(np.searchsorted(ts1, nxt, side="left"))
        path = [(int(ts1[i]), float(cp1[i])) for i in range(lo, hi)
                if ts1[i] < nxt]
        res = delta_hedge(path, float(k), nxt, iv, -1.0, is_call=False,
                          band=0.10)
        dvol = ctx["dvol"](t_r)
        rows.append(dict(t_r=t_r, pnl=res["pnl"] / s0 * 10.0,
                         mode="real", vrp=dvol - ctx["rv30"](t_r),
                         dvol_pct=None, rv_pct=None, skew=iv - dvol,
                         slope=None, dte=(nxt - t_r) / MSEC_DAY,
                         iv=iv))
    return rows


def rv_window(ctx: dict, t0: float, t1: float) -> float:
    """Annualized realized vol (%) on daily closes over [t0, t1)."""
    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    days: dict[int, float] = {}
    lo = int(np.searchsorted(ts1, int(t0 // MSEC_DAY) * MSEC_DAY))
    hi = int(np.searchsorted(ts1, int(t1 // MSEC_DAY) * MSEC_DAY))
    for i in range(lo, hi):
        days[int(ts1[i] // MSEC_DAY)] = float(cp1[i])
    xs = np.array([days[d] for d in sorted(days)])
    if len(xs) < 10:
        return float("nan")
    return float(np.std(np.diff(np.log(xs))) * math.sqrt(365) * 100)


def meds_ok(pnl: np.ndarray, x: np.ndarray, qs: np.ndarray,
            mask: np.ndarray) -> float:
    lo, hi = (mask & (x < qs[0])), (mask & (x >= qs[1]))
    if lo.sum() < 3 or hi.sum() < 3:
        return float("nan")
    return float(np.median(pnl[hi]) - np.median(pnl[lo]))


def tercile_verdict(pnl: np.ndarray, x: np.ndarray,
                    years: np.ndarray, rv: np.ndarray) -> dict:
    """Frozen rules: ALIVE / TRAP / NULL (+ reasons)."""
    from scipy.stats import spearmanr
    out: dict = {}
    ok = np.isfinite(x) & np.isfinite(pnl)
    x, pnl, years, rv = x[ok], pnl[ok], years[ok], rv[ok]
    out["n"] = int(ok.sum())
    if out["n"] < 30:
        out["verdict"] = "INSUFFICIENT"
        return out
    rho_rv = float(spearmanr(x, rv).statistic)
    out["rho_rv"] = rho_rv
    qs = np.quantile(x, [1 / 3, 2 / 3])
    lo, mid, hi = ((x < qs[0]), (x >= qs[0]) & (x < qs[1]), (x >= qs[1]))
    meds = [float(np.median(pnl[m])) if m.sum() else float("nan")
            for m in (lo, mid, hi)]
    ns = [int(m.sum()) for m in (lo, mid, hi)]
    out["meds"], out["ns"] = meds, ns
    spread = meds[2] - meds[0]
    out["spread"] = spread
    half = years >= 2024
    sp0 = meds_ok(pnl, x, qs, ~half)
    sp1 = meds_ok(pnl, x, qs, half)
    out["spread_halves"] = [sp0, sp1]
    mono = (meds[0] <= meds[1] <= meds[2]) or (meds[0] >= meds[1] >= meds[2])
    if min(ns) < 20:
        out["verdict"] = "INSUFFICIENT"
    elif mono and spread >= 0.50 and sp0 * sp1 > 0:
        out["verdict"] = "ALIVE"
    elif abs(rho_rv) >= 0.30 and spread < 0.50:
        out["verdict"] = "TRAP"
    else:
        out["verdict"] = "NULL"
    return out


def main() -> None:
    ctx = load_ctx()
    log = [f"cond_pnl_diag v{__version__} -- one-shot, frozen rules"]

    u1 = build_universe(ctx, "put")
    u2 = build_universe(ctx, "call")
    u3 = hedge_universe(ctx)
    log.append(f"universe sizes: U1 put {len(u1)}, U2 call {len(u2)}, "
               f"U3 hedged {len(u3)}")

    # global ranks for dvol / rv percentiles
    allrows = u1 + u2 + u3
    dv = np.array([ctx["dvol"](r["t_r"]) for r in allrows])
    rvv = np.array([ctx["rv30"](r["t_r"]) for r in allrows])
    pdv, prv = pct_rank(dv), pct_rank(rvv)
    for i, r in enumerate(allrows):
        r["dvol_pct"] = float(pdv[i])
        r["rv_pct"] = float(prv[i])

    # term slope per roll (same construction as ts_readout)
    puts = sorted((t_r, nxt, k) for (t_r, nxt, o, k) in leg_specs(ctx)
                  if o == "put")
    slopes: dict[float, float] = {}
    for i in range(len(puts) - 1):
        t_r, nxt, k = puts[i]
        _, nxt2, k2 = puts[i + 1]
        if nxt2 <= nxt:
            continue
        iv_f = entry_iv(ctx, instrument_name(nxt, k, False), t_r)
        iv_b = entry_iv(ctx, instrument_name(nxt2, k2, False), t_r)
        if iv_f is not None and iv_b is not None:
            slopes[t_r] = iv_b - iv_f
    for r in allrows:
        r["slope"] = slopes.get(r["t_r"])

    names = [("vrp", "VRP pt"), ("dvol_pct", "DVOL pct"),
             ("rv_pct", "RV30 pct"), ("skew", "print-skew pt"),
             ("slope", "term slope pt"), ("dte", "DTE days"),
             ("iv", "IV entry %")]

    for label, uni in (("U1 unhedged put", u1), ("U2 unhedged call", u2),
                       ("U3 hedged put", u3)):
        log.append("")
        log.append(f"[{label}] n={len(uni)}")
        pnl = np.array([r["pnl"] for r in uni])
        years = np.array([dt.datetime.utcfromtimestamp(
            r["t_r"] / 1000).year for r in uni])
        rvw = np.array([rv_window(ctx, r["t_r"],
                                  r["t_r"] + r["dte"] * MSEC_DAY)
                        for r in uni])
        for key, title in names:
            x = np.array([r[key] if r[key] is not None else np.nan
                          for r in uni], dtype=np.float64)
            v = tercile_verdict(pnl, x, years, rvw)
            if v["verdict"] == "INSUFFICIENT":
                log.append(f"  {title:16s} INSUFFICIENT (n={v['n']})")
                continue
            log.append(f"  {title:16s} {v['verdict']:12s} "
                       f"meds [{v['meds'][0]:+.2f}, {v['meds'][1]:+.2f}, "
                       f"{v['meds'][2]:+.2f}] spread {v['spread']:+.2f} "
                       f"halves [{v['spread_halves'][0]:+.2f}, "
                       f"{v['spread_halves'][1]:+.2f}] "
                       f"rho_RV {v['rho_rv']:+.2f} ns {v['ns']}")

    out = ctx["out"].parent.parent / "runs/cond_pnl_diag.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()

