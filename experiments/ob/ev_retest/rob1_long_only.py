# -*- coding: utf-8 -*-
"""R-OB-1 -- OB long-only (demand blocks), prereg 44a0c75
(STATUS, 2026-09-23, frozen before this code).

Signal: R2 preset DEMAND blocks only, retest-bar entry, stop
3xATR14, TP {3,5,8}R PRIMARY=5R, horizon 500, fee 10bp RT,
WARMUP 400, 10 assets, split 2/3.  TRUE global grid alignment
(declared in the prereg; no legacy-index numbers produced).

Single gate config: S1 vol-target sizing (frozen-module formula).
Gates per segment: G1' Sharpe >= 1.0 (nw_sharpe; if the NW
autocorrelation sum < -0.5 the factor is degenerate and the plain
annualized Sharpe is the G1' input -- frozen metric rule),
G2' DD <= 25%, G3' net EV >= 0.10R, G4' >= 7/10 assets positive,
G5' block bootstrap CI (B=1000, block 500) excludes 0.
KILL: any gate FAIL -> R-OB-1 CLOSED.

Read-outs: raw-1x DD, per-asset EV, ATR-pct quintiles, corr vs
the AVSL S1 true-aligned stream, TP {3,8}R EV, matched-geometry
null (long-only counts, seeds 0..99) as percentiles.

Run:  uv run python -m experiments.ob.ev_retest.rob1_long_only
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,
    ASSETS,
    SPLIT_FRAC,
    block_bootstrap_ci,
    collect_trades,
    nw_sharpe,
    portfolio_dd,
    repo_root,
    s1_sizes,
)
from experiments.avsl.retest.retest_entry import HORIZON, N_DRAWS, WARMUP
from experiments.ob.ev_retest.ob_risk_overlay import (
    TP_GRID,
    TP_PRIMARY,
    _env,
    _trade_tp,
    base_trades,
    decorate,
    sizing_aux,
)


BOOT_B = 1000
G1_SHARPE = 1.0
G2_DD = 0.25
G3_EV = 0.10
G4_ASSETS = 7
NW_RHO_FLOOR = -0.5


def gate_sharpe(v: np.ndarray) -> tuple[float, bool]:
    """(G1' input, degenerate flag) per the frozen metric rule:
    plain annualized Sharpe replaces nw_sharpe only when the NW
    autocorrelation sum < -0.5 (factor floored -> metric void)."""
    vv = v[np.isfinite(v)]
    if vv.size < 30 or vv.std() == 0:
        return float("nan"), False
    rhos = []
    for k in range(1, min(500, vv.size - 10) + 1):
        c = np.corrcoef(vv[:-k], vv[k:])[0, 1]
        if np.isfinite(c):
            rhos.append(c)
    if rhos and float(np.sum(rhos)) < NW_RHO_FLOOR:
        return float(vv.mean() / vv.std() * np.sqrt(ANN)), True
    return nw_sharpe(v), False


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0_min = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0_min
    split = int(n_g * SPLIT_FRAC)
    aux = sizing_aux(repo)
    trades = [t for t in base_trades(envs) if t["long"]]
    decorate(trades, envs, aux, g0_min)
    print(f"[rob1] long entries={len(trades)} "
          f"grid n={n_g} split={split}", flush=True)

    stream = np.zeros(n_g + 1)
    raw = np.zeros(n_g + 1)
    for t in trades:
        w = t["s1"] * t["net"]
        hold = max(t["e1"] - t["e0"], 1)
        stream[t["e0"]:t["e1"] + 1] += w / (hold + 1)
        raw[t["e0"]:t["e1"] + 1] += t["net"] / (hold + 1)
    stream, raw = stream[:n_g], raw[:n_g]

    fails: list[str] = []
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        sv = stream[lo:hi]
        sh, degen = gate_sharpe(sv)
        dd = portfolio_dd(sv)
        seg_tr = [t for t in trades if lo <= t["e0"] < hi]
        ev = float(np.mean([t["net"] for t in seg_tr]))
        pos = 0
        for sym in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        lo_ci, hi_ci = block_bootstrap_ci(sv, BOOT_B, HORIZON)
        checks = {
            "G1p": sh >= G1_SHARPE, "G2p": dd <= G2_DD,
            "G3p": ev >= G3_EV, "G4p": pos >= G4_ASSETS,
            "G5p": lo_ci > 0,
        }
        fails.extend(k for k, ok in checks.items() if not ok)
        print(f"{seg:>7} (n={len(seg_tr)}): "
              f"G1' {'plain' if degen else 'NW'} Sh={sh:+.2f}"
              f"{'P' if checks['G1p'] else 'F'} | "
              f"G2' DD={dd:.0%}{'P' if checks['G2p'] else 'F'} | "
              f"G3' EV={ev:+.3f}R{'P' if checks['G3p'] else 'F'} | "
              f"G4' {pos}/10{'P' if checks['G4p'] else 'F'} | "
              f"G5' [{lo_ci:+.5f},{hi_ci:+.5f}]"
              f"{'P' if checks['G5p'] else 'F'}", flush=True)
    if fails:
        print(f"\nR-OB-1 VERDICT: FAIL ({fails}) -> R-OB-1 CLOSED "
              "per prereg 44a0c75", flush=True)
    else:
        print("\nR-OB-1 VERDICT: PASS 5/5 both segments "
              "(prereg 44a0c75)", flush=True)

    print(f"  raw-1x sensitivity: PRIMARY DD="
          f"{portfolio_dd(raw[:split]):.0%} F3 DD="
          f"{portfolio_dd(raw[split:]):.0%}", flush=True)

    print("  per-asset EV (pooled):", flush=True)
    for sym in ASSETS:
        v = [t["net"] for t in trades if t["sym"] == sym]
        print(f"    {sym:>5}: n={len(v):>4} "
              f"EV={float(np.mean(v)):+.3f}R", flush=True)

    print("  ATR-pct quintile x EV:", flush=True)
    for q in range(5):
        lo_q, hi_q = q * 20, (q + 1) * 20
        sel = [t["net"] for t in trades
               if np.isfinite(t["pct"]) and lo_q < t["pct"] <= hi_q]
        ev = f"{float(np.mean(sel)):+.3f}R" if sel else "n/a"
        print(f"    Q{q + 1} ({lo_q:>3},{hi_q:>3}]: n={len(sel):>4} "
              f"EV={ev}", flush=True)

    avsl = np.zeros(n_g + 1)
    for sym in ASSETS:
        d = collect_trades(sym, repo)
        sizes = s1_sizes(aux[sym][2])
        for t in d["trades"]:
            e0 = d["g0"] + t["e0"] - g0_min
            e1 = d["g0"] + t["e1"] - g0_min
            hold = max(e1 - e0, 1)
            avsl[e0:e1 + 1] += sizes[t["e0"]] * t["net"] / (hold + 1)
    avsl = avsl[:n_g]
    print("  corr(rob1 S1, AVSL S1) per segment:", flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        c = float(np.corrcoef(stream[lo:hi], avsl[lo:hi])[0, 1])
        print(f"    {seg:>7}: r={c:+.2f}", flush=True)

    print("  TP grid EV (descriptive):", flush=True)
    for tp in TP_GRID:
        if tp == TP_PRIMARY:
            continue
        for seg, lo, hi in (("PRIMARY", 0, split),
                            ("F3", split, n_g)):
            vals = [t["by_tp"][tp] for t in trades
                    if lo <= t["e0"] < hi]
            vals = [v for v in vals if v is not None]
            print(f"    TP {tp:.0f}R {seg:>7}: "
                  f"EV={float(np.mean(vals)):+.3f}R "
                  f"(n={len(vals)})", flush=True)

    match = {s: sum(1 for t in trades if t["sym"] == s)
             for s in ASSETS}
    null: dict = {"PRIMARY": [], "F3": []}
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        draw: dict = {"PRIMARY": [], "F3": []}
        for s in ASSETS:
            if match[s] == 0:
                continue
            env = envs[s]
            hi_bar = int(env["b"][-1]) - env["g0"] - 1
            bars = rng.choice(np.arange(WARMUP, hi_bar),
                              size=match[s], replace=False)
            for t in bars:
                tr = _trade_tp(env, int(t), True, TP_PRIMARY)
                if tr is None:
                    continue
                e0 = env["g0"] + tr["e0"] - g0_min
                draw["PRIMARY" if e0 < split else "F3"] \
                    .append(tr["net"])
        for seg in ("PRIMARY", "F3"):
            if draw[seg]:
                null[seg].append(float(np.mean(draw[seg])))
    print("  matched-geometry null (descriptive):", flush=True)
    for seg in ("PRIMARY", "F3"):
        nv = np.array(null[seg])
        ev = float(np.mean([t["net"] for t in trades
                            if (t["e0"] < split) == (seg == "PRIMARY")]))
        pct = float((nv < ev).mean() * 100)
        print(f"    {seg:>7}: EV {ev:+.3f} vs {nv.mean():+.3f}"
              f"+-{nv.std():.3f} -> {pct:.0f}th pct", flush=True)


if __name__ == "__main__":
    main()

