# -*- coding: utf-8 -*-
"""E5 -- regime slices, DESCRIPTIVE (prereg 68953e0 + amendment
BEFORE run, STATUS 2026-09-22).  No gates.

Arm A (frozen AVSL-cross 5R geometry) trades sliced by:
  - ATR14 percentile at entry (top-20 vs bottom-20, 500-bar window)
  - SMA50 slope trend state (up / down / range, 0.1%-per-day deadband)
  - entry year bucket (<=2020 / 2021 / 2022 / 2023-24 / >=2025)
Each slice also reports the matched random-geometry null (E1
procedure, 100 draws, seeds 0..99) and entry-lift = A - null.

Run:  uv run python -m experiments.avsl.ablation_regime
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    WARMUP,
    repo_root,
)
from experiments.avsl.ablation_entry import (
    N_DRAWS,
    SPLIT_FRAC,
    _env,
    _trade,
)
from experiments.avsl.avsl_cross_confirm import _nw_z


REG_WIN = 500
SLOPE_LAG = 6              # 1 day on 4H
DEADBAND = 0.001           # 0.1% of price per day
YEARS = ("<2021", "2021", "2022", "2023-24", ">=2025")


def _features(env: dict) -> dict:
    """Per-bar: ATR percentile (500w) and SMA50 trend state."""
    cp, atr = env["cp"], env["atr"]
    n = len(cp)
    pct = np.full(n, np.nan)
    for i in range(n):
        w = atr[max(0, i - REG_WIN):i + 1]
        w = w[np.isfinite(w)]
        if w.size and np.isfinite(atr[i]):
            pct[i] = float((w <= atr[i]).mean() * 100.0)
    sma = np.full(n, np.nan)
    for i in range(SLOPE_LAG, n):
        sma[i] = cp[max(0, i - 49):i + 1].mean()
    state = np.full(n, "range", dtype=object)
    for i in range(SLOPE_LAG, n):
        slope = sma[i] - sma[i - SLOPE_LAG]
        if slope > DEADBAND * cp[i]:
            state[i] = "up"
        elif slope < -DEADBAND * cp[i]:
            state[i] = "down"
    return {"pct": pct, "state": state}


def _year_bucket(env: dict, t: int) -> str:
    year = datetime.fromtimestamp(
        int(env["b"][t]) * MSEC_4H / 1000, tz=timezone.utc,
    ).year
    if year <= 2020:
        return YEARS[0]
    if year == 2021:
        return YEARS[1]
    if year == 2022:
        return YEARS[2]
    if year <= 2024:
        return YEARS[3]
    return YEARS[4]


SLICES = ("atr_hi", "atr_lo", "up", "down", "range", *YEARS)
NW_LAGS = 500


def _slice_of(env: dict, t: int) -> dict:
    pct = env["pct"][t]
    st = env["state"][t]
    return {
        "atr_hi": bool(np.isfinite(pct) and pct > 80),
        "atr_lo": bool(np.isfinite(pct) and pct < 20),
        "up": st == "up",
        "down": st == "down",
        "range": st == "range",
        _year_bucket(env, t): True,
    }


def _slice_stats(trades: list[dict], split: int,
                 which: str) -> dict:
    """Per-slice n / mean net / NW-z (z over e0-ordered stream)."""
    out: dict = {}
    for sl in SLICES:
        sel = [t for t in trades
               if ((t["e0"] < split) == (which == "PRIMARY"))
               and t["slices"].get(sl, False)]
        if not sel:
            out[sl] = None
            continue
        net = np.array([t["net"] for t in sel])
        order = np.argsort([t["e0"] for t in sel])
        out[sl] = (float(net.mean()), len(sel),
                   float(_nw_z(net[order], NW_LAGS)))
    return out


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    for s in ASSETS:
        envs[s].update(_features(envs[s]))
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)

    # arm A trades with slice flags
    arm_a: list[dict] = []
    for s in ASSETS:
        e = envs[s]
        for t in e["cross_idx"]:
            if t < WARMUP:
                continue
            tr = _trade(e, int(t), bool(e["up"][t - 1]))
            if tr is None:
                continue
            arm_a.append({**tr, "sym": s,
                          "slices": _slice_of(e, int(t))})
    print(f"arm A trades: {len(arm_a)}", flush=True)

    # matched random draws (E1 procedure), sliced per draw
    match = {}
    for s in ASSETS:
        tot = sum(1 for t in arm_a if t["sym"] == s)
        n_long = sum(1 for t in arm_a
                     if t["sym"] == s and t["long"])
        match[s] = {"n": tot,
                    "p_long": n_long / tot if tot else 0.5}
    null_sum: dict = {sl: {"PRIMARY": [], "F3": []} for sl in SLICES}
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        draw: list[dict] = []
        for s in ASSETS:
            m = match[s]
            if m["n"] == 0:
                continue
            bars = rng.choice(
                np.arange(WARMUP, envs[s]["n_bars"] - 1),
                size=m["n"], replace=False,
            )
            for t in bars:
                is_long = bool(rng.random() < m["p_long"])
                tr = _trade(envs[s], int(t), is_long)
                if tr is not None:
                    draw.append({**tr,
                                 "slices": _slice_of(envs[s],
                                                     int(t))})
        for seg in ("PRIMARY", "F3"):
            want_primary = seg == "PRIMARY"
            for sl in SLICES:
                sel = [t["net"] for t in draw
                       if (t["e0"] < split) == want_primary
                       and t["slices"].get(sl, False)]
                if sel:
                    null_sum[sl][seg].append(float(np.mean(sel)))
        if (seed + 1) % 50 == 0:
            print(f"  draw {seed + 1}/{N_DRAWS}", flush=True)

    # ---- read-out
    for seg in ("PRIMARY", "F3"):
        print(f"\n-- {seg} --", flush=True)
        print(f"{'slice':>8} {'n':>5} {'A EV':>8} {'z':>6} "
              f"{'null':>14} {'lift':>7}", flush=True)
        for sl in SLICES:
            st = _slice_stats(arm_a, split, seg)[sl]
            ns = null_sum[sl][seg]
            if st is None or not ns:
                print(f"{sl:>8} {'-':>5}", flush=True)
                continue
            mu, sd = float(np.mean(ns)), float(np.std(ns))
            print(f"{sl:>8} {st[1]:>5} {st[0]:>+8.3f} {st[2]:>+6.2f} "
                  f"{mu:>+7.3f}+-{sd:.3f} {st[0] - mu:>+7.3f}",
                  flush=True)

    print("\n==== E5 READ-OUT (descriptive, no gates) ====",
          flush=True)
    print("interpretation vocabulary: universal / vol-concentrated /"
          " trend-concentrated / beta-like", flush=True)


if __name__ == "__main__":
    main()
