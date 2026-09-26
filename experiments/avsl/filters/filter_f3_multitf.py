# -*- coding: utf-8 -*-
"""F3 Multi-TF filter -- frozen prereg (STATUS 2026-09-25,
AVSL TREND-FILTER PROGRAM, F3 SPEC).  One pass.

Keep long iff F1 daily rule AND 4H close(entry bar) >
SMA200(4H closes up to and incl. entry bar); mirrored short.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    collect_trades,
    evaluate,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.filters.filter_f1_htf import (
    DAY,
    SMA_N as DAILY_SMA,
    daily_closes,
    neg_windows,
    stream_metrics,
)


def build_ctx(repo, sym: str) -> dict:
    ts1, hp1, lp1, cp1, vol1 = read_1h(repo, sym)
    ts4, _hp, _lp, cp4, _vol = resample_4h(ts1, hp1, lp1, cp1, vol1)
    d = collect_trades(sym, repo)
    dk, dc = daily_closes(ts1, cp1)
    return {"ts4": ts4, "cp4": cp4, "sizes": s1_sizes(cp4),
            "dkeys": dk, "dc": dc, "g0": d["g0"],
            "n_bars": d["n_bars"], "trades": d["trades"]}


def sma_arr(cp: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(cp), np.nan)
    if len(cp) >= n:
        c = np.cumsum(np.insert(cp, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def f1_keep(c: dict, tr: dict) -> bool:
    t4 = tr["e0"]
    m = int(c["ts4"][t4]) + MSEC_4H
    di = m // DAY - 1
    j = int(np.searchsorted(c["dkeys"], di, side="right")) - 1
    if j < DAILY_SMA or c["dkeys"][j] != di:
        return False
    c_prev = c["dc"][j]
    sma = float(np.mean(c["dc"][j - DAILY_SMA + 1:j + 1]))
    return bool(c_prev > sma) if tr["long"] else bool(c_prev < sma)


def f3_keep(c: dict, sma: np.ndarray, tr: dict) -> bool:
    if not f1_keep(c, tr):
        return False
    t4 = tr["e0"]
    s = sma[t4]
    if not np.isfinite(s):
        return False
    px = c["cp4"][t4]
    return bool(px > s) if tr["long"] else bool(px < s)


def main() -> None:
    repo = repo_root()
    base = evaluate()
    ok = (abs(base["PRIMARY"]["net_ev"] - 0.17) < 0.05
          and abs(base["F3"]["net_ev"] - 0.33) < 0.05)
    print(f"baseline sanity: {'OK' if ok else 'DEVIATION - ABORT'}")
    if not ok:
        return

    ctxs = {sym: build_ctx(repo, sym) for sym in ASSETS}
    smas = {sym: sma_arr(ctxs[sym]["cp4"], 200) for sym in ASSETS}
    data = {"base": [], "filt": []}
    for sym in ASSETS:
        for tr in ctxs[sym]["trades"]:
            data["base"].append({**tr, "sym": sym})
            if f3_keep(ctxs[sym], smas[sym], tr):
                data["filt"].append({**tr, "sym": sym})

    nb, nf = len(data["base"]), len(data["filt"])
    print(f"== F3 ==\ntrades: base {nb} -> filtered {nf} "
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
              f"| F3 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"neg 12m windows: base {neg_windows(ctxs, data['base'])} "
          f"-> F3 {neg_windows(ctxs, data['filt'])}")
    print(f"F3 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
