# -*- coding: utf-8 -*-
"""P-S1 forensic: leg decomposition (STATUS 2026-09-25).
Descriptive; no gates."""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    K_STOP,
    TAKER_FEE,
    WARMUP,
    nw_sharpe,
    portfolio_dd,
    repo_root,
    s1_sizes,
)
from engine.passed.avsl_trailing_s1 import SPLIT_FRAC, build_env

TP_R = 8.0


def short_tp_tagged(env, t):
    cp, hp, lp = env["cp"], env["hp"], env["lp"]
    risk = max(abs(cp[t] - env["line"][t]), K_STOP * env["atr"][t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop, tp = cp[t] + risk, cp[t] - TP_R * risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    n = len(cp)
    pnl, reason, k_exit = None, "mtm", min(t + 500, n - 1)
    for k in range(t + 1, min(t + 501, n)):
        if hp[k] >= stop:
            pnl, reason, k_exit = -1.0, "stop", k
            break
        if lp[k] <= tp:
            pnl, reason, k_exit = TP_R, "tp", k
            break
    if pnl is None:
        pnl = (cp[t] - cp[k_exit]) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": int(env["b"][k_exit]) - env["g0"], "long": False,
            "reason": reason}


def long_tagged(env, t):
    cp, hp, lp = env["cp"], env["hp"], env["lp"]
    risk = max(abs(cp[t] - env["line"][t]), K_STOP * env["atr"][t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    n = len(cp)
    dirs = env["up"][env["cross_idx"] - 1]
    bars = env["cross_idx"][~dirs]
    nxt = bars[bars > t]
    k_exit = int(min(nxt[0], t + 500)) if nxt.size else -1
    reason = "revcross"
    if k_exit < 0:
        k_exit, reason = n - 1, "mtm_final"
    pnl = 0.0
    for k in range(t + 1, min(k_exit + 1, n)):
        if lp[k] <= stop:
            pnl, reason, k_exit = -1.0, "stop", k
            break
    if reason != "stop":
        pnl = (cp[k_exit] - cp[t]) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": k_exit, "long": True, "reason": reason}


def short_revcross_tagged(env, t):
    cp, hp = env["cp"], env["hp"]
    risk = max(abs(cp[t] - env["line"][t]), K_STOP * env["atr"][t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    n = len(cp)
    dirs = env["up"][env["cross_idx"] - 1]
    bars = env["cross_idx"][dirs]
    nxt = bars[bars > t]
    k_exit = int(min(nxt[0], t + 500)) if nxt.size else -1
    reason = "revcross"
    if k_exit < 0:
        k_exit, reason = n - 1, "mtm_final"
    pnl = 0.0
    for k in range(t + 1, min(k_exit + 1, n)):
        if hp[k] >= stop:
            pnl, reason, k_exit = -1.0, "stop", k
            break
    if reason != "stop":
        pnl = (cp[t] - cp[k_exit]) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": k_exit, "long": False, "reason": reason}


def bear_day_array(env):
    day = env["b"] // 6
    bnd = np.nonzero(np.diff(day))[0] + 1
    dnum, dclose = day[bnd - 1], env["cp"][bnd - 1]
    csum = np.cumsum(np.insert(dclose, 0, 0.0))
    sma = np.full(len(dclose), np.nan)
    sma[199:] = (csum[200:] - csum[:-200]) / 200.0
    return dnum, dclose < sma


def stream(ctxs, trades, g0g, n_g):
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        hold = max(e1 - e0, 1)
        w = c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
        s[e0:e1 + 1] += w
    return s


def main() -> None:
    repo = repo_root()
    ctxs, ps1_l, ps1_s, prd_s = {}, [], [], []
    for sym in ASSETS:
        env = build_env(sym, repo)
        ctxs[sym] = {"g0": env["g0"], "n_bars": env["n_bars"],
                     "sizes": s1_sizes(env["cp"])}
        dnum, bear = bear_day_array(env)
        for t, up in zip(env["cross_idx"], env["up"][env["cross_idx"] - 1]):
            t = int(t)
            if t < WARMUP:
                continue
            tr = long_tagged(env, t) if up else None
            if tr is not None:
                tr["sym"] = sym
                ps1_l.append(tr)
            if not up:
                pos = int(np.searchsorted(dnum, env["b"][t] // 6)) - 1
                if pos < 199 or not bear[pos]:
                    continue
                tr = short_tp_tagged(env, t)
                if tr is not None:
                    tr["sym"] = sym
                    ps1_s.append(tr)
                tr2 = short_revcross_tagged(env, t)
                if tr2 is not None:
                    tr2["sym"] = sym
                    prd_s.append(tr2)
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    s_l = stream(ctxs, ps1_l, g0g, n_g)
    s_s = stream(ctxs, ps1_s, g0g, n_g)
    print("== (1) standalone leg streams (true grid) ==")
    for name, v, leg in (("long-only ", s_l, ps1_l),
                         ("short-only", s_s, ps1_s),
                         ("combined  ", s_l + s_s, ps1_l + ps1_s)):
        for seg, a, b in (("PRIMARY", 0, split), ("F3", split, n_g)):
            st = [t for t in leg
                  if a <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < b]
            ev = float(np.mean([t["net"] for t in st])) if st else float("nan")
            print(f"{name} {seg:>7}: Sharpe {nw_sharpe(v[a:b]):+.2f} "
                  f"DD {portfolio_dd(v[a:b]):.0%} EV {ev:+.2f}R n={len(st)}")
    print("\n== (2)+(3) P-S1 short leg by year ==")
    yr = {}
    for tr in ps1_s:
        y = dt.datetime.utcfromtimestamp(
            (ctxs[tr["sym"]]["g0"] + tr["e0"]) * 14_400_000 / 1000).year
        yr.setdefault(y, []).append(tr)
    print("year | n | EV | stop% tp% mtm% | maxConc p95Conc")
    for y, v in sorted(yr.items()):
        e0s = np.array([t["e0"] + ctxs[t["sym"]]["g0"] - g0g for t in v])
        e1s = np.array([t["e1"] + ctxs[t["sym"]]["g0"] - g0g for t in v])
        conc = np.zeros(int(e1s.max()) + 1)
        for a, b in zip(e0s, e1s):
            conc[a:b + 1] += 1
        r = np.array([t["net"] for t in v])
        mix = {x: np.mean([t["reason"] == x for t in v])
               for x in ("stop", "tp", "mtm")}
        print(f"{y} | {len(v):3d} | {r.mean():+.3f} | "
              f"{mix['stop']:.0%} {mix['tp']:.0%} {mix['mtm']:.0%} | "
              f"{conc.max():.0f} {np.percentile(conc[conc > 0], 95):.1f}")
    print("\n== (4) exit attribution ==")
    for name, leg in (("P-S1 shorts (TP=8R)", ps1_s),
                      ("promoted shorts (revcross)", prd_s)):
        r = np.array([t["net"] for t in leg])
        print(f"{name}: n={len(r)} EV {r.mean():+.3f}R sum {r.sum():+.1f}R")
        for reason in sorted(set(t["reason"] for t in leg)):
            v = np.array([t["net"] for t in leg if t["reason"] == reason])
            print(f"   {reason:>10}: n={len(v):4d} EV {v.mean():+.3f}R "
                  f"sum {v.sum():+.1f}R max {v.max():+.1f}R")


if __name__ == "__main__":
    main()
