# -*- coding: utf-8 -*-
"""E6/E7/E8 -- dead-pool entry re-tests under the wide-TP frame
(prereg E6/E7/E8, STATUS 2026-09-22; E8 prereg frozen BEFORE run
code, commit 7105724).

Entry rules are the ORIGINAL ones moved to the 4H grid:
  zscore   MOM-1: z28 = (close-SMA28)/STD28 crosses above +1.5 ->
           long, below -1.5 -> short (28 x 4H = the original 168 x 1H)
  donchian close crosses above prior 20-bar high -> long, below
           prior 20-bar low -> short; EMA200 side filter (original)
  ob       E8: OB-retest events on 4H from the frozen RESEARCH
           preset R2 (experiments/ob/research_presets.py); demand
           retest -> long, supply retest -> short; entry bar = the
           detector's retest bar.  R1/R3 are sensitivity-only and
           are NOT runnable through this prereg gate.
Shared frozen frame: stop 3xATR14 (E-style, no line), TP 5R,
horizon 500, fee 10bp RT, S1-sized account stream, matched
random-geometry null (100 draws, seeds 0..99).

Run:
  uv run python -m experiments.avsl.retest_entry zscore   # E6
  uv run python -m experiments.avsl.retest_entry donchian # E7
  uv run python -m experiments.avsl.retest_entry ob       # E8
"""

from __future__ import annotations

import sys

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SPLIT_FRAC,
    TAKER_FEE,
    TP_PRIMARY,
    WARMUP,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from ta.src.volatility.atr import atr_ind


N_DRAWS = 100
MARGIN_R = 0.05
PCT_GATE = 95.0
SHARPE_MIN = 1.0
DD_MAX = 0.25
Z_LEVEL = 1.5
Z_WIN = 28
DON_WIN = 20
EMA_WIN = 200
STOP_K = 3.0            # E-style: 3 x ATR, no line
HORIZON = 500


def _env(sym: str, repo) -> dict:
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    b = ts // 14_400_000
    return {"hp": hp, "lp": lp, "cp": cp, "atr": atr,
            "ts": ts, "vol": vol,
            "b": b, "g0": int(b[0]),
            "n_bars": int(b[-1]) - int(b[0]) + 1}


def _ob_events(env: dict) -> tuple[np.ndarray, np.ndarray]:
    """E8 (prereg 7105724): frozen R2 preset; entry = retest bar;
    demand -> long, supply -> short.  Same-bar opposite-side
    duplicates are kept (both fills; declared in the prereg)."""
    from experiments.ob.research_presets import R2
    from ta.src.custom.market_structure import identify_order_blocks

    df = pl.DataFrame({
        "date": pl.from_epoch(env["ts"], time_unit="ms"),
        "high": env["hp"], "low": env["lp"],
        "close": env["cp"], "volume": env["vol"],
    })
    blocks = identify_order_blocks(df, cfg=R2)
    pos = {d: i for i, d in enumerate(df["date"].to_list())}
    ev = sorted((pos[r["retest"]], r["block_type"] == "demand")
                for r in blocks.iter_rows(named=True)
                if r["retest"] in pos)
    idx = np.array([e[0] for e in ev], dtype=np.int64)
    side = np.array([e[1] for e in ev], dtype=bool)
    return idx, side


