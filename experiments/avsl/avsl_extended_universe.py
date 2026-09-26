# -*- coding: utf-8 -*-
"""AVSL-extended: frozen AVSL-cross S1 on the 29-asset cached
universe, 2024-2026 common window (prereg frozen in STATUS
2026-09-24, BEFORE this run).

Frozen signal/sizing imported read-only from the engine module.
TRUE-grid placement; only trades entering inside the common
window; gates G1'-G5' identical thresholds (G4' >= 21/29);
PF-G4 12m negative-window count reported, NOT gated.

Run:  python -m experiments.avsl.avsl_extended_universe
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,
    BOOT_B,
    HORIZON,
    RISK_PCT,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.risk_overlay_mirror import (
    NW_LAGS,
    _block_boot_mean_ci,
    _nw_sharpe,
)

UNIVERSE_29 = (
    "AAVE", "ADA", "APT", "ARB", "ATOM", "AVAX", "BCH", "BNB",
    "BTC", "DOGE", "DOT", "ETC", "ETH", "FIL", "HBAR", "INJ",
    "LINK", "LTC", "NEAR", "OP", "SEI", "SOL", "SUI", "TIA",
    "TON", "TRX", "WIF", "XLM", "XRP",
)
G4_MIN = 21
W12M = 2190


def _raw_sharpe(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan")
    return float(v.mean() / v.std() * np.sqrt(ANN))


def _dd(v: np.ndarray) -> float:
    eq = np.cumprod(1.0 + RISK_PCT * v)
    return float(np.max(1.0 - eq / np.maximum.accumulate(eq)))


def main() -> None:
    repo = repo_root()
    data = {s: collect_trades(s, repo) for s in UNIVERSE_29}
    g0c = max(d["g0"] for d in data.values())
    n_g = min(d["g0"] + d["n_bars"] for d in data.values()) - g0c
    split = int(n_g * 2 / 3)
    print(f"AVSL-EXTENDED one-shot: {len(data)} assets, common grid "
          f"n={n_g} from "
          f"{dt.datetime.utcfromtimestamp(g0c * 14_400_000 / 1000).date()}, "
          f"PRIMARY<{split}<=F3", flush=True)

    stream = np.zeros(n_g)
    seg_tr: dict[str, list] = {"PRIMARY": [], "F3": []}
    n_all = 0
    for s, d in data.items():
        _ts, hp, lp, cp, vol = read_1h(repo, s)
        _ts, hp, lp, cp, vol = resample_4h(_ts, hp, lp, cp, vol)
        sizes = s1_sizes(cp)
        for t in d["trades"]:
            e0 = d["g0"] + t["e0"] - g0c
            if e0 < 0:
                continue  # entry before the common window
            e1 = min(d["g0"] + t["e1"] - g0c, n_g - 1)
            hold = max(t["e1"] - t["e0"], 1)
            seg = "PRIMARY" if e0 < split else "F3"
            seg_tr[seg].append({**t, "sym": s})
            w = sizes[t["e0"]] * t["net"] / (hold + 1)
            stream[e0:e1 + 1] += w
            n_all += 1
    print(f"trades inside window: {n_all} "
          f"(PRIMARY {len(seg_tr['PRIMARY'])}, F3 {len(seg_tr['F3'])})",
          flush=True)

    fails: list[str] = []
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        v = stream[lo:hi]
        sh_nw = _nw_sharpe(v, NW_LAGS, ANN)
        sh_raw = _raw_sharpe(v)
        ok1 = sh_nw >= 1.0
        if not ok1:
            fails.append(f"G1p:{seg}")
        dd = _dd(v)
        ok2 = dd <= 0.25
        if not ok2:
            fails.append(f"G2p:{seg}")
        trs = seg_tr[seg]
        ev = float(np.mean([t["net"] for t in trs])) if trs else float("nan")
        ok3 = ev >= 0.10
        if not ok3:
            fails.append(f"G3p:{seg}")
        pos = 0
        for s in UNIVERSE_29:
            vv = [t["net"] for t in trs if t["sym"] == s]
            if vv and float(np.mean(vv)) > 0:
                pos += 1
        ok4 = pos >= G4_MIN
        if not ok4:
            fails.append(f"G4p:{seg}")
        lo_ci, hi_ci = _block_boot_mean_ci(v, BOOT_B, HORIZON)
        ok5 = lo_ci > 0
        if not ok5:
            fails.append(f"G5p:{seg}")
        print(f"  {seg:>7} (n={len(trs)}): G1' Sh_NW={sh_nw:+.2f} "
              f"(raw {sh_raw:+.2f}){'P' if ok1 else 'F'} | "
              f"G2' DD={dd:.1%}{'P' if ok2 else 'F'} | "
              f"G3' EV={ev:+.3f}R{'P' if ok3 else 'F'} | "
              f"G4' {pos}/29{'P' if ok4 else 'F'} | "
              f"G5' [{lo_ci:+.5f},{hi_ci:+.5f}]"
              f"{'P' if ok5 else 'F'}", flush=True)

    roll = np.convolve(stream, np.ones(W12M), mode="valid")
    n_neg = int(np.sum(roll <= 0))
    print(f"  PF-G4 read-out (NOT gated): {n_neg}/{len(roll)} "
          f"trailing 12m windows negative, worst {roll.min():+.1f}R",
          flush=True)

    print("\n==== AVSL-EXTENDED VERDICT ====", flush=True)
    if fails:
        print(f"FAIL: {', '.join(fails)} -> extended-universe "
              f"test CLOSED", flush=True)
    else:
        print("PASS (G1'-G5' both segments) -> signal carries to "
              "the 29-asset universe on the 2024-2026 window",
              flush=True)


if __name__ == "__main__":
    main()
