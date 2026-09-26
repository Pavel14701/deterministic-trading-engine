# -*- coding: utf-8 -*-
"""Family-diversification diagnostic (2026-09-24, no gates, no
verdict): AVSL-cross S1 (A) vs AVS-channel S1 (B) vs OB E8b S1
(C, R2 preset post-fix, TRUE-grid placement).

Read-outs requested by the principal:
  1. 3x3 per-bar P&L correlation (Pearson + Spearman), by segment.
  2. Top-5 DD episodes per stream + temporal overlap between
     families (the key question: do AVS regime holes and OB
     whipsaw holes coincide?).
  3. Combined portfolios 50/50 A+C, B+C, 33/33/33 A+B+C
     (A+B already measured): full-period DD, raw + NW Sharpe
     (NW degeneracy caveat: lags=500 factor can blow up),
     PF-G4 trailing-12m negative-window counts.

Run:  python -m experiments.debug.avs_ob_portfolio_check
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import ASSETS, MSEC_4H
from experiments.debug.corr_check import _avsl_stream, _channel_stream
from experiments.avsl.portfolio_layer import _grid
from experiments.ob.ob_risk_overlay import (
    apply_arm,
    base_trades,
    decorate,
    sizing_aux,
    stream_of,
)
from experiments.avsl.retest_entry import _env

W12M = 2190
TOP_K = 5


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def _raw_sharpe(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan")
    return float(v.mean() / v.std() * np.sqrt(6 * 365))


def _dd_pct(v: np.ndarray) -> float:
    eq = np.cumprod(1.0 + 0.01 * v)
    return float(np.max(1.0 - eq / np.maximum.accumulate(eq)))


def _dd_episodes(v: np.ndarray, t0_ms: int, k: int = TOP_K) -> list[dict]:
    """Top-k peak-to-recovery drawdown episodes by depth."""
    eq = np.cumprod(1.0 + 0.01 * v)
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    eps: list[dict] = []
    i = 0
    n = len(v)
    while i < n:
        if dd[i] <= 0:
            i += 1
            continue
        j = i
        while j < n and dd[j] > 0:
            j += 1
        seg = dd[i:j]
        depth = float(seg.max())
        trough = i + int(np.argmax(seg))
        eps.append({
            "depth": depth,
            "lo": i,
            "hi": j,
            "trough": trough,
        })
        i = j
    eps.sort(key=lambda e: -e["depth"])
    for e in eps[:k]:
        e["lo_d"] = dt.datetime.utcfromtimestamp(
            (t0_ms + e["lo"] * MSEC_4H) / 1000).date()
        e["hi_d"] = dt.datetime.utcfromtimestamp(
            (t0_ms + min(e["hi"], n - 1) * MSEC_4H) / 1000).date()
    return eps[:k]


def _overlap(a: list[dict], b: list[dict]) -> float:
    """Fraction of A's top-K episodes whose [lo,hi] intersects
    any of B's top-K episodes."""
    if not a:
        return float("nan")
    hit = 0
    for e in a:
        for f in b:
            if e["lo"] <= f["hi"] and f["lo"] <= e["hi"]:
                hit += 1
                break
    return hit / len(a)


def _pf4(v: np.ndarray) -> tuple[int, int, float]:
    roll = np.convolve(v, np.ones(W12M), mode="valid")
    return int(np.sum(roll <= 0)), len(roll), float(roll.min())


def main() -> None:
    from engine.passed.avsl_cross_s1 import repo_root

    n_g, off, split = _grid()
    a, n_a = _avsl_stream(n_g, off)
    b, n_b = _channel_stream(n_g, off)

    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0_min = min(e["g0"] for e in envs.values())
    t0_ms = g0_min * MSEC_4H
    aux = sizing_aux(repo)
    trades = base_trades(envs)
    decorate(trades, envs, aux, g0_min)
    kept, n_skip = apply_arm("S1", trades)
    c = stream_of(kept, n_g)
    print(f"streams on grid n={n_g} (OB n_g check: "
          f"{max(e['n_bars'] + e['g0'] for e in envs.values()) - g0_min}), "
          f"PRIMARY<{split}<=F3")
    print(f"trades: A={n_a}, B={n_b}, C={len(kept)} "
          f"(OB S1 skipped {n_skip})\n", flush=True)

    names = ("A:AVSL", "B:CHAN", "C:OB")
    streams = (a, b, c)
    print("== 1. correlation matrix (per-bar) ==")
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        print(f"  -- {seg} --")
        for p, q in ((0, 1), (0, 2), (1, 2)):
            va, vc = streams[p][lo:hi], streams[q][lo:hi]
            print(f"    {names[p]} <-> {names[q]}: "
                  f"Pearson {np.corrcoef(va, vc)[0, 1]:+.3f}  "
                  f"Spearman {_spearman(va, vc):+.3f}", flush=True)

    print("\n== 2. top-5 DD episodes (depth, span) + overlap ==")
    eps = {}
    for k2, nm in zip(streams, names):
        e = _dd_episodes(k2, t0_ms)
        eps[nm] = e
        print(f"  {nm}:")
        for x in e:
            print(f"    {x['depth']:5.1%}  {x['lo_d']} -> {x['hi_d']}",
                  flush=True)
    for p, q in ((0, 1), (0, 2), (1, 2)):
        ov = _overlap(eps[names[p]], eps[names[q]])
        print(f"  overlap top-5: {names[p]} vs {names[q]}: {ov:.0%}")

    print("\n== 3. combined portfolios ==")
    combos = {
        "50/50 A+B": 0.5 * (a + b),
        "50/50 A+C": 0.5 * (a + c),
        "50/50 B+C": 0.5 * (b + c),
        "33/33/33": (a + b + c) / 3.0,
    }
    for nm, v in combos.items():
        neg, tot, worst = _pf4(v)
        print(f"  {nm}: DD {_dd_pct(v):.1%}  "
              f"rawSh {_raw_sharpe(v):+.2f}  "
              f"12m neg windows {neg}/{tot} "
              f"(worst {worst:+.1f}R)", flush=True)
    print(f"  individual: A DD {_dd_pct(a):.1%} "
          f"(12m neg {_pf4(a)[0]}), B DD {_dd_pct(b):.1%} "
          f"(12m neg {_pf4(b)[0]}), C DD {_dd_pct(c):.1%} "
          f"(12m neg {_pf4(c)[0]})", flush=True)
    print("\nDIAGNOSTIC ONLY -- no gates, no verdict.", flush=True)


if __name__ == "__main__":
    main()