def _cross_idx(env: dict, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """Entry bars + side; zscore/donchian signal on CLOSE crosses."""
    cp = env["cp"]
    if kind == "ob":
        idx, side = _ob_events(env)
        keep = idx >= WARMUP
        return idx[keep], side[keep]
    if kind == "zscore":
        roll = np.full(len(cp), np.nan)
        for i in range(Z_WIN, len(cp)):
            w = cp[i - Z_WIN:i + 1]
            mu, sd = w.mean(), w.std(ddof=1)
            if sd > 0:
                roll[i] = (cp[i] - mu) / sd
        long_sig = (roll[1:] > Z_LEVEL) & (roll[:-1] <= Z_LEVEL)
        short_sig = (roll[1:] < -Z_LEVEL) & (roll[:-1] >= -Z_LEVEL)
    else:                                   # donchian
        hp, lp = env["hp"], env["lp"]
        ema = np.full(len(cp), np.nan)
        k = 2.0 / (EMA_WIN + 1.0)
        ema[0] = cp[0]
        for i in range(1, len(cp)):
            ema[i] = cp[i] * k + ema[i - 1] * (1.0 - k)
        hh = np.full(len(cp), np.nan)
        ll = np.full(len(cp), np.nan)
        for i in range(DON_WIN, len(cp)):
            hh[i] = hp[i - DON_WIN:i].max()
            ll[i] = lp[i - DON_WIN:i].min()
        long_sig = ((cp[1:] > hh[1:]) & (cp[:-1] <= hh[1:])
                    & (cp[1:] > ema[1:]))
        short_sig = ((cp[1:] < ll[1:]) & (cp[:-1] >= ll[1:])
                     & (cp[1:] < ema[1:]))
    idx = np.nonzero(long_sig | short_sig)[0] + 1
    side = long_sig[idx - 1]
    keep = idx >= WARMUP
    return idx[keep], side[keep]


def _trade(env: dict, t: int, is_long: bool) -> dict | None:
    """Frozen frame: stop = 3xATR, TP 5R, horizon 500, stop-first."""
    hp, lp, cp, atr = env["hp"], env["lp"], env["cp"], env["atr"]
    risk = STOP_K * atr[t]
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    tp_px = entry + TP_PRIMARY * risk if is_long \
        else entry - TP_PRIMARY * risk
    n = len(cp)
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
    return {"net": pnl - fee_r,
            "e0": int(env["b"][t]) - env["g0"],
            "e1": int(env["b"][k_exit]) - env["g0"],
            "long": is_long}


def _segment(trades: list[dict], split: int,
             seg: str) -> tuple[float, int, float]:
    from experiments.avsl.avsl_cross_confirm import _nw_z

    sel = [t for t in trades
           if (t["e0"] < split) == (seg == "PRIMARY")]
    if not sel:
        return float("nan"), 0, float("nan")
    net = np.array([t["net"] for t in sel])
    order = np.argsort([t["e0"] for t in sel])
    return float(net.mean()), len(sel), float(_nw_z(net[order], 500))


def _null_and_gates(kind: str, envs: dict, trades: list[dict],
                    split: int, n_g: int) -> None:
    match = {}
    for s in ASSETS:
        tot = sum(1 for t in trades if t["sym"] == s)
        n_long = sum(1 for t in trades
                     if t["sym"] == s and t["long"])
        match[s] = {"n": tot,
                    "p_long": n_long / tot if tot else 0.5}
    null: dict = {"PRIMARY": [], "F3": []}
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
                tr = _trade(envs[s], int(t),
                            bool(rng.random() < m["p_long"]))
                if tr is not None:
                    draw.append(tr)
        for seg in ("PRIMARY", "F3"):
            sel = [t["net"] for t in draw
                   if (t["e0"] < split) == (seg == "PRIMARY")]
            if sel:
                null[seg].append(float(np.mean(sel)))
        if (seed + 1) % 25 == 0:
            print(f"  draw {seed + 1}/{N_DRAWS}", flush=True)

    # S1-sized account stream (engine accrual semantics)
    repo = repo_root()
    sizes_by = {s: s1_sizes(resample_4h(*read_1h(repo, s))[3])
                for s in ASSETS}
    stream = np.zeros(n_g + 1)
    for tr in trades:
        sz = sizes_by[tr["sym"]][tr["e0"]]
        hold = max(tr["e1"] - tr["e0"], 1)
        stream[tr["e0"]:tr["e1"] + 1] += sz * tr["net"] / (hold + 1)
    stream = stream[:n_g]

    print(f"\n==== {kind.upper()} GATES (both segments) ====",
          flush=True)
    verdict = True
    for seg, lo_s, hi_s in (("PRIMARY", 0, split),
                            ("F3", split, n_g)):
        ev, n, _z = _segment(trades, split, seg)
        nv = np.array(null[seg])
        mu, sd = float(nv.mean()), float(nv.std())
        pct = float((nv < ev).mean() * 100)
        seg_stream = stream[lo_s:hi_s]
        sh = nw_sharpe(seg_stream)
        dd = portfolio_dd(seg_stream)
        lo, hi = block_bootstrap_ci(seg_stream)
        checks = {
            "E-a": ev > mu + MARGIN_R,
            "E-b": pct >= PCT_GATE,
            "E-c": sh >= SHARPE_MIN,
            "E-d": dd <= DD_MAX,
            "E-f": lo > 0,
        }
        verdict = verdict and all(checks.values())
        fails = [k for k, ok in checks.items() if not ok]
        print(f"  {seg}: EV {ev:+.3f} vs null {mu:+.3f}+-{sd:.3f} "
              f"-> E-a {'PASS' if checks['E-a'] else 'FAIL'}, "
              f"E-b {pct:.0f}th pct {'PASS' if checks['E-b'] else 'FAIL'}\n"
              f"        n={n} Sh {sh:+.2f} "
              f"(E-c {'PASS' if checks['E-c'] else 'FAIL'}), "
              f"DD {dd:.0%} "
              f"(E-d {'PASS' if checks['E-d'] else 'FAIL'}), "
              f"CI [{lo:+.5f},{hi:+.5f}] "
              f"(E-f {'PASS' if checks['E-f'] else 'FAIL'})"
              + (f"   FAIL: {fails}" if fails else ""), flush=True)
    label = "FAIL" if not verdict else \
        "PASS (WEAK per family multiplicity, prereg 68953e0 addendum)"
    print(f"\n{kind.upper()} VERDICT: {label}", flush=True)


def main() -> None:
    kind = sys.argv[1]
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)

    trades: list[dict] = []
    for s in ASSETS:
        idx, side = _cross_idx(envs[s], kind)
        for t, is_long in zip(idx, side, strict=True):
            tr = _trade(envs[s], int(t), bool(is_long))
            if tr is not None:
                trades.append({**tr, "sym": s})
    print(f"[{kind}] entries={len(trades)}", flush=True)
    for seg in ("PRIMARY", "F3"):
        ev, n, z = _segment(trades, split, seg)
        print(f"[{kind}] {seg}: EV={ev:+.3f}R (n={n}, z={z:+.2f})",
              flush=True)

    _null_and_gates(kind, envs, trades, split, n_g)


if __name__ == "__main__":
    main()


