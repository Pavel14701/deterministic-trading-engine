# -*- coding: utf-8 -*-
"""P-S1 short revival -- prereg run (STATUS 2026-09-25).
Shorts: dn-cross AND 1D bear filter (last completed daily close
< its 1D SMA200), exit hard stop OR TP=8R, HORIZON 500,
stop-first.  Longs unchanged (F-TP1).  One pass."""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    K_STOP,
    TAKER_FEE,
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

TP_R = 8.0
MSEC_1D = 86_400_000


def bear_ok(env: dict, t: int) -> bool:
    """Causal 1D filter: last COMPLETED daily close < SMA200."""
    if not hasattr(env, "__bear__"):
        day = env["b"] // 6
        bnd = np.nonzero(np.diff(day))[0] + 1
        dnum = day[bnd - 1]
        dclose = env["cp"][bnd - 1]
        csum = np.cumsum(np.insert(dclose, 0, 0.0))
        sma = np.full(len(dclose), np.nan)
        sma[199:] = (csum[200:] - csum[:-200]) / 200.0
        env.__dict__ if False else None
        env["_bear_dnum"], env["_bear_ok"] = dnum, dclose < sma
    dnum, ok = env["_bear_dnum"], env["_bear_ok"]
    d = env["b"][t] // 6
    pos = int(np.searchsorted(dnum, d)) - 1
    return pos >= 199 and bool(ok[pos])


def trade_short_tp(env: dict, t: int) -> dict | None:
    """Short with hard stop OR TP=8R; HORIZON 500, stop-first."""
    cp, hp, lp = env["cp"], env["hp"], env["lp"]
    risk = max(abs(cp[t] - env["line"][t]), K_STOP * env["atr"][t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] + risk
    tp = cp[t] - TP_R * risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    n = len(cp)
    pnl, k_exit = None, min(t + 500, n - 1)
    for k in range(t + 1, min(t + 501, n)):
        if hp[k] >= stop:
            pnl, k_exit = -1.0, k
            break
        if lp[k] <= tp:
            pnl, k_exit = TP_R, k
            break
    if pnl is None:
        pnl = (cp[t] - cp[k_exit]) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": int(env["b"][k_exit]) - env["g0"], "long": False}


def main() -> None:
    repo = repo_root()
    ctxs, trades, n_short_total = {}, [], 0
    for sym in ASSETS:
        env = build_env(sym, repo)
        ctxs[sym] = {"g0": env["g0"], "n_bars": env["n_bars"],
                     "sizes": None}
        from engine.passed.avsl_cross_s1 import s1_sizes
        ctxs[sym]["sizes"] = s1_sizes(env["cp"])
        n_dn = 0
        for t, up in zip(env["cross_idx"], env["up"][env["cross_idx"] - 1]):
            t = int(t)
            if t < WARMUP:
                continue
            if bool(up):
                tr = trade_revcross(env, t, True)
                if tr is not None:
                    tr["sym"] = sym
                    trades.append(tr)
            else:
                n_dn += 1
                if not bear_ok(env, t):
                    continue
                tr = trade_short_tp(env, t)
                if tr is not None:
                    tr["sym"] = sym
                    trades.append(tr)
        n_short_total += sum(1 for tr in trades
                             if tr["sym"] == sym and not tr["long"])
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    shorts = [t for t in trades if not t["long"]]
    longs = [t for t in trades if t["long"]]
    print(f"P-S1: trades {len(trades)} = longs {len(longs)} + "
          f"gated shorts {len(shorts)}")

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
    print(f"G-S1 short-leg EV: {sh_ev:+.3f}R (gate >= +0.05R) -> "
          f"{'PASS' if sh_ev >= 0.05 else 'FAIL'}")
    gates = sh_ev >= 0.05
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in seg_tr])
        v = s[lo:hi]
        pos = sum(1 for sym in ASSETS
                  if [t["net"] for t in seg_tr if t["sym"] == sym]
                  and np.mean([t["net"] for t in seg_tr
                               if t["sym"] == sym]) > 0)
        sh, dd = nw_sharpe(v), portfolio_dd(v)
        lo_ci, hi_ci = block_bootstrap_ci(v)
        g = (sh >= 1.2 and dd <= 0.20 and pos >= 7 and lo_ci > 0)
        gates &= g
        sr = [t["net"] for t in seg_tr if not t["long"]]
        print(f"{seg:>7}: Sharpe_NW={sh:+.2f} DD={dd:.0%} EV={r.mean():+.2f}R "
              f"pos={pos}/10 CI=[{lo_ci:+.5f},{hi_ci:+.5f}] n={len(r)} "
              f"(shorts n={len(sr)} EV {np.mean(sr) if sr else float('nan'):+.2f}R) "
              f"| gates {'PASS' if g else 'FAIL'}")
    yr: dict[int, list] = {}
    for tr in shorts:
        y = dt.datetime.utcfromtimestamp(
            (ctxs[tr["sym"]]["g0"] + tr["e0"]) * 14_400_000 / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("short-leg per-year EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})
    print(f"P-S1 VERDICT: {'PASS' if gates else 'FAIL'}")


if __name__ == "__main__":
    main()
