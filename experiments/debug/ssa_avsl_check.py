# -*- coding: utf-8 -*-
"""R-SSA-1 feasibility gate: causal SSA denoising of the AVSL line.

Context (STATUS 2026-09-24): the cross-asset SVD family is parked
(rank-one universe); the per-asset SSA idea -- denoise the AVSL line
to cut false crosses -- was never tested.  This is the cheap gate
BEFORE any prereg.

Design (predeclared, ONE config, no tuning):
  - line_raw  = frozen fast_line(lp, cp, vol)          (import only)
  - line_ssa  = causal SSA reconstruction of line_raw:
      for each t >= W: Hankel matrix of line_raw[t-W..t], SVD,
      keep top-k rank-1 terms, anti-diagonal average, take the LAST
      element -> uses only data <= t (no lookahead).
  - same entry/exit machinery as the frozen collect_trades (cross of
    close vs line, WARMUP, K_STOP*ATR risk, TP=5R/HORIZON sim) with
    the only difference being the line.

Read-outs: crosses, trades, EV/trade, win rate, total R, max DD of
the equal-risk cum-R stream, median lag of SSA crosses vs baseline.
Gate (declared here, before running): SSA arm is interesting only if
EV/trade >= baseline AND max DD < baseline; a large cross reduction
with EV collapse is a fail (latency ate the edge).
Run:  uv run python -m experiments.debug.ssa_avsl_check
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    K_STOP,
    TAKER_FEE,
    WARMUP,
    _sim_5r,
    fast_line,
    read_1h,
    repo_root,
    resample_4h,
)
from ta.src.volatility.atr import atr_ind


SSA_W = 30   # past-bars window (incl. current)
SSA_K = 3    # components kept
HANKEL_L = (SSA_W + 1) // 2


def ssa_last_point(seg: np.ndarray) -> float:
    """Causal SSA: reconstruct seg from top-k components, return the
    final (newest) element of the anti-diagonal-averaged series."""
    n = len(seg)
    lag = n // 2 + n % 2 - 1
    k = n - lag
    x = np.empty((lag + 1, k))
    for i in range(lag + 1):
        x[i] = seg[i:i + k]
    u, s, vt = np.linalg.svd(x, full_matrices=False)
    xk = (u[:, :SSA_K] * s[:SSA_K]) @ vt[:SSA_K]
    # anti-diagonal average, last element only: average of x[:, k-1]
    return float(xk[:, -1].mean())


def ssa_denoise_line(line: np.ndarray) -> np.ndarray:
    out = np.full_like(line, np.nan)
    for t in range(SSA_W, len(line)):
        seg = line[t - SSA_W:t + 1]
        if np.isfinite(seg).all():
            out[t] = ssa_last_point(seg)
        elif t > 0 and np.isfinite(out[t - 1]):
            out[t] = out[t - 1]  # hold through line warm-up gaps
    return out


def simulate(lp: np.ndarray, cp: np.ndarray, hp: np.ndarray,
             line: np.ndarray, atr: np.ndarray) -> dict:
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    nets: list[float] = []
    for t in cross_idx:
        if t < WARMUP:
            continue
        is_long = bool(up[t - 1])
        risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
        if not np.isfinite(risk) or risk <= 0:
            continue
        stop = cp[t] - risk if is_long else cp[t] + risk
        fee_r = 2 * TAKER_FEE * cp[t] / risk
        pnl = _sim_5r(hp, lp, cp, int(t), is_long, float(stop))
        if pnl is None:
            continue
        nets.append(pnl - fee_r)
    nets_a = np.asarray(nets)
    cum = np.concatenate([[0.0], np.cumsum(nets_a)])
    max_dd = float((np.maximum.accumulate(cum) - cum).max()) \
        if len(nets_a) else 0.0
    return {
        "n_cross": len(cross_idx),
        "n_trades": len(nets_a),
        "n_win": int((nets_a > 0).sum()),
        "ev": float(nets_a.mean()) if len(nets_a) else 0.0,
        "win": float((nets_a > 0).mean()) if len(nets_a) else 0.0,
        "total_r": float(nets_a.sum()),
        "max_dd_r": max_dd,
        "cross_t": cross_idx,
    }


def main() -> None:
    repo = repo_root()
    from engine.passed.avsl_cross_s1 import ASSETS
    agg = {"base": [], "ssa": []}
    lags: list[float] = []
    for sym in ASSETS:
        _ts, hp, lp, cp, vol = resample_4h(*read_1h(repo, sym))
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        line = fast_line(lp, cp, vol)
        base = simulate(lp, cp, hp, line, atr)
        ssa = simulate(lp, cp, hp, ssa_denoise_line(line), atr)
        # median lag of SSA crosses relative to nearest baseline cross
        bc = base["cross_t"]
        for t in ssa["cross_t"]:
            if t < WARMUP or len(bc) == 0:
                continue
            lags.append(float(np.min(np.abs(bc - t))))
        agg["base"].append(base)
        agg["ssa"].append(ssa)
        print(f"{sym}: base x={base['n_cross']} tr={base['n_trades']} "
              f"EV={base['ev']:+.3f} win={base['win']:.2f} "
              f"DD={base['max_dd_r']:.1f}R | "
              f"ssa x={ssa['n_cross']} tr={ssa['n_trades']} "
              f"EV={ssa['ev']:+.3f} win={ssa['win']:.2f} "
              f"DD={ssa['max_dd_r']:.1f}R")

    def tot(key: str, field: str) -> float:
        return float(sum(a[field] for a in agg[key]))

    bt = sum(a["n_trades"] for a in agg["base"])
    st = sum(a["n_trades"] for a in agg["ssa"])
    bev = tot("base", "total_r") / max(bt, 1)
    sev = tot("ssa", "total_r") / max(st, 1)
    print(f"\nTOTAL base: trades={bt} EV={bev:+.3f} "
          f"win={tot('base', 'n_win') / max(bt, 1):.2f} "
          f"totalR={tot('base', 'total_r'):+.0f} "
          f"sumDD={sum(a['max_dd_r'] for a in agg['base']):.0f}R")
    print(f"TOTAL ssa : trades={st} EV={sev:+.3f} "
          f"totalR={tot('ssa', 'total_r'):+.0f} "
          f"sumDD={sum(a['max_dd_r'] for a in agg['ssa']):.0f}R")
    print(f"cross reduction: {100 * (1 - st / max(bt, 1)):.0f}% | "
          f"median lag of ssa crosses: {np.median(lags):.0f} bars "
          f"({np.median(lags) * 4:.0f}h)")
    verdict = ("INTERESTING" if sev >= bev else "FAIL: EV collapsed")
    print("GATE:", verdict)


if __name__ == "__main__":
    main()
