# -*- coding: utf-8 -*-
"""E1 -- ENTRY vs RANDOM vs LAGGED (prereg 68953e0, STATUS
2026-09-22, gates frozen BEFORE this run).

Arm A: AVSL cross entries, frozen geometry (= engine.passed).
Arm B: 100 random-uniform entry draws with per-asset entry count and
       long/short ratio matched to A -> null distribution.
Arm C: AVSL cross delayed 100 bars (geometry at the delayed bar).
Gates: A > mean(B) + 0.05R AND A at >=95th pct of B, PRIMARY and F3.

Run:  uv run python -m experiments.avsl.ablation_entry
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    HORIZON,
    K_STOP,
    MSEC_4H,
    TAKER_FEE,
    TP_PRIMARY,
    WARMUP,
    collect_trades,
    fast_line,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsl.avsl_cross_confirm import _nw_z
from ta.src.volatility.atr import atr_ind


N_DRAWS = 100
DELAY = 100
MARGIN_R = 0.05
PCT_GATE = 95.0
SPLIT_FRAC = 2 / 3


def _env(sym: str, repo) -> dict:
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    line = fast_line(lp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = ts // MSEC_4H
    return {
        "hp": hp, "lp": lp, "cp": cp, "line": line, "atr": atr,
        "up": up, "dn": dn, "cross_idx": cross_idx,
        "b": b, "g0": int(b[0]), "n_bars": int(b[-1]) - int(b[0]) + 1,
    }


def _trade(env: dict, t: int, is_long: bool) -> dict | None:
    """One TP=5R trade with the frozen geometry at entry bar t."""
    hp, lp, cp, line, atr = (env["hp"], env["lp"], env["cp"],
                             env["line"], env["atr"])
    risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    tp_px = entry + TP_PRIMARY * risk if is_long \
        else entry - TP_PRIMARY * risk
    n = len(cp)
    pnl = None
    k_exit = min(t + HORIZON, n - 1)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                pnl = -1.0
                break
            if hp[k] >= tp_px:
                pnl = TP_PRIMARY
                break
        else:
            if hp[k] >= stop:
                pnl = -1.0
                break
            if lp[k] <= tp_px:
                pnl = TP_PRIMARY
                break
    else:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {
        "net": pnl - fee_r,
        "e0": int(env["b"][t]) - env["g0"],
        "long": is_long,
    }


def _segment_stats(trades: list[dict], split: int,
                   which: str) -> tuple:
    sel = [t for t in trades
           if (t["e0"] < split if which == "PRIMARY"
               else t["e0"] >= split)]
    net = np.array([t["net"] for t in sel])
    order = np.argsort([t["e0"] for t in sel])
    z = _nw_z(net[order], NW_LAGS)
    return float(net.mean()), len(sel), float(z)


NW_LAGS = 500


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    print(f"global grid n={n_g}, PRIMARY<{split}<=F3", flush=True)

    # ---- Arm A: frozen entries via the generic path
    arm_a: list[dict] = []
    for s, e in envs.items():
        for t in e["cross_idx"]:
            if t < WARMUP:
                continue
            tr = _trade(e, int(t), bool(e["up"][t - 1]))
            if tr is not None:
                arm_a.append({**tr, "sym": s})
    # sanity: must equal the frozen core collector
    ref = collect_trades("BTC", repo)
    n_ref_btc = len(ref["trades"])
    n_a_btc = sum(1 for t in arm_a if t["sym"] == "BTC")
    print(f"sanity: arm A BTC n={n_a_btc} vs core collector "
          f"n={n_ref_btc} -> "
          f"{'MATCH' if n_a_btc == n_ref_btc else 'MISMATCH'}",
          flush=True)

    # per-asset matching stats from A
    match: dict = {}
    for s in ASSETS:
        tr = [t for t in arm_a if t["sym"] == s]
        n_elig = envs[s]["n_bars"] - WARMUP - 1
        match[s] = {
            "n": len(tr),
            "p_long": (sum(1 for t in tr if t["long"]) / len(tr)
                       if tr else 0.5),
            "n_elig": n_elig,
        }

    # ---- Arm B: null distribution
    b_ev = {"PRIMARY": [], "F3": []}
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
                    draw.append({**tr, "sym": s})
        for seg in ("PRIMARY", "F3"):
            b_ev[seg].append(_segment_stats(draw, split, seg)[0])
        if (seed + 1) % 25 == 0:
            print(f"  draw {seed + 1}/{N_DRAWS}", flush=True)

    # ---- Arm C: delayed entries
    arm_c: list[dict] = []
    for s, e in envs.items():
        for t in e["cross_idx"]:
            te = int(t) + DELAY
            if te >= e["n_bars"] - 1:
                continue
            tr = _trade(e, te, bool(e["up"][t - 1]))
            if tr is not None:
                arm_c.append({**tr, "sym": s})

    # ---- gates
    print(f"\ntrades: A={len(arm_a)}  C={len(arm_c)}  "
          f"B draws={N_DRAWS}", flush=True)
    fails = []
    for seg in ("PRIMARY", "F3"):
        ev_a, n_a, z_a = _segment_stats(arm_a, split, seg)
        ev_c, n_c, z_c = _segment_stats(arm_c, split, seg)
        b = np.array(b_ev[seg])
        mu_b, sd_b = float(b.mean()), float(b.std())
        pct = float((b < ev_a).mean() * 100.0)
        ok_a = ev_a > mu_b + MARGIN_R
        ok_b = pct >= PCT_GATE
        if not ok_a:
            fails.append(("E1a", seg))
        if not ok_b:
            fails.append(("E1b", seg))
        print(f"{seg:>7}: A EV={ev_a:+.3f}R (n={n_a}, z={z_a:+.2f}) | "
              f"B mean={mu_b:+.3f}+-{sd_b:.3f} "
              f"[min {b.min():+.3f}, max {b.max():+.3f}] | "
              f"A pct-in-B={pct:.0f} (need >={PCT_GATE:.0f}) "
              f"{'P' if ok_a and ok_b else 'F'} | "
              f"C(+{DELAY}b) EV={ev_c:+.3f}R (n={n_c}, z={z_c:+.2f})",
              flush=True)

    print("\n==== E1 VERDICT ====", flush=True)
    if fails:
        print(f"FAIL {fails}: entry carries NO information beyond "
              "the 4H RR geometry -> edge is geometry/sizing; "
              "E3/E5/E2/E4 re-interpreted as geometry decomposition",
              flush=True)
    else:
        print("E1a+E1b PASS on both segments: the AVSL cross entry "
              "carries real information beyond RR geometry",
              flush=True)


if __name__ == "__main__":
    main()
