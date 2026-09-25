# -*- coding: utf-8 -*-
"""F6 Supertrend filter -- frozen prereg (STATUS 2026-09-25,
AVSL TREND-FILTER PROGRAM, F6 SPEC).  One pass.

Supertrend(10, 3.0) on 4H H/L/C, ATR via the engine's atr_ind
(Wilder RMA default).  Keep long iff Supertrend direction up at
the entry bar, short iff down.  Seed: first bar with finite ATR
-> direction up, final bands = basic bands (frozen).
"""
from __future__ import annotations

import numpy as np

from ta.src.volatility.atr import atr_ind

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    collect_trades,
    evaluate,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.filter_f1_htf import neg_windows, stream_metrics

ST_LEN = 10
ST_MULT = 3.0


def supertrend_dir(hp: np.ndarray, lp: np.ndarray,
                   cp: np.ndarray) -> np.ndarray:
    atr = np.asarray(atr_ind(hp, lp, cp, ST_LEN, use_talib=False))
    hl2 = (hp + lp) / 2.0
    bub = hl2 + ST_MULT * atr
    blb = hl2 - ST_MULT * atr
    n = len(cp)
    fub = np.full(n, np.nan)
    flb = np.full(n, np.nan)
    dr = np.zeros(n, dtype=np.int64)
    started = False
    for i in range(n):
        if not np.isfinite(atr[i]):
            continue
        if not started:
            started = True
            fub[i], flb[i], dr[i] = bub[i], blb[i], 1
            continue
        fub[i] = bub[i] if (bub[i] < fub[i - 1]
                            or cp[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = blb[i] if (blb[i] > flb[i - 1]
                            or cp[i - 1] < flb[i - 1]) else flb[i - 1]
        if cp[i] > fub[i - 1]:
            dr[i] = 1
        elif cp[i] < flb[i - 1]:
            dr[i] = -1
        else:
            dr[i] = dr[i - 1]
    return dr


def main() -> None:
    repo = repo_root()
    base = evaluate()
    ok = (abs(base["PRIMARY"]["net_ev"] - 0.17) < 0.05
          and abs(base["F3"]["net_ev"] - 0.33) < 0.05)
    print(f"baseline sanity: {'OK' if ok else 'DEVIATION - ABORT'}")
    if not ok:
        return

    ctxs = {}
    data = {"base": [], "filt": []}
    for sym in ASSETS:
        ts1, hp1, lp1, cp1, vol1 = read_1h(repo, sym)
        ts4, hp4, lp4, cp4, _v = resample_4h(ts1, hp1, lp1, cp1, vol1)
        d = collect_trades(sym, repo)
        dr = supertrend_dir(hp4, lp4, cp4)
        ctxs[sym] = {"ts4": ts4, "sizes": s1_sizes(cp4),
                     "g0": d["g0"], "n_bars": d["n_bars"],
                     "trades": d["trades"]}
        for tr in d["trades"]:
            data["base"].append({**tr, "sym": sym})
            want = 1 if tr["long"] else -1
            if dr[tr["e0"]] == want:
                data["filt"].append({**tr, "sym": sym})

    nb, nf = len(data["base"]), len(data["filt"])
    print(f"== F6 ==\ntrades: base {nb} -> filtered {nf} "
          f"({nf / nb:.0%} kept)")
    mb = stream_metrics(ctxs, data["base"])
    mf = stream_metrics(ctxs, data["filt"])
    gates = []
    for seg in ("PRIMARY", "F3"):
        b, f = mb[seg], mf[seg]
        dd_ok = f["dd"] <= 0.8 * b["dd"]
        ev_ok = f["net_ev"] >= 0.9 * b["net_ev"]
        g4_ok = f["pos_assets"] >= 7
        gates.append(dd_ok and ev_ok and g4_ok)
        print(f"{seg:>7}: base DD={b['dd']:.0%} EV={b['net_ev']:+.2f}R "
              f"| F6 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"neg 12m windows: base {neg_windows(ctxs, data['base'])} "
          f"-> F6 {neg_windows(ctxs, data['filt'])}")
    print(f"F6 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
