# -*- coding: utf-8 -*-
"""F7 Market-structure filter -- frozen prereg (STATUS
2026-09-25, AVSL TREND-FILTER PROGRAM, F7 SPEC).  One pass.

5-bar fractal swings (k=2 neighbours each side) on 4H highs /
lows.  A swing at bar i is CONFIRMED at bar i+2 (no lookahead).
Structure up iff the last two confirmed swing highs are HH AND
the last two confirmed swing lows are HL; down iff LH AND LL;
otherwise no structure -> trade dropped.  Keep long in up
structure, short in down structure.
"""
from __future__ import annotations

import numpy as np

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

K = 2


def structure_at(hp: np.ndarray, lp: np.ndarray,
                 t: int) -> int:
    """+1 up (HH & HL), -1 down (LH & LL), 0 none, at bar t."""
    n = len(hp)
    shs, sls = [], []
    for i in range(K, min(t - K, n - K)):
        if hp[i] > hp[i - 1] and hp[i] > hp[i - 2] \
                and hp[i] > hp[i + 1] and hp[i] > hp[i + 2]:
            shs.append(hp[i])
        if lp[i] < lp[i - 1] and lp[i] < lp[i - 2] \
                and lp[i] < lp[i + 1] and lp[i] < lp[i + 2]:
            sls.append(lp[i])
    if len(shs) < 2 or len(sls) < 2:
        return 0
    hh = shs[-1] > shs[-2]
    hl = sls[-1] > sls[-2]
    if hh and hl:
        return 1
    if (not hh) and (not hl):
        return -1
    return 0


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
        ctxs[sym] = {"ts4": ts4, "sizes": s1_sizes(cp4),
                     "g0": d["g0"], "n_bars": d["n_bars"],
                     "trades": d["trades"]}
        for tr in d["trades"]:
            data["base"].append({**tr, "sym": sym})
            st = structure_at(hp4, lp4, tr["e0"])
            want = 1 if tr["long"] else -1
            if st == want:
                data["filt"].append({**tr, "sym": sym})

    nb, nf = len(data["base"]), len(data["filt"])
    print(f"== F7 ==\ntrades: base {nb} -> filtered {nf} "
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
              f"| F7 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"neg 12m windows: base {neg_windows(ctxs, data['base'])} "
          f"-> F7 {neg_windows(ctxs, data['filt'])}")
    print(f"F7 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
