# -*- coding: utf-8 -*-
"""R-SVD-2 feasibility gate -- runner for the prereg frozen in
STATUS (2026-09-24, commit 1a903c7).

Residual cross-sectional mean-reversion: rolling PC1 loadings
(recomputed every 24 bars from a strictly-past 180-bar window),
residual = return minus its PC1 projection, 30-bar cumulative
residual as the rank signal, long bottom-3 / short top-3 equal
weight, held 24 bars, 10bp RT fee per basket.  Orthogonality
read-outs vs the AVSL S1 stream and BTC returns.

Run:  uv run python -m experiments.diagnostics.rsvd2_check
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
)


W = 180
N = 30
K = 3
REB = 24
FEE = 0.002          # 10bp RT per side basket, both legs
PY = 365.0 / 4.0     # rebalances per year (24 x 4H = 4 days)


def _returns(repo) -> tuple[np.ndarray, np.ndarray]:
    data = []
    for sym in ASSETS:
        ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, sym))
        b = np.asarray(ts, dtype=np.int64) // 14_400_000
        lc = np.log(np.asarray(cp[:-1], float))
        bb = b[:-1]
        # sanitize: DOGE/NEAR/XRP lead-in has non-finite closes
        keep = np.isfinite(lc) & np.isfinite(bb)
        data.append((bb[keep], lc[keep]))
    common = data[0][0]
    for b, _lc in data[1:]:
        common = np.intersect1d(common, b)
    R = np.column_stack([
        np.diff(lc[np.searchsorted(b, common)]) for b, lc in data
    ])
    ok = np.isfinite(R).all(axis=1)
    R = R[ok]
    axis = common[1:][ok]
    return axis, R


def _avsl_stream(repo, axis: np.ndarray) -> np.ndarray:
    """AVSL S1 equal-risk 4H accrual stream on the given axis."""
    n = len(axis)
    pnl = np.zeros(n)
    for sym in ASSETS:
        _ts, _hp, _lp, _cp, _vol = resample_4h(*read_1h(repo, sym))
        d = collect_trades(sym, repo)
        g = int(d["g0"])
        lo = int(axis[0])
        sizes = s1_sizes_local(repo, sym)
        for t in d["trades"]:
            e0 = g + int(t["e0"]) - lo
            e1 = g + int(t["e1"]) - lo
            if e0 >= n or e1 <= 0:
                continue
            w = (float(sizes[int(t["e0"])]) * float(t["net"])
                 / (max(int(t["e1"]) - int(t["e0"]), 1) + 1))
            pnl[max(e0, 0):min(e1 + 1, n)] += w
    return pnl


def s1_sizes_local(repo, sym: str) -> np.ndarray:
    from engine.passed.avsl_cross_s1 import s1_sizes
    _ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, sym))
    return s1_sizes(cp[:-1])


def main() -> None:
    repo = repo_root()
    axis, R = _returns(repo)
    n, m = len(R) + 1, len(ASSETS)
    btc = R[:, list(ASSETS).index("BTC")]

    starts = np.arange(W + N, n - 1 - REB, REB)
    gross, net = [], []
    avsl = _avsl_stream(repo, axis)

    beta = np.full(m, 1.0 / np.sqrt(m))
    for t in starts:
        if (t - W) % REB == 0:
            c = np.corrcoef(R[t - W:t].T)
            lam, vec = np.linalg.eigh(c)
            b = vec[:, np.argmax(lam)]
            beta = b if b[np.abs(b).argmax()] > 0 else -b
        pc1 = R[t - N:t + 1] @ beta
        E = R[t - N + 1:t + 1] - np.outer(pc1[1:], beta)
        sig = E.sum(axis=0)
        order = np.argsort(sig)
        longs, shorts = order[:K], order[-K:]
        fwd = R[t + 1:t + 1 + REB]
        spread = fwd[:, longs].mean(axis=1) - fwd[:, shorts].mean(axis=1)
        g = float(spread.sum())
        gross.append(g)
        net.append(g - FEE)

    g_arr, n_arr = np.asarray(gross), np.asarray(net)
    avsl_p = np.array([avsl[t:t + REB].sum() for t in starts])
    btc_p = np.array([btc[t:t + REB].sum() for t in starts])

    def sharpe(v: np.ndarray) -> float:
        return float(v.mean() / v.std(ddof=1) * np.sqrt(PY))

    def maxdd(v: np.ndarray) -> float:
        cum = np.concatenate([[0.0], np.cumsum(v)])
        return float((np.maximum.accumulate(cum) - cum).max())

    print(f"rebalances={len(starts)} (t {starts[0]}..{starts[-1]})")
    print(f"gross Sharpe={sharpe(g_arr):+.2f}  "
          f"net Sharpe={sharpe(n_arr):+.2f}")
    print(f"net EV/rebalance={n_arr.mean():+.5f}  "
          f"total net={n_arr.sum():+.3f}  maxDD={maxdd(n_arr):+.3f}")
    print(f"corr(net, AVSL S1)={np.corrcoef(n_arr, avsl_p)[0, 1]:+.3f}")
    print(f"corr(net, BTC)    ={np.corrcoef(n_arr, btc_p)[0, 1]:+.3f}")
    n_sh, c_avsl = sharpe(n_arr), float(np.corrcoef(n_arr, avsl_p)[0, 1])
    if n_sh >= 1.0 and c_avsl < 0.3:
        verdict = "PASS -> full R-SVD-2 prereg (N arms {10,30,90})"
    elif n_sh < 0.5 or c_avsl > 0.5:
        verdict = "PARKED -> structural fail; SVD family closes"
    else:
        verdict = "NEUTRAL -> post-mortem, no prereg"
    print("GATE:", verdict)


if __name__ == "__main__":
    main()
