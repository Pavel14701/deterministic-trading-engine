# -*- coding: utf-8 -*-
"""Risk-overlay track -- S1..S4 sizing on the CLOSED AVSL-cross 4H
signal (prereg frozen in STATUS 2026-09-22, commit b6005ca, BEFORE
this run).

Signal source: avsl_cross_confirm._collect -- byte-identical trade
set to the confirmed runs (AVSL(70,345) 4H, stop =
max(|close-line|, 2*ATR14), TP 5R PRIMARY, HORIZON 500, fee 10bp).
Only position sizing differs:

S1 vol-target:   size = clip(0.20 / rv100, 0.25, 2.0)
S2 regime:       x1 / x0.5 / x0.25 by ATR14 pct (500-bar window)
S3 conc. cap:    skip entry if >=5 open or exposure >= 3x base
S4               = S1 x S2 with S3 caps

Gates per config (frozen): G1' Sharpe_NW >= 1.0 both segs; G2'
DD <= 25% both segs; G3' net EV >= 0.10R both; G4' >= 7/10 assets
positive both; G5' block bootstrap (block 500, B 1000) CI of mean
sized bar R excludes 0 both.  Verdict: risk-first selection
S3 > S4 > S1 > S2 among full passers.

Run:  uv run python -m experiments.avsl.risk_overlay
"""

from __future__ import annotations

import numpy as np

from experiments.avsl.avsl_cross_confirm import (
    ANN,
    NW_LAGS,
    _collect,
    _nw_sharpe,
)
from experiments.avsl.avsl_cross_confirm2 import (
    HORIZON,
    RISK_PCT,
    _block_boot_mean_ci,
)
from experiments.avsl.avsl_cross_tf import ASSETS, _read_1h, _resample_4h
from ta.src.volatility.atr import atr_ind


TP_PRIMARY = 5.0
VOL_WIN = 100
VOL_TARGET = 0.20
SIZE_MIN, SIZE_MAX = 0.25, 2.0
REG_WIN = 500
MAX_OPEN = 5
MAX_EXPO = 3.0
G1_SHARPE = 1.0
G2_DD = 0.25
G3_EV = 0.10
G4_ASSETS = 7
BOOT_B = 1000

CONFIGS = ("S1", "S2", "S3", "S4")
PICK_ORDER = {"S3": 0, "S4": 1, "S1": 2, "S2": 3}


def _sizing_inputs(sym: str) -> tuple[np.ndarray, np.ndarray]:
    """Per 4H bar: realized vol (ann, 100-bar std of log rets) and
    ATR14 percentile within the last 500 bars.  Index = bucket idx
    (same contiguity assumption as the confirm exit-walk)."""
    ts, hp, lp, cp, vol = _read_1h(sym)
    ts, hp, lp, cp, vol = _resample_4h(ts, hp, lp, cp, vol)
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    rv = np.full(n, np.nan)
    for i in range(1, n):
        rv[i] = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    pct = np.full(n, np.nan)
    for i in range(n):
        w = atr[max(0, i - REG_WIN):i + 1]
        w = w[np.isfinite(w)]
        if w.size and np.isfinite(atr[i]):
            pct[i] = float((w <= atr[i]).mean() * 100.0)
    return rv, pct


def _base_trades() -> tuple[list[dict], int, int, int]:
    """TP=5R trade table (identical to confirm), global grid, split."""
    data = {s: _collect(s) for s in ASSETS}
    g0 = min(d["g0"] for d in data.values())
    n_g = max(d["n_bars"] + d["g0"] for d in data.values()) - g0
    split = int(n_g * 2 / 3)
    trs = []
    for s, d in data.items():
        for t in d["trades"]:
            if t["tp"] == TP_PRIMARY:
                trs.append({**t, "sym": s})
    trs.sort(key=lambda t: (t["e0"], t["sym"]))
    return trs, g0, n_g, split


def _apply_config(name: str, trs: list[dict],
                  aux: dict) -> list[dict]:
    """Attach 'size' or drop the trade (S3/S4 caps).  Entries processed
    in (e0, sym) order; a trade is open at e0 while its e1 >= e0."""
    out: list[dict] = []
    open_tr: list[dict] = []
    for t in trs:
        rv, pct = aux[t["sym"]]
        e0 = t["e0"]
        open_tr = [o for o in open_tr if o["e1"] >= e0]
        r = rv[e0]
        s1 = float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX)) \
            if np.isfinite(r) and r > 0 else 1.0
        p = pct[e0]
        s2 = 1.0 if not np.isfinite(p) or p <= 80 else \
            0.5 if p <= 90 else 0.25
        if name == "S1":
            size, skip = s1, False
        elif name == "S2":
            size, skip = s2, False
        elif name == "S3":
            size = 1.0
            expo = sum(o["size"] for o in open_tr)
            skip = len(open_tr) >= MAX_OPEN or expo >= MAX_EXPO
        else:  # S4
            size = s1 * s2
            expo = sum(o["size"] for o in open_tr)
            skip = len(open_tr) >= MAX_OPEN or expo >= MAX_EXPO
        t2 = {**t, "size": 0.0 if skip else size, "skipped": skip}
        if not skip:
            open_tr.append(t2)
        out.append(t2)
    return out


