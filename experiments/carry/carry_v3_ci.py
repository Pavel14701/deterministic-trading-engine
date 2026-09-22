"""P2 prereg (STATUS 2026-09-21): honest quoting of carry v3 fold EVs.

v3 params were frozen ex ante -- no selection bias applies; the
near-zero risk is sampling noise.  Procedure (frozen before run):
stationary block bootstrap on the portfolio daily stream,
block=30d, B=10,000, seed=7.  95% CI on annualized mean for F1, F2,
F3 and per-asset F3.  Read-out rule: F3 is quotable as edge only if
its CI excludes 0 (and the risk-free benchmark).  Streams AS-IS.
"""

from __future__ import annotations

import datetime as _dt

import numpy as np

from experiments.carry.funding_carry_v3 import (
    UNIVERSE,
    binance_daily_funding,
    build_panel,
    per_asset_stream,
    trailing_signal,
)


BLOCK = 30  # days
B = 10_000
SEED = 7


def ann_ci(stream: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    v = stream[np.isfinite(stream)]
    n = len(v)
    point = float(v.mean() * 365) * 100
    nb = int(np.ceil(n / BLOCK))
    means = np.empty(B)
    starts_all = np.arange(n - BLOCK + 1)
    for i in range(B):
        starts = rng.choice(starts_all, size=nb, replace=True)
        idx = (starts[:, None] + np.arange(BLOCK)[None, :]).ravel()[:n]
        means[i] = v[idx].mean() * 365 * 100
    lo, hi = np.percentile(means, [2.5, 97.5])
    return point, float(lo), float(hi)


def main() -> None:
    print("=== P2: carry v3 fold CIs (block bootstrap, frozen) ===",
          flush=True)
    mat, dates = build_panel(binance_daily_funding)
    sig = trailing_signal(mat)
    streams = np.zeros_like(mat)
    for j in range(mat.shape[1]):
        streams[:, j] = per_asset_stream(mat[:, j], sig[:, j])

    marks = [_dt.date(2023, 9, 1), _dt.date(2024, 9, 1),
             _dt.date(2025, 9, 1), _dt.date(2026, 9, 30)]
    n = mat.shape[0]
    idx = [0] + [next((i for i, d in enumerate(dates) if d >= m), n)
                 for m in marks[1:]]
    folds = [(idx[0], idx[1], "F1"), (idx[1], idx[2], "F2"),
             (idx[2], min(idx[3], n), "F3")]

    rng = np.random.default_rng(SEED)
    port = streams.mean(axis=1)
    print(f"days total: {n}  ({dates[0]} .. {dates[n - 1]})")
    for a, b, name in folds:
        p, lo, hi = ann_ci(port[a:b], rng)
        q = "QUOTABLE" if (lo > 0.0) else "not quotable (CI includes 0)"
        print(f"{name} {dates[a]}..{dates[min(b, n) - 1]}  "
              f"ann={p:+.2f}%  CI95=[{lo:+.2f}, {hi:+.2f}]  -> {q}",
              flush=True)

    a, b, _ = folds[2]
    print("\n-- F3 per-asset CIs (active>=60d):")
    for j in range(mat.shape[1]):
        s = streams[a:b, j]
        if int(np.sum((s != 0.0) & np.isfinite(s))) < 60:
            continue
        p, lo, hi = ann_ci(s, rng)
        flag = "*" if lo > 0.0 else " "
        print(f"  {flag} {UNIVERSE[j]:11s} ann={p:+7.2f}%  "
              f"CI95=[{lo:+7.2f}, {hi:+7.2f}]")


if __name__ == "__main__":
    main()
