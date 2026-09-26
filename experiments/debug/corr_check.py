# -*- coding: utf-8 -*-
"""Correlation check (diagnostic, no gates): AVSL-cross S1 vs
AVS-channel S1 per-bar P&L streams, requested 2026-09-24.

Both streams: identical S1 sizing (clip(0.20/rv100, 0.25, 2.0),
NaN fallback 1.0) applied to the frozen trade tables; identical
accrual bookkeeping (engine.passed.avsl_cross_s1.
sized_accrual_stream); identical global 4H grid.  Read-outs:
Pearson + Spearman per segment, stream stats, 50/50 combined
stream diagnostic.  Diagnostic only -- no prereg, no verdict.

Run:  python -m experiments.debug.corr_check
"""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SIZE_MAX,
    SIZE_MIN,
    VOL_TARGET,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
    sized_accrual_stream,
)
from experiments.avsl.channel.risk_overlay_mirror import _sizing_inputs
from experiments.avsl.channel.channel_breakout import collect_channel_trades


def _s1_sizes_from_rv(rv: np.ndarray) -> np.ndarray:
    """Same formula as the S1 gate config, incl. NaN fallback 1.0."""
    out = np.ones(len(rv))
    for i, r in enumerate(rv):
        if np.isfinite(r) and r > 0:
            out[i] = float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX))
    return out


def _avsl_stream(n_g: int, off: dict) -> tuple[np.ndarray, int]:
    stream = np.zeros(n_g)
    n_tr = 0
    for s in ASSETS:
        d = collect_trades(s)
        repo = repo_root()
        _ts, _hp, _lp, cp, _vol = read_1h(repo, s)
        _ts, _hp, _lp, cp, _vol = resample_4h(_ts, _hp, _lp, cp, _vol)
        sizes = _s1_sizes_from_rv(_sizing_inputs(s)[0])
        st = sized_accrual_stream(d["trades"], sizes, len(cp))
        o = off[s]
        stream[o:o + len(st)] += st
        n_tr += len(d["trades"])
    return stream, n_tr


def _channel_stream(n_g: int, off: dict) -> tuple[np.ndarray, int]:
    stream = np.zeros(n_g)
    n_tr = 0
    for s in ASSETS:
        d = collect_channel_trades(s)
        rv = _sizing_inputs(s)[0]
        sizes = _s1_sizes_from_rv(rv)
        st = sized_accrual_stream(d["trades"], sizes, len(sizes))
        o = off[s]
        stream[o:o + len(st)] += st
        n_tr += len(d["trades"])
    return stream, n_tr


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def _stats(name: str, v: np.ndarray) -> None:
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    print(f"  {name}: mean {v.mean() * 1e4:+.2f}bp/bar  std "
          f"{v.std() * 1e4:.2f}bp  sum {v.sum():+.1f}R  "
          f"maxDD {dd:.2f}R", flush=True)


def main() -> None:
    repo = repo_root()
    starts, ends = {}, {}
    for s in ASSETS:
        ts, *_rest = read_1h(repo, s)
        ts, *_rest = resample_4h(ts, *_rest)
        starts[s] = int(ts[0] // 14_400_000)
        ends[s] = int(ts[-1] // 14_400_000)
    g0 = min(starts.values())
    n_g = max(ends.values()) - g0 + 1
    off = {s: starts[s] - g0 for s in ASSETS}
    split = int(n_g * 2 / 3)

    print(f"global 4H grid n={n_g}, PRIMARY<{split}<=F3", flush=True)
    a, n_a = _avsl_stream(n_g, off)
    c, n_c = _channel_stream(n_g, off)
    print(f"AVSL S1: {n_a} trades; channel S1: {n_c} trades\n",
          flush=True)

    comb = 0.5 * (a + c)
    _stats("AVSL-cross S1 ", a)
    _stats("AVS-channel S1", c)
    _stats("50/50 combined", comb)

    print("", flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g),
                        ("FULL", 0, n_g)):
        va, vc = a[lo:hi], c[lo:hi]
        act = np.isfinite(va) & np.isfinite(vc)
        pr = float(np.corrcoef(va, vc)[0, 1])
        sp = _spearman(va, vc)
        print(f"  {seg:>7}: Pearson {pr:+.3f}  Spearman {sp:+.3f}",
              flush=True)

    # overlap of activity: bars where each stream is nonzero
    an, cn = a != 0, c != 0
    both = int(np.sum(an & cn))
    print(f"\nactive bars: AVSL {int(an.sum())}, channel "
          f"{int(cn.sum())}, both {both}", flush=True)
    print("DIAGNOSTIC ONLY -- no gates, no verdict.", flush=True)


if __name__ == "__main__":
    main()
