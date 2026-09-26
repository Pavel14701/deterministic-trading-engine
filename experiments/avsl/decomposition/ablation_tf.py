# -*- coding: utf-8 -*-
"""E2 -- TF ablation 4H vs 1D (prereg 68953e0, STATUS 2026-09-22).

Frozen: 1D deterministic resample of the same 1H source; identical
pipeline at 1D (fast_line, ATR14, cross entries, stop
max(|c-line|, 2*ATR), TP 5R, horizon 500 BARS OF THE RESPECTIVE TF,
fee 10bp round trip, stop-first).  All frozen parameters keep their
numeric values; only the bar grid changes.

Gate (frozen): 4H net EV > 1D net EV + 0.05R on PRIMARY and F3.
Kill: 1D ~ 4H -> the edge is not 4H-specific.
Read-out per the per-geometry-null standard: matched random-geometry
null at each TF (E1 procedure, 100 draws, seeds 0..99), reported not
gated.

Run:  uv run python -m experiments.avsl.decomposition.ablation_tf
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    WARMUP,
    fast_line,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsl.decomposition.ablation_entry import (
    _segment_stats,
    _trade,
)
from ta.src.volatility.atr import atr_ind


N_DRAWS = 100
MARGIN_R = 0.05
SPLIT_FRAC = 2 / 3
MSEC_1D = 86_400_000
NW_LAGS = 500


def _resample(ts, hp, lp, cp, vol, msec: int):
    df = pl.DataFrame({"b": ts // msec, "ts": ts, "hp": hp,
                       "lp": lp, "cp": cp, "vol": vol})
    g = df.group_by("b", maintain_order=True).agg(
        pl.first("ts"), pl.max("hp"), pl.min("lp"),
        pl.last("cp"), pl.sum("vol"),
    )
    return (
        g["ts"].to_numpy().astype(np.int64),
        g["hp"].to_numpy().astype(np.float64),
        g["lp"].to_numpy().astype(np.float64),
        g["cp"].to_numpy().astype(np.float64),
        g["vol"].to_numpy().astype(np.float64),
    )


def _env(sym: str, repo, tf: str) -> dict:
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    if tf == "4H":
        ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    else:
        ts, hp, lp, cp, vol = _resample(ts, hp, lp, cp, vol, MSEC_1D)
    line = fast_line(lp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = ts // (MSEC_4H if tf == "4H" else MSEC_1D)
    return {
        "hp": hp, "lp": lp, "cp": cp, "line": line, "atr": atr,
        "up": up, "dn": dn, "cross_idx": cross_idx,
        "b": b, "g0": int(b[0]), "n_bars": int(b[-1]) - int(b[0]) + 1,
    }


def _arm(envs: dict) -> list[dict]:
    trades: list[dict] = []
    for s in ASSETS:
        e = envs[s]
        for t in e["cross_idx"]:
            if t < WARMUP:
                continue
            tr = _trade(e, int(t), bool(e["up"][t - 1]))
            if tr is not None:
                trades.append({**tr, "sym": s})
    return trades


def _null(envs: dict, trades: list[dict], split: int) -> dict:
    """E1 procedure: 100 matched random draws -> null distribution."""
    match = {}
    for s in ASSETS:
        tot = sum(1 for t in trades if t["sym"] == s)
        n_long = sum(1 for t in trades
                     if t["sym"] == s and t["long"])
        match[s] = {"n": tot,
                    "p_long": n_long / tot if tot else 0.5}
    ev = {"PRIMARY": [], "F3": []}
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
                    draw.append(tr)
        for seg in ("PRIMARY", "F3"):
            sel = [t["net"] for t in draw
                   if (t["e0"] < split) == (seg == "PRIMARY")]
            if sel:
                ev[seg].append(float(np.mean(sel)))
    return ev


def _report(tf: str, repo, split_cache: dict) -> dict:
    envs = {s: _env(s, repo, tf) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    trades = _arm(envs)
    print(f"[{tf}] bars/asset ~{envs[ASSETS[0]]['n_bars']}, "
          f"trades={len(trades)}, split@{split}", flush=True)
    res: dict = {"trades": trades, "split": split}
    for seg in ("PRIMARY", "F3"):
        st = _segment_stats(trades, split, seg)
        res[seg] = st
        print(f"[{tf}] {seg}: EV={st[0]:+.3f}R (n={st[1]}, "
              f"z={st[2]:+.2f})", flush=True)
    res["null"] = _null(envs, trades, split)
    for seg in ("PRIMARY", "F3"):
        v = np.array(res["null"][seg])
        mu, sd = float(v.mean()), float(v.std())
        pct = float((v < res[seg][0]).mean() * 100)
        print(f"[{tf}] null {seg}: {mu:+.3f}+-{sd:.3f} "
              f"(A at {pct:.0f}th pct)", flush=True)
        res[f"null_{seg}"] = (mu, sd, pct)
    split_cache[tf] = res
    return res


def main() -> None:
    repo = repo_root()
    cache: dict = {}
    # sanity first: 4H must reproduce E1 published numbers
    r4 = _report("4H", repo, cache)
    ok = (abs(r4["PRIMARY"][0] - 0.172) < 5e-3
          and abs(r4["F3"][0] - 0.335) < 5e-3
          and r4["trades"].__len__() == 2939)
    print(f"sanity vs E1 (+0.172/+0.335, n=2939): "
          f"{'MATCH' if ok else 'MISMATCH'}", flush=True)

    r1 = _report("1D", repo, cache)
    print("\n==== E2 GATE (4H > 1D + 0.05R, both segments) ====",
          flush=True)
    verdict = "PASS"
    for seg in ("PRIMARY", "F3"):
        a, d = r4[seg][0], r1[seg][0]
        gate = a > d + MARGIN_R
        verdict = verdict if gate else "FAIL"
        print(f"  {seg}: 4H {a:+.3f} vs 1D {d:+.3f} "
              f"(margin +{MARGIN_R:.2f}) -> "
              f"{'PASS' if gate else 'FAIL'}", flush=True)
    print(f"\nE2 VERDICT: {verdict}", flush=True)
    if verdict == "FAIL":
        print("Kill interpretation per prereg: the edge is NOT "
              "4H-specific (TF-scale drift capture).", flush=True)


if __name__ == "__main__":
    main()