def _gates(name: str, kept: list[dict], n_sized: int, n_g: int,
           split: int, fails: list) -> None:
    stream = np.zeros(n_g + 1)
    for t in kept:
        hold = max(t["e1"] - t["e0"], 1)
        w = t["size"] * t["net"] / (hold + 1)
        stream[t["e0"]:t["e1"] + 1] += w
    stream = stream[:n_g]
    sizes = np.array([t["size"] for t in kept])
    print(f"  sizing: kept {len(kept)}/{n_sized}, "
          f"size mean {sizes.mean():.2f} / med "
          f"{np.median(sizes):.2f} / max {sizes.max():.2f}",
          flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        sh = _nw_sharpe(stream[lo:hi], NW_LAGS, ANN)
        ok1 = sh >= G1_SHARPE
        if not ok1:
            fails.append((name, "G1p", seg))
        eq = np.cumprod(1.0 + RISK_PCT * stream[lo:hi])
        dd = float(np.max(1.0 - eq / np.maximum.accumulate(eq)))
        ok2 = dd <= G2_DD
        if not ok2:
            fails.append((name, "G2p", seg))
        seg_tr = [t for t in kept if lo <= t["e0"] < hi]
        ev = float(np.mean([t["net"] for t in seg_tr])) if seg_tr \
            else float("nan")
        ok3 = ev >= G3_EV
        if not ok3:
            fails.append((name, "G3p", seg))
        pos = 0
        for s in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == s]
            if v and float(np.mean(v)) > 0:
                pos += 1
        ok4 = pos >= G4_ASSETS
        if not ok4:
            fails.append((name, "G4p", seg))
        lo_ci, hi_ci = _block_boot_mean_ci(
            stream[lo:hi], BOOT_B, HORIZON
        )
        ok5 = lo_ci > 0
        if not ok5:
            fails.append((name, "G5p", seg))
        print(f"  {seg:>7} (n={len(seg_tr)}): "
              f"G1' Sh={sh:+.2f}{'P' if ok1 else 'F'} | "
              f"G2' DD={dd:.0%}{'P' if ok2 else 'F'} | "
              f"G3' EV={ev:+.2f}R{'P' if ok3 else 'F'} | "
              f"G4' {pos}/10{'P' if ok4 else 'F'} | "
              f"G5' [{lo_ci:+.5f},{hi_ci:+.5f}]"
              f"{'P' if ok5 else 'F'}", flush=True)


def main() -> None:
    trs, _g0, n_g, split = _base_trades()
    print(f"global 4H grid n={n_g}, PRIMARY<{split}<=F3, "
          f"TP=5R trades {len(trs)}", flush=True)
    aux = {s: _sizing_inputs(s) for s in ASSETS}

    summary: dict = {}
    for name in CONFIGS:
        sized = _apply_config(name, trs, aux)
        kept = [t for t in sized if not t["skipped"]]
        print(f"\n=== {name}: skipped {len(sized) - len(kept)} "
              f"entries, kept {len(kept)} ===", flush=True)
        fails: list = []
        _gates(name, kept, len(sized), n_g, split, fails)
        summary[name] = (not fails, len(sized) - len(kept), len(kept))

    print("\n==== RISK-OVERLAY VERDICT (risk-first) ====", flush=True)
    passers = [c for c in CONFIGS if summary[c][0]]
    for c in CONFIGS:
        print(f"  {c}: {'PASS' if summary[c][0] else 'FAIL'} "
              f"(skipped {summary[c][1]}, kept {summary[c][2]})",
              flush=True)
    if not passers:
        print("0/4 configs pass -> risk profile is FUNDAMENTAL "
              "(correlation, not vol); RISK-OVERLAY TRACK CLOSED",
              flush=True)
    else:
        pick = min(passers, key=lambda c: PICK_ORDER[c])
        print(f"passers: {passers} -> selected (most conservative): "
              f"{pick}", flush=True)


if __name__ == "__main__":
    main()
