# -*- coding: utf-8 -*-
"""AVSL-cross 4H -- confirmation run (STATUS 2026-09-21, gates
frozen BEFORE run; see STATUS block "AVSL-CROSS 4H -- CONFIRMATION
PRE-REGISTRATION").

The configuration is IDENTICAL to the screening run
(avsl_cross_tf.py): AVSL(70,345) 4H, normal arm, stop =
max(|close-line|, 2*ATR14), TP {3,5,8}R, HORIZON 500, fee 10bp.
This script only adds the missing full evaluation battery:
portfolio Sharpe_NW (lags = 500 bars), event-basis DD, long/short
split, F3 integrity sub-windows, block-bootstrap CIs, and the
NW-adjusted significance z (n_eff via autocorr up to lag 500).
PRIMARY TP = 5R.  Any gate FAIL closes the family FINALLY.

Run:  uv run python -m experiments.avsl.avsl_cross_confirm
"""

from __future__ import annotations

import numpy as np

from experiments.avsl.avsl_baseline import TPS, WARMUP, _fast_line
from experiments.avsl.avsl_cross_tf import (
    ASSETS,
    K_STOP,
    MSEC_4H,
    TAKER_FEE,
    _read_1h,
    _resample_4h,
    _sim,
)
from ta.src.volatility.atr import atr_ind


TP_PRIMARY = 5.0
NW_LAGS = 500
ANN = 6 * 365            # 4H bars per year
G1_SHARPE = 1.0
G2_DD = 0.25
G5_MIN_ASSETS = 6
G6_Z = 2.0
BOOT_B = 2000
BOOT_BLOCK = 25


def _collect(sym: str) -> dict:
    """Trades for one asset on 4H: per-TP list of
    (net_r, gross_r, fee_r, entry_bucket_g, exit_bucket_g, is_long)."""
    ts, hp, lp, cp, vol = _read_1h(sym)
    ts, hp, lp, cp, vol = _resample_4h(ts, hp, lp, cp, vol)
    line = _fast_line(lp, cp, vol, 2.0)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = ts // MSEC_4H
    g0 = int(b[0])
    trades = []
    for t in cross_idx:
        if t < WARMUP:
            continue
        is_long = bool(up[t - 1])
        risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
        if not np.isfinite(risk) or risk <= 0:
            continue
        stop = cp[t] - risk if is_long else cp[t] + risk
        fee_r = 2 * TAKER_FEE * cp[t] / risk
        per_tp = {}
        for tp_r in TPS:
            pnl = _sim(hp, lp, cp, t, is_long, stop, tp_r)
            if pnl is None:
                continue
            # locate exit bar: first bar reaching TP or stop (replay
            # cheaply from the stored sim outcome? we re-walk below)
            per_tp[tp_r] = pnl
        if not per_tp:
            continue
        # walk once for exit buckets per TP
        n = len(cp)
        exits = {}
        for k in range(t + 1, min(t + 1 + 500, n)):
            if is_long:
                hit_stop = lp[k] <= stop
            else:
                hit_stop = hp[k] >= stop
            for tp_r, pnl in per_tp.items():
                if tp_r in exits:
                    continue
                if hit_stop:
                    exits[tp_r] = k
                else:
                    tp_px = (cp[t] + tp_r * risk if is_long
                             else cp[t] - tp_r * risk)
                    hit_tp = hp[k] >= tp_px if is_long \
                        else lp[k] <= tp_px
                    if hit_tp:
                        exits[tp_r] = k
        for tp_r, pnl in per_tp.items():
            k = exits.get(tp_r, min(t + 500, n - 1))
            trades.append({
                "tp": tp_r,
                "net": pnl - fee_r,
                "gross": pnl,
                "fee": fee_r,
                "e0": int(b[t]) - g0,
                "e1": int(b[k]) - g0,
                "long": is_long,
            })
    return {"trades": trades, "g0": g0, "n_bars": int(b[-1]) - g0 + 1}


def _nw_sharpe(v: np.ndarray, lags: int, ann: int) -> float:
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan")
    rhos = []
    for k in range(1, min(lags, v.size - 10) + 1):
        c = np.corrcoef(v[:-k], v[k:])[0, 1]
        if np.isfinite(c):
            rhos.append(c)
    factor = float(np.sqrt(max(1e-6, 1.0 + 2.0 * float(np.sum(rhos)))))
    return float(v.mean() / v.std() * np.sqrt(ann) / factor)


def _nw_z(v: np.ndarray, lags: int) -> float:
    """NW-adjusted z of the mean with n_eff = n/(1+2*sum rho)."""
    v = v[np.isfinite(v)]
    n = v.size
    if n < 30:
        return float("nan")
    rhos = []
    for k in range(1, min(lags, n - 10) + 1):
        c = np.corrcoef(v[:-k], v[k:])[0, 1]
        if np.isfinite(c):
            rhos.append(c)
    n_eff = n / max(1.0, 1.0 + 2.0 * float(np.sum(rhos)))
    return float(v.mean() / (v.std() / np.sqrt(n_eff)))


