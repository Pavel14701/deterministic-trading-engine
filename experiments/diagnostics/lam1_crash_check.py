# -*- coding: utf-8 -*-
"""R-SVD-3 feasibility gate: is rolling PC1 share a crash detector?

Context (STATUS 2026-09-24): DD-quintile check showed AVSL/OB DD is
timing-structural (crypto-beta crash exposure), not sizing -- three
independent fails (E5 vol, S5 regime-skip, R-SVD-1 PC1 cap).  The
only mechanism left that could cut DD is a regime HALT.  Hypothesis:
in crashes all correlations -> 1, so the rolling top-eigenvalue
share lambda1/sum(lambda) spikes; if it is elevated DURING and
BEFORE the large drawdown episodes, a halt rule is prereg-able.

Read-outs (no thresholds tuned here):
  1. lambda1 share during the top-5 drawdown episodes vs its full
     sample distribution (mean/median percentile rank), including
     the value at episode START (a detector must fire before the
     losses, not inside them);
  2. mean per-bucket PnL by lambda1-share decile -- a usable halt
     signal needs high-share buckets to be the losing ones;
  3. simple descriptive counterfactual: share of total PnL earned
     in buckets above each decile of lambda1 share.

Diagnostic ONLY: reads frozen loaders, gates nothing.
Run:  uv run python -m experiments.diagnostics.lam1_crash_check
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)


MS = 14_400_000  # 4H bucket
W = 180          # 30 days of 4H buckets


def _buckets(repo) -> tuple[np.ndarray, np.ndarray]:
    """BTC closed 4H bucket timeline as the common axis."""
    ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, "BTC"))
    b = np.asarray(ts, dtype=np.int64) // MS
    return b[:-1], np.asarray(cp[:-1], dtype=float)


def _closes(repo, sym) -> tuple[np.ndarray, np.ndarray]:
    """(closed bucket starts, RAW closes) -- raw prices are required
    by s1_sizes; log returns are taken downstream."""
    ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, sym))
    b = np.asarray(ts, dtype=np.int64) // MS
    return b[:-1], np.asarray(cp[:-1], dtype=float)


def _dd_episodes(cum: np.ndarray, k: int = 5):
    """Top-k drawdown episodes as (trough, recovery, depth): losses
    accrue over [trough, recovery) -- recovery is the first index
    where cum regains its pre-drawdown peak (or the series end)."""
    run_max = np.maximum.accumulate(cum)
    dd = run_max - cum
    episodes = []
    dd_work = dd.copy()
    for _ in range(k):
        p = int(np.argmax(dd_work))
        if dd_work[p] <= 0:
            break
        t = int(np.argmax(cum[:p + 1]))
        rec = int(np.searchsorted(-cum[p:], -cum[t])) + p
        rec = min(rec + 1, len(cum) - 1)
        episodes.append((t, p, float(dd_work[p])))
        dd_work[t:rec] = 0.0
    return episodes


def main() -> None:
    repo = repo_root()
    axis, _cp = _buckets(repo)
    n = len(axis)

    data = [_closes(repo, s) for s in ASSETS]
    common: np.ndarray = data[0][0]
    for b, _lc in data[1:]:
        common = np.intersect1d(common, b)
    R = np.column_stack([
        np.diff(np.log(lc[np.searchsorted(b, common)])) for b, lc in data
    ])
    m = len(common)  # bucket count on common axis
    off = np.searchsorted(axis, common)

    # rolling PC1 share on the common grid...
    share = np.full(m, np.nan)
    for t in range(W, m):
        c = np.corrcoef(R[t - W:t].T)
        lam = np.linalg.eigvalsh(c)
        share[t] = lam[-1] / lam.sum()
    # ...lifted onto the full bucket axis
    share_ax = np.full(n, np.nan)
    share_ax[off] = share
    print(f"common buckets={m} axis={n} window={W} "
          f"share: mean={np.nanmean(share_ax):.3f} "
          f"p50={np.nanpercentile(share_ax, 50):.3f} "
          f"p90={np.nanpercentile(share_ax, 90):.3f}")

    # per-bucket PnL (same accrual convention as pilot_tracker._equity)
    pnl = np.zeros(n)
    for sym, dat in zip(ASSETS, data):
        d = collect_trades(sym, repo)
        g = int(d["g0"])
        sizes = s1_sizes(dat[1])
        for t in d["trades"]:
            e0 = int(np.searchsorted(axis, g + int(t["e0"])))
            e1 = int(np.searchsorted(axis, g + int(t["e1"])))
            w = (float(sizes[int(t["e0"])]) * float(t["net"])
                 / (max(int(t["e1"]) - int(t["e0"]), 1) + 1))
            pnl[e0:e1 + 1] += w

    cum = np.concatenate([[0.0], np.cumsum(pnl)])
    eps = _dd_episodes(cum)
    valid = share_ax[~np.isnan(share_ax)]

    def pct_rank(x: float) -> float:
        return float(np.searchsorted(valid, x)) / len(valid) * 100

    print("\ntop drawdown episodes: depth (% of top5), "
          "share@start pct-rank, mean share in episode (pct-rank):")
    tot_depth = sum(d for _, _, d in eps) or 1.0
    for t, p, depth in eps:
        s0 = share_ax[min(t, n - 1)]
        s_in = share_ax[t:p]
        s_in = s_in[~np.isnan(s_in)]
        print(f"  {depth:8.1f}R ({100 * depth / tot_depth:4.1f}% of "
              f"top5): start={pct_rank(float(s0)):5.1f}pct "
              f"in-episode={float(np.mean(s_in)):.3f} "
              f"({pct_rank(float(np.mean(s_in))):5.1f}pct)")

    # conditional PnL by lambda1-share decile
    sh = valid
    pp = pnl[~np.isnan(share_ax)]
    dec = np.digitize(sh, np.nanpercentile(sh, np.arange(10, 100, 10)))
    print("\ndecile of lambda1 share | mean PnL/bucket | sum PnL")
    for q in range(10):
        mm = dec == q
        print(f"  D{q + 1} ({np.nanpercentile(sh, q * 10):.2f}-"
              f"{np.nanpercentile(sh, (q + 1) * 10):.2f}): "
              f"{pp[mm].mean():+9.2f} | {pp[mm].sum():+10.1f}")


if __name__ == "__main__":
    main()
