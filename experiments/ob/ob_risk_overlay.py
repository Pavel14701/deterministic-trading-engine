# -*- coding: utf-8 -*-
"""OB confirmation + sizing -- prereg 83c2b3f (STATUS, 2026-09-23).

Signal FROZEN at the E8b frame: R2 preset (post-fix), retest-bar
entry, stop 3xATR14, TP grid {3, 5, 8}R with PRIMARY = 5R,
horizon 500, fee 10bp RT, WARMUP 400, 10 assets, split 2/3.

Arms (sizing only): A raw 1x; S1 vol-target clip(0.20/rv100,
0.25, 2.0); S3 concurrency cap (>=5 open or >=3x base -> skip);
S5 = S1 x 0.5 when ATR14 pct(500) > 80.  Exits for all arms at
PRIMARY 5R.

Gates G1'-G5' per arm, both segments (thresholds = AVSL overlay):
Sharpe_NW >= 1.0; event DD <= 25%; net EV >= 0.10R; >= 7/10 assets
positive; block bootstrap CI (B=1000, block 500) excludes 0.
KILL: any arm-A gate FAIL -> OB CLOSED FINAL (no sizing rescue).
Risk-first pick among full passers: S3 > S5 > S1 > A.

GRID ALIGNMENT (declared): this runner places every trade on the
TRUE global grid (absolute 4H bucket minus the earliest asset
bucket).  The E8/E8b runner (retest_entry.py) and the frozen
module's evaluate() used asset-LOCAL indices for the stream -- for
late-listed assets this shifts trades by up to ~2246 buckets; the
legacy convention is reported here as a sensitivity read-out
(stream metrics only; per-trade EV and the matched null are
unaffected by the convention).

Run:  uv run python -m experiments.ob.ob_risk_overlay
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SPLIT_FRAC,
    block_bootstrap_ci,
    collect_trades,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.retest_entry import (
    HORIZON,
    N_DRAWS,
    STOP_K,
    TAKER_FEE,
    TP_PRIMARY,
    WARMUP,
    _env,
    _ob_events,
)
from ta.src.volatility.atr import atr_ind


TP_GRID = (3.0, 5.0, 8.0)
VOL_WIN = 100
VOL_TARGET = 0.20
SIZE_MIN, SIZE_MAX = 0.25, 2.0
REG_WIN = 500
REG_THR = 80.0
REG_CUT = 0.5
MAX_OPEN = 5
MAX_EXPO = 3.0
G1_SHARPE = 1.0
G2_DD = 0.25
G3_EV = 0.10
G4_ASSETS = 7
BOOT_B = 1000
ARMS = ("A", "S1", "S3", "S5")
PICK_ORDER = {"S3": 0, "S5": 1, "S1": 2, "A": 3}


def _trade_tp(env: dict, t: int, is_long: bool,
              tp_r: float) -> dict | None:
    """E8b frame at an arbitrary TP: stop 3xATR, horizon 500,
    stop-first.  Returns gross/net (net after fee) in R."""
    hp, lp, cp, atr = env["hp"], env["lp"], env["cp"], env["atr"]
    risk = STOP_K * atr[t]
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    tp_px = entry + tp_r * risk if is_long else entry - tp_r * risk
    n = len(cp)
    k_exit = min(t + HORIZON, n - 1)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                pnl = -1.0
                break
            if hp[k] >= tp_px:
                pnl = tp_r
                break
        else:
            if hp[k] >= stop:
                pnl = -1.0
                break
            if lp[k] <= tp_px:
                pnl = tp_r
                break
    else:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {"gross": pnl, "net": pnl - fee_r, "fee": fee_r,
            "e0": int(env["b"][t]) - env["g0"],
            "e1": int(env["b"][k_exit]) - env["g0"],
            "long": is_long}


def base_trades(envs: dict) -> list[dict]:
    """All OB entries, simulated on the TP grid; e0/e1 shifted to
    the TRUE global grid (absolute bucket - min g0)."""
    g0_min = min(e["g0"] for e in envs.values())
    trades: list[dict] = []
    for s in ASSETS:
        env = envs[s]
        idx, side = _ob_events(env)
        for t, is_long in zip(idx, side, strict=True):
            if t < WARMUP:
                continue
            per_tp: dict[float, dict | None] = {}
            for tp in TP_GRID:
                per_tp[tp] = _trade_tp(env, int(t), bool(is_long), tp)
            prim = per_tp[TP_PRIMARY]
            if prim is None:
                continue
            trades.append({
                "sym": s,
                "e0": env["g0"] + prim["e0"] - g0_min,
                "e1": env["g0"] + prim["e1"] - g0_min,
                "long": bool(is_long),
                "net": prim["net"], "gross": prim["gross"],
                "fee": prim["fee"],
                "by_tp": {tp: (d["net"] if d else None)
                          for tp, d in per_tp.items()},
            })
    trades.sort(key=lambda t: (t["e0"], t["sym"]))
    return trades


ANN = 6 * 365


def sizing_aux(repo) -> dict:
    """Per-asset (rv100 annualized, ATR14 pct in 500-bar window,
    cp) indexed by asset-local 4H bar."""
    aux: dict = {}
    for sym in ASSETS:
        _ts, hp, lp, cp, _vol = resample_4h(*read_1h(repo, sym))
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
        aux[sym] = (rv, pct, cp)
    return aux


def decorate(trades: list[dict], envs: dict, aux: dict,
             g0_min: int) -> None:
    """Attach per-entry local bar index, S1 size and regime pct."""
    for t in trades:
        rv, pct, _cp = aux[t["sym"]]
        i0 = t["e0"] - (envs[t["sym"]]["g0"] - g0_min)
        r, p = rv[i0], pct[i0]
        t["i0"] = i0
        t["s1"] = (float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX))
                   if np.isfinite(r) and r > 0 else 1.0)
        t["pct"] = float(p) if np.isfinite(p) else float("nan")


def apply_arm(name: str, trades: list[dict]) -> tuple[list[dict], int]:
    """Attach 'size' (or skip).  Concurrency on PRIMARY (5R) exits;
    entries processed in (e0, sym) order; open while e1 >= e0."""
    out: list[dict] = []
    open_tr: list[dict] = []
    n_skip = 0
    for t in trades:
        open_tr = [o for o in open_tr if o["e1"] >= t["e0"]]
        if name == "A":
            size, skip = 1.0, False
        elif name == "S1":
            size, skip = t["s1"], False
        elif name == "S5":
            hi = np.isfinite(t["pct"]) and t["pct"] > REG_THR
            size, skip = t["s1"] * (REG_CUT if hi else 1.0), False
        else:  # S3
            size = 1.0
            expo = sum(o["size"] for o in open_tr)
            skip = len(open_tr) >= MAX_OPEN or expo >= MAX_EXPO
        t2 = {**t, "size": 0.0 if skip else size, "skipped": skip}
        n_skip += skip
        if not skip:
            open_tr.append(t2)
        out.append(t2)
    return out, n_skip


def stream_of(kept: list[dict], n_g: int, legacy: bool = False,
              envs: dict | None = None) -> np.ndarray:
    """Per-bar accrual.  legacy=True reproduces the retest_entry
    convention (asset-local placement) for sensitivity only."""
    s = np.zeros(n_g + 1)
    for t in kept:
        if t["skipped"]:
            continue
        e0, e1 = t["e0"], t["e1"]
        if legacy:
            off = envs[t["sym"]]["g0"] - min(e["g0"]
                                             for e in envs.values())
            e0, e1 = e0 - off, e1 - off
        hold = max(e1 - e0, 1)
        s[e0:e1 + 1] += t["size"] * t["net"] / (hold + 1)
    return s[:n_g]


def gates(name: str, kept: list[dict], n_g: int, split: int,
          fails: list) -> dict:
    stream = stream_of(kept, n_g)
    sizes = np.array([t["size"] for t in kept if not t["skipped"]])
    print(f"  sizing: kept {int(np.sum(sizes > 0))}/{len(kept)}, "
          f"size mean {sizes.mean():.2f} / med "
          f"{float(np.median(sizes)):.2f}", flush=True)
    res: dict = {}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_stream = stream[lo:hi]
        sh = nw_sharpe(seg_stream)
        dd = portfolio_dd(seg_stream)
        seg_tr = [t for t in kept
                  if not t["skipped"] and lo <= t["e0"] < hi]
        ev = (float(np.mean([t["net"] for t in seg_tr]))
              if seg_tr else float("nan"))
        pos = 0
        for sym in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        lo_ci, hi_ci = block_bootstrap_ci(seg_stream, BOOT_B, HORIZON)
        checks = {
            "G1p": sh >= G1_SHARPE, "G2p": dd <= G2_DD,
            "G3p": ev >= G3_EV, "G4p": pos >= G4_ASSETS,
            "G5p": lo_ci > 0,
        }
        fails.extend((name, k, seg) for k, ok in checks.items()
                     if not ok)
        res[seg] = {"sh": sh, "dd": dd, "ev": ev, "pos": pos,
                    "ci": (lo_ci, hi_ci), "n": len(seg_tr)}
        print(f"  {seg:>7} (n={len(seg_tr)}): "
              f"G1' Sh={sh:+.2f}{'P' if checks['G1p'] else 'F'} | "
              f"G2' DD={dd:.0%}{'P' if checks['G2p'] else 'F'} | "
              f"G3' EV={ev:+.2f}R{'P' if checks['G3p'] else 'F'} | "
              f"G4' {pos}/10{'P' if checks['G4p'] else 'F'} | "
              f"G5' [{lo_ci:+.5f},{hi_ci:+.5f}]"
              f"{'P' if checks['G5p'] else 'F'}", flush=True)
    return res


TRADES: list = []


def descriptive_null(envs: dict, g0_min: int, split: int) -> None:
    """Matched random-geometry null (arm A, TP 5R) -- descriptive."""
    match = {}
    for s in ASSETS:
        tot = sum(1 for t in TRADES if t["sym"] == s)
        n_long = sum(1 for t in TRADES
                     if t["sym"] == s and t["long"])
        match[s] = {"n": tot,
                    "p_long": n_long / tot if tot else 0.5}
    null: dict = {"PRIMARY": [], "F3": []}
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        draw: dict = {"PRIMARY": [], "F3": []}
        for s in ASSETS:
            m = match[s]
            if m["n"] == 0:
                continue
            env = envs[s]
            hi_bar = int(env["b"][-1]) - env["g0"] - 1
            bars = rng.choice(np.arange(WARMUP, hi_bar),
                              size=m["n"], replace=False)
            for t in bars:
                tr = _trade_tp(env, int(t),
                               bool(rng.random() < m["p_long"]),
                               TP_PRIMARY)
                if tr is None:
                    continue
                e0 = env["g0"] + tr["e0"] - g0_min
                seg = "PRIMARY" if e0 < split else "F3"
                draw[seg].append(tr["net"])
        for seg in ("PRIMARY", "F3"):
            if draw[seg]:
                null[seg].append(float(np.mean(draw[seg])))
    print("  matched-geometry null (descriptive, arm A):", flush=True)
    for seg in ("PRIMARY", "F3"):
        nv = np.array(null[seg])
        ev = float(np.mean([t["net"] for t in TRADES
                            if (t["e0"] < split) == (seg == "PRIMARY")]))
        pct = float((nv < ev).mean() * 100)
        print(f"    {seg:>7}: EV {ev:+.3f} vs "
              f"{nv.mean():+.3f}+-{nv.std():.3f} "
              f"-> {pct:.0f}th pct", flush=True)


def readouts(kept: list[dict], seg_streams: dict, n_g: int,
             split: int, envs: dict, aux: dict, g0_min: int) -> None:
    print("  long/short (arm A):", flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        for side, is_l in (("long", True), ("short", False)):
            sel = [t for t in kept if not t["skipped"]
                   and lo <= t["e0"] < hi and t["long"] == is_l]
            ev = float(np.mean([t["net"] for t in sel])) if sel \
                else float("nan")
            wr = (float(np.mean([t["net"] > 0 for t in sel]))
                  if sel else float("nan"))
            print(f"    {seg:>7} {side:>5}: n={len(sel):>4} "
                  f"EV={ev:+.3f}R WR={wr:.0%}", flush=True)
    print("  per-asset EV (arm A, pooled):", flush=True)
    n_pos = 0
    for sym in ASSETS:
        v = [t["net"] for t in kept
             if t["sym"] == sym and not t["skipped"]]
        ev = float(np.mean(v)) if v else float("nan")
        n_pos += ev > 0
        print(f"    {sym:>5}: n={len(v):>4} EV={ev:+.3f}R",
              flush=True)
    print(f"  positive assets: {n_pos}/10", flush=True)
    print("  ATR-pct quintile x EV (arm A):", flush=True)
    for q in range(5):
        lo_q, hi_q = q * 20, (q + 1) * 20
        sel = [t["net"] for t in kept
               if not t["skipped"] and np.isfinite(t["pct"])
               and lo_q < t["pct"] <= hi_q]
        ev = float(np.mean(sel)) if sel else float("nan")
        print(f"    Q{q + 1} ({lo_q:>3},{hi_q:>3}]: n={len(sel):>4} "
              f"EV={ev:+.3f}R", flush=True)
    avsl = np.zeros(n_g + 1)
    for sym in ASSETS:
        d = collect_trades(sym, repo_root())
        sizes = s1_sizes(aux[sym][2])
        for t in d["trades"]:
            e0 = d["g0"] + t["e0"] - g0_min
            e1 = d["g0"] + t["e1"] - g0_min
            hold = max(e1 - e0, 1)
            avsl[e0:e1 + 1] += sizes[t["e0"]] * t["net"] / (hold + 1)
    avsl = avsl[:n_g]
    print("  corr(OB arm A, AVSL S1) per segment:", flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        c = float(np.corrcoef(seg_streams[seg], avsl[lo:hi])[0, 1])
        print(f"    {seg:>7}: r={c:+.2f}", flush=True)


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0_min = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0_min
    split = int(n_g * SPLIT_FRAC)
    aux = sizing_aux(repo)
    TRADES.clear()
    TRADES.extend(base_trades(envs))
    decorate(TRADES, envs, aux, g0_min)
    print(f"[ob-overlay] entries={len(TRADES)} "
          f"grid n={n_g} split={split}", flush=True)

    fails: list = []
    streams: dict = {}
    for arm in ARMS:
        kept, n_skip = apply_arm(arm, TRADES)
        print(f"== arm {arm} (skipped {n_skip}) ==", flush=True)
        gates(arm, kept, n_g, split, fails)
        streams[arm] = {"true": stream_of(kept, n_g),
                        "legacy": stream_of(kept, n_g, legacy=True,
                                            envs=envs)}

    print("== sensitivity: legacy local-index placement (arm A) ==",
          flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        s = streams["A"]["legacy"][lo:hi]
        print(f"  {seg:>7}: Sh={nw_sharpe(s):+.2f} "
              f"DD={portfolio_dd(s):.0%}", flush=True)

    a_fails = [f for f in fails if f[0] == "A"]
    passers = [arm for arm in ARMS
               if not [f for f in fails if f[0] == arm]]
    if a_fails:
        print(f"\nVERDICT: KILL -- arm A gate failures: {a_fails}\n"
              "OB CLOSED FINAL per prereg 83c2b3f", flush=True)
    else:
        pick = min(passers, key=lambda a: PICK_ORDER[a])
        print(f"\nVERDICT: arm A PASS; full passers {passers}; "
              f"risk-first pick = {pick}", flush=True)

    kept_a, _ = apply_arm("A", TRADES)
    readouts(kept_a, {seg: streams["A"]["true"][
        0 if seg == "PRIMARY" else split:
        split if seg == "PRIMARY" else n_g]
        for seg in ("PRIMARY", "F3")},
        n_g, split, envs, aux, g0_min)
    descriptive_null(envs, g0_min, split)


if __name__ == "__main__":
    main()

