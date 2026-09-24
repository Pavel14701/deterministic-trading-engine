# -*- coding: utf-8 -*-
"""Portfolio-layer one-shot: 50/50 AVSL-cross S1 + AVS-channel
S1 (prereg frozen in STATUS 2026-09-24, BEFORE this run).

Gates: PF-G1 Sharpe_NW >= 1.0 both segments; PF-G2 event DD
<= 30% both segments; PF-G3 block bootstrap CI excludes 0
both; PF-G4 honest layer -- every trailing 12m window (2190
bars) positive cumulative R.  Combination 0.5/0.5, streams
exactly as corr_check builds them (frozen S1 sizing).

Run:  python -m experiments.avsr.portfolio_layer
"""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    RISK_PCT,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsr.corr_check import _avsl_stream, _channel_stream
from experiments.avsr.risk_overlay_mirror import (
    ANN,
    BOOT_B,
    HORIZON,
    NW_LAGS,
    _block_boot_mean_ci,
    _nw_sharpe,
)


def _grid() -> tuple[int, dict, int]:
    starts, ends = {}, {}
    for s in ASSETS:
        ts, hp, lp, cp, vol = read_1h(repo_root(), s)
        ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
        starts[s] = int(ts[0] // 14_400_000)
        ends[s] = int(ts[-1] // 14_400_000)
    g0 = min(starts.values())
    n_g = max(ends.values()) - g0 + 1
    return n_g, {s: starts[s] - g0 for s in ASSETS}, n_g // 3 * 2

DD_CAP = 0.30
W12M = 2190          # 365d x 6 x 4H bars


def main() -> None:
    n_g, off, split = _grid()

    a, n_a = _avsl_stream(n_g, off)
    c, n_c = _channel_stream(n_g, off)
    p = 0.5 * (a + c)
    print(f"PORTFOLIO-LAYER one-shot: 50/50 AVSL({n_a}) + "
          f"channel({n_c}); grid n={n_g}, PRIMARY<{split}<=F3",
          flush=True)

    fails: list[str] = []
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        v = p[lo:hi]
        sh = _nw_sharpe(v, NW_LAGS, ANN)
        ok1 = sh >= 1.0
        if not ok1:
            fails.append(f"PF-G1:{seg}")
        eq = np.cumprod(1.0 + RISK_PCT * v)
        dd = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
        ok2 = dd <= DD_CAP
        if not ok2:
            fails.append(f"PF-G2:{seg}")
        lo_ci, hi_ci = _block_boot_mean_ci(v, BOOT_B, HORIZON)
        ok3 = lo_ci > 0
        if not ok3:
            fails.append(f"PF-G3:{seg}")
        print(f"  {seg:>7}: PF-G1 Sh_NW={sh:+.2f}"
              f"{'P' if ok1 else 'F'} | PF-G2 DD={dd:.1%} "
              f"(cap {DD_CAP:.0%}){'P' if ok2 else 'F'} | "
              f"PF-G3 CI [{lo_ci:+.5f},{hi_ci:+.5f}]"
              f"{'P' if ok3 else 'F'}", flush=True)

    # PF-G4: every trailing 12m window positive cumulative R
    roll = np.convolve(p, np.ones(W12M), mode="valid")
    n_neg = int(np.sum(roll <= 0))
    ok4 = n_neg == 0
    if not ok4:
        fails.append("PF-G4")
    print(f"  12m windows: {len(roll)} trailing windows, "
          f"min cumR {roll.min():+.2f}R at worst window; "
          f"negative windows {n_neg} -> "
          f"{'PASS' if ok4 else 'FAIL'}", flush=True)

    eq = np.cumprod(1.0 + RISK_PCT * p)
    dd_full = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
    print(f"  read-out: full-period DD {dd_full:.1%}, "
          f"sum {p.sum():+.1f}R", flush=True)

    print("\n==== PORTFOLIO-LAYER VERDICT ====", flush=True)
    if fails:
        print(f"FAIL: {', '.join(fails)} -> portfolio layer "
              f"CLOSED, tracks stay LATENT", flush=True)
    else:
        print("PASS (PF-G1..PF-G4) -> portfolio 50/50 is "
              "DEPLOYABLE-CANDIDATE; next layer: execution "
              "prereg (P4-EX honest pattern) before capital",
              flush=True)


if __name__ == "__main__":
    main()
