# -*- coding: utf-8 -*-
"""Diagnostic: why did Sharpe fall under the frozen NW metric?
Descriptive post-mortem (STATUS 2026-09-25).  No gates."""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,
    ASSETS,
    NW_LAGS,
    SPLIT_FRAC,
    repo_root,
)
from experiments.avsl.tp1.tp1_checks import collect_all


def lag_sum(v: np.ndarray, kmax: int) -> float:
    s = 0.0
    for k in range(1, min(kmax, v.size - 10) + 1):
        c = np.corrcoef(v[:-k], v[k:])[0, 1]
        if np.isfinite(c):
            s += c
    return s


def build_stream(ctxs, trades, seg_lo, seg_hi, g0g, n_g):
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        if not (seg_lo <= e0 < seg_hi):
            continue
        hold = max(e1 - e0, 1)
        s[e0:e1 + 1] += c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
    return s[seg_lo:seg_hi]


def main() -> None:
    repo = repo_root()
    envs, ctxs, base_tr, ftp1_tr = collect_all(repo)
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)

    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        print(f"===== {seg} =====")
        for name, tr_all in (("baseline", base_tr), ("F-TP1", ftp1_tr)):
            tr_seg = []
            for t in tr_all:
                e0 = t["e0"] + ctxs[t["sym"]]["g0"] - g0g
                if lo <= e0 < hi:
                    tr_seg.append(t)
            v = build_stream(ctxs, tr_all, lo, hi, g0g, n_g)
            plain = v.mean() / v.std() * np.sqrt(ANN)
            s50 = lag_sum(v, 50)
            s500 = lag_sum(v, NW_LAGS)
            f50 = np.sqrt(max(1e-6, 1 + 2 * s50))
            f500 = np.sqrt(max(1e-6, 1 + 2 * s500))
            r = np.array([t["net"] for t in tr_seg])
            hold = np.array([max(t["e1"] - t["e0"], 1)
                             for t in tr_seg])
            sr = r.mean() / r.std()
            print(f"{name:>8}: n={len(r)} plain_ann={plain:+.2f} "
                  f"NW={plain / f500:+.2f}")
            print(f"         lag-sums: k<=50 {s50:+.1f} "
                  f"k<=500 {s500:+.1f} | factor50 {f50:.1f} "
                  f"factor500 {f500:.1f} | eff_n {v.size / f500**2:.0f} "
                  f"of {v.size}")
            print(f"         per-trade: SR {sr:+.3f} t={sr * np.sqrt(len(r)):+.1f} "
                  f"| hold med {np.median(hold):.0f} p90 "
                  f"{np.percentile(hold, 90):.0f} max {hold.max()} "
                  f"| holds>500bars: {(hold > 500).sum()}")
            for k in (1, 5, 20):
                r2 = np.sort(r)[:-k]
                sr2 = r2.mean() / r2.std()
                print(f"         ex-top{k}: SR {sr2:+.3f} "
                      f"mean {r2.mean():+.3f}R | top{k} share "
                      f"{np.sort(r)[-k:].sum() / r.sum():.0%}")


if __name__ == "__main__":
    main()