def _block_boot_ci(v: np.ndarray, b: int, block: int):
    """Circular block bootstrap 95% CI of the mean."""
    v = np.asarray(v)
    n = v.size
    if n < block:
        return float("nan"), float("nan")
    rng = np.random.default_rng(7)
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

    # flat trade table (per TP)
    flat = {}
    for s, d in data.items():
        for tr in d["trades"]:
            flat.setdefault(tr["tp"], []).append({**tr, "sym": s})

    verdicts = {}

    # ---- G1: portfolio Sharpe_NW on exit-attributed stream
    # gated at TP_PRIMARY only; 3R/8R recorded, not gated (prereg)
    for tp in TPS:
        trs = flat.get(tp, [])
        stream = np.zeros(n_g)
        for tr in trs:
            stream[tr["e1"]] += tr["net"]
        for seg, lo, hi in (("PRIMARY", 0, split),
                            ("F3", split, n_g)):
            sh = _nw_sharpe(stream[lo:hi], NW_LAGS, ANN)
            ok = sh >= G1_SHARPE
            if tp == TP_PRIMARY:
                verdicts["G1", seg, tp] = ok
            print(f"G1 {seg} TP={tp:.0f}R: Sharpe_NW={sh:+.2f} "
                  f"(need >={G1_SHARPE}) -> {'PASS' if ok else 'FAIL'}"
                  f"{'' if tp == TP_PRIMARY else '  [recorded, not gated]'}",
                  flush=True)

    # ---- G2, G3, G6 on PRIMARY TP
    tr5 = [t for t in flat[TP_PRIMARY]]
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        sel = [t for t in tr5 if lo <= t["e0"] < hi]
        net = np.array([t["net"] for t in sel])
        print(f"\n-- {seg} (TP=5R): n={len(sel)} net_EV="
              f"{net.mean():+.3f}R", flush=True)

        if seg == "PRIMARY":
            # G2 event DD, entry-ordered
            order = np.argsort([t["e0"] for t in sel])
            eq = np.cumprod(1.0 + 0.01 * net[order])
            dd = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
            ok = dd <= G2_DD
            verdicts["G2", seg] = ok
            print(f"G2 {seg}: event DD={dd:.1%} (cap {G2_DD:.0%}) "
                  f"-> {'PASS' if ok else 'FAIL'}", flush=True)
            # G3 long/short
            for side, flag in (("LONG", True), ("SHORT", False)):
                sv = net[[t["long"] == flag for t in sel]]
                ok = sv.mean() > 0
                verdicts["G3", side] = ok
                print(f"G3 {seg} {side}: n={len(sv)} "
                      f"net_EV={sv.mean():+.3f}R "
                      f"-> {'PASS' if ok else 'FAIL'}", flush=True)

        # G4: F3 pooled + sub-windows
        if seg == "F3":
            ok_pooled = net.mean() > 0
            thirds = np.array_split(np.arange(lo, hi), 3)
            sub_ok = 0
            for j, idx in enumerate(thirds):
                if idx.size == 0:
                    continue
                a, bnd = int(idx[0]), int(idx[-1]) + 1
                sub = [t for t in tr5 if a <= t["e0"] < bnd]
                m = float(np.mean([t["net"] for t in sub])) if sub \
                    else float("nan")
                pos = m > 0
                sub_ok += pos
                print(f"G4 {seg} win{j + 1}: n={len(sub)} "
                      f"net_EV={m:+.3f}R -> {'+' if pos else '-'}",
                      flush=True)
            ok = ok_pooled and sub_ok >= 2
            verdicts["G4", seg] = ok
            print(f"G4 {seg}: pooled {'+' if ok_pooled else '-'} "
                  f"subwindows {sub_ok}/3 -> "
                  f"{'PASS' if ok else 'FAIL'}", flush=True)

        # G6: NW-adjusted z (headline)
        z = _nw_z(net, NW_LAGS)
        ok = z >= G6_Z
        verdicts["G6", seg] = ok
        print(f"G6 {seg}: NW-z={z:+.2f} (need >={G6_Z}) "
              f"-> {'PASS' if ok else 'FAIL'}", flush=True)

    # ---- G5: block bootstrap
    allnet = np.array([t["net"] for t in flat[TP_PRIMARY]])
    lo_ci, hi_ci = _block_boot_ci(allnet, BOOT_B, BOOT_BLOCK)
    ok_pooled = lo_ci > 0
    verdicts["G5", "pooled"] = ok_pooled
    print(f"\nG5 pooled (PRIMARY+F3, TP=5R): 95% CI "
          f"[{lo_ci:+.3f}, {hi_ci:+.3f}] -> "
          f"{'PASS' if ok_pooled else 'FAIL'}", flush=True)
    n_exc = 0
    for s in ASSETS:
        v = np.array([t["net"] for t in flat[TP_PRIMARY]
                      if t["sym"] == s])
        lo_a, hi_a = _block_boot_ci(v, BOOT_B, BOOT_BLOCK)
        exc = lo_a > 0
        n_exc += exc
        print(f"G5 {s:>5}: n={len(v)} CI [{lo_a:+.3f}, {hi_a:+.3f}] "
              f"{'EXCL 0' if exc else ''}", flush=True)
    ok_assets = n_exc >= G5_MIN_ASSETS
    verdicts["G5", "assets"] = ok_assets
    print(f"G5 assets: {n_exc}/10 CI excludes 0 "
          f"(need >={G5_MIN_ASSETS}) -> "
          f"{'PASS' if ok_assets else 'FAIL'}", flush=True)

    print("\n==== CONFIRM VERDICT ====", flush=True)
    fails = [k for k, v in verdicts.items() if not v]
    if fails:
        print(f"FAIL: {fails}\n-> AVSL-cross entry family CLOSED FINAL",
              flush=True)
    else:
        print("ALL GATES PASS -> signal confirmed, next stage = "
              "live-scale prereg (sizing, venue, monitoring)",
              flush=True)


if __name__ == "__main__":
    main()

