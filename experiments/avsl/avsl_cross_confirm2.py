# -*- coding: utf-8 -*-
"""AVSL-cross 4H confirm -- overlap-corrected G1'/G2'/G5' recompute
(STATUS 2026-09-21 addendum, frozen BEFORE recompute).

Per-bar portfolio R stream: every open trade accrues net R linearly
over its hold buckets; account return per bar = 1% x stream (1%
risk per trade slot, concurrent).

G1' Sharpe_NW >= 1.0 on the accrual stream (lags 500, ann sqrt(6*365)),
PRIMARY and F3.
G2' event DD <= 25% on PRIMARY equity (cumprod of 1% x stream).
G5' circular block bootstrap on the bar stream (block = 500 buckets
= HORIZON, B=1000): 95% CI of mean bar R excludes 0 in PRIMARY and
in F3.  Per-asset counts = diagnostics only.

Run:  uv run python -m experiments.avsl.avsl_cross_confirm2
"""

from __future__ import annotations

import numpy as np

from experiments.avsl.avsl_cross_confirm import (
    ANN,
    BOOT_B,
    NW_LAGS,
    _collect,
    _nw_sharpe,
)
from experiments.avsl.avsl_cross_tf import ASSETS


TP_PRIMARY = 5.0
HORIZON = 500
RISK_PCT = 0.01
G1_SHARPE = 1.0
G2_DD = 0.25


def _accrual_stream(trs, n_g: int) -> np.ndarray:
    s = np.zeros(n_g + 1)
    for tr in trs:
        hold = max(tr["e1"] - tr["e0"], 1)
        s[tr["e0"]:tr["e1"] + 1] += tr["net"] / (hold + 1)
    return s[:n_g]


def _block_boot_mean_ci(v: np.ndarray, b: int, block: int):
    n = v.size
    rng = np.random.default_rng(11)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(b, n_blocks))
    means = np.empty(b)
    for i in range(b):
        idx = np.concatenate(
            [(np.arange(starts[i, j], starts[i, j] + block)) % n
             for j in range(n_blocks)]
        )[:n]
        means[i] = v[idx].mean()
    return float(np.percentile(means, 2.5)), \
        float(np.percentile(means, 97.5))


def main() -> None:
    data = {s: _collect(s) for s in ASSETS}
    g0 = min(d["g0"] for d in data.values())
    n_g = max(d["n_bars"] + d["g0"] for d in data.values()) - g0
    split = int(n_g * 2 / 3)
    print(f"global 4H grid: n={n_g}, PRIMARY<{split}<=F3", flush=True)

    trs = []
    for s, d in data.items():
        for t in d["trades"]:
            if t["tp"] == TP_PRIMARY:
                trs.append({**t, "sym": s})
    print(f"TP=5R trades: {len(trs)}", flush=True)

    stream = _accrual_stream(trs, n_g)
    print(f"stream: mean bar R={stream.mean():+.5f}", flush=True)

    fails = []

    # ---- G1' Sharpe_NW on the accrual stream
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        sh = _nw_sharpe(stream[lo:hi], NW_LAGS, ANN)
        ok = sh >= G1_SHARPE
        if not ok:
            fails.append(("G1p", seg))
        print(f"G1' {seg}: Sharpe_NW(accrual)={sh:+.2f} "
              f"(need >={G1_SHARPE}) -> {'PASS' if ok else 'FAIL'}",
              flush=True)

    # ---- G2' event DD on PRIMARY equity (1% risk per slot)
    eq = np.cumprod(1.0 + RISK_PCT * stream[:split])
    dd = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
    ok = dd <= G2_DD
    if not ok:
        fails.append(("G2p", "PRIMARY"))
    print(f"G2' PRIMARY: portfolio DD={dd:.1%} (cap {G2_DD:.0%}) "
          f"-> {'PASS' if ok else 'FAIL'}", flush=True)
    eq_f = np.cumprod(1.0 + RISK_PCT * stream[split:])
    dd_f = float(np.max(1.0 - eq_f / np.maximum.accumulate(eq_f)))
    print(f"    (info) F3 portfolio DD={dd_f:.1%}", flush=True)

    # ---- G5' block bootstrap on bar stream, block = HORIZON
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        lo_ci, hi_ci = _block_boot_mean_ci(
            stream[lo:hi], BOOT_B, HORIZON
        )
        ok = lo_ci > 0
        if not ok:
            fails.append(("G5p", seg))
        print(f"G5' {seg}: 95% CI mean bar R [{lo_ci:+.5f}, "
              f"{hi_ci:+.5f}] -> {'PASS' if ok else 'FAIL'}",
              flush=True)

    # per-asset diagnostics (not gating)
    n_exc = 0
    for s in ASSETS:
        trs_s = [t for t in trs if t["sym"] == s]
        st = _accrual_stream(trs_s, n_g)
        lo_ci, hi_ci = _block_boot_mean_ci(
            st, max(200, BOOT_B // 2), HORIZON
        )
        exc = lo_ci > 0
        n_exc += exc
        print(f"  diag {s:>5}: CI [{lo_ci:+.5f}, {hi_ci:+.5f}] "
              f"{'EXCL 0' if exc else ''}", flush=True)
    print(f"  diag: {n_exc}/10 per-asset streams exclude 0 "
          "(informational)", flush=True)

    print("\n==== CORRECTED VERDICT (with G3/G4/G6 already PASS) ====",
          flush=True)
    if fails:
        print(f"FAIL: {fails}\n-> AVSL-cross entry family CLOSED FINAL",
              flush=True)
    else:
        print("ALL CORRECTED GATES PASS -> signal CONFIRMED",
              flush=True)


if __name__ == "__main__":
    main()
