# -*- coding: utf-8 -*-
"""P-S1.1: promoted module + bear-gated shorts (prereg
STATUS 2026-09-25).  One pass."""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    WARMUP,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from engine.passed.avsl_trailing_s1 import (
    SPLIT_FRAC,
    build_env,
    trade_revcross,
)


def bear_arrays(env):
    day = env["b"] // 6
    bnd = np.nonzero(np.diff(day))[0] + 1
    dnum, dclose = day[bnd - 1], env["cp"][bnd - 1]
    csum = np.cumsum(np.insert(dclose, 0, 0.0))
    sma = np.full(len(dclose), np.nan)
    sma[199:] = (csum[200:] - csum[:-200]) / 200.0
    return dnum, dclose < sma


def main() -> None:
    repo = repo_root()
    ctxs, trades, shorts = {}, [], []
    for sym in ASSETS:
        env = build_env(sym, repo)
        dnum, bear = bear_arrays(env)
        ctxs[sym] = {"g0": env["g0"], "n_bars": env["n_bars"],
                     "sizes": __import__(
                         "engine.passed.avsl_cross_s1",
                         fromlist=["s1_sizes"]).s1_sizes(env["cp"])}
        for t, up in zip(env["cross_idx"], env["up"][env["cross_idx"] - 1]):
            t = int(t)
            if t < WARMUP:
                continue
            if not up:
                pos = int(np.searchsorted(dnum, env["b"][t] // 6)) - 1
                if pos < 199 or not bear[pos]:
                    continue
            tr = trade_revcross(env, t, bool(up))
            if tr is not None:
                tr["sym"] = sym
                trades.append(tr)
                if not up:
                    shorts.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        hold = max(e1 - e0, 1)
        s[e0:e1 + 1] += c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
    sh_ev = float(np.mean([t["net"] for t in shorts]))
    g1 = sh_ev >= 0.05
    print(f"trades {len(trades)} (shorts {len(shorts)}); G1 short-leg "
          f"EV {sh_ev:+.3f}R -> {'PASS' if g1 else 'FAIL'}")
    gates = g1
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        st = [t for t in trades
              if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in st])
        v = s[lo:hi]
        pos = sum(1 for sym in ASSETS
                  if [t["net"] for t in st if t["sym"] == sym]
                  and np.mean([t["net"] for t in st
                               if t["sym"] == sym]) > 0)
        sh, dd = nw_sharpe(v), portfolio_dd(v)
        lo_ci, hi_ci = block_bootstrap_ci(v)
        g = sh >= 1.2 and dd <= 0.20 and pos >= 7 and lo_ci > 0
        gates &= g
        print(f"{seg:>7}: Sharpe_NW={sh:+.2f} DD={dd:.0%} EV={r.mean():+.2f}R "
              f"pos={pos}/10 CI=[{lo_ci:+.5f},{hi_ci:+.5f}] n={len(r)} "
              f"-> {'PASS' if g else 'FAIL'}")
        rd = np.sort(r)[::-1]
        print(f"         ex-top20 EV {rd[20:].mean():+.3f}R (top20 share "
              f"{rd[:20].sum() / r.sum():.0%})")
    yr = {}
    for tr in shorts:
        y = dt.datetime.utcfromtimestamp(
            (ctxs[tr["sym"]]["g0"] + tr["e0"]) * 14_400_000 / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("short-leg per-year EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})
    e0s = np.array([t["e0"] + ctxs[t["sym"]]["g0"] - g0g for t in shorts])
    e1s = np.array([t["e1"] + ctxs[t["sym"]]["g0"] - g0g for t in shorts])
    conc = np.zeros(int(e1s.max()) + 1)
    for a, b in zip(e0s, e1s):
        conc[a:b + 1] += 1
    print(f"short concurrency: max {conc.max():.0f} "
          f"p95 {np.percentile(conc[conc > 0], 95):.1f}")
    print(f"P-S1.1 VERDICT: {'PASS' if gates else 'FAIL'}")


if __name__ == "__main__":
    main()
