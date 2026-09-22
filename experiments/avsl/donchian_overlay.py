# -*- coding: utf-8 -*-
"""Donchian-4H risk overlay -- S1..S5 sweep (prereg STATUS
2026-09-22, frozen BEFORE this code; signal = E7 exactly).

Configs:
  S1  clip(0.20/rv100, 0.25, 2.0)          -- baseline (= engine S1)
  S2  clip(0.15/rv100, 0.15, 1.5)
  S3  S1 + cap (max 5 open, max 3.0 open exposure; breaching entries
      skipped)
  S4  S2 + cap
  S5  S2 x 0.5 when ATR14 pct (500w) > 80 at entry
Gates G1'-G5' on BOTH segments; risk-first selection (lowest PRIMARY
DD among full passers).

Run:  uv run python -m experiments.avsl.donchian_overlay
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,
    ASSETS,
    SPLIT_FRAC,
    VOL_WIN,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsl.retest_entry import _cross_idx, _env, _trade


CAP_COUNT = 5
CAP_EXPOSURE = 3.0
ATR_PCT_WIN = 500
ATR_PCT_HI = 80.0
REGIME_CUT = 0.5


def _vol_sizes(cp: np.ndarray, target: float, lo: float,
               hi: float) -> np.ndarray:
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(target / r, lo, hi))
    return sizes


def _atr_pcts(env: dict) -> np.ndarray:
    atr = env["atr"]
    n = len(atr)
    pct = np.full(n, np.nan)
    for i in range(n):
        w = atr[max(0, i - ATR_PCT_WIN):i + 1]
        w = w[np.isfinite(w)]
        if w.size and np.isfinite(atr[i]):
            pct[i] = float((w <= atr[i]).mean() * 100.0)
    return pct


def _apply_cap(trades: list[dict], sizes: np.ndarray) -> np.ndarray:
    """Chronological cap: skip entries breaching count/exposure."""
    out = np.zeros(len(trades))
    open_trades: list[tuple[int, float]] = []   # (e1, size)
    for i, tr in enumerate(trades):
        open_trades = [(e1, sz) for e1, sz in open_trades
                       if e1 >= tr["e0"]]
        sz = sizes[i]
        if len(open_trades) >= CAP_COUNT \
                or sum(sz2 for _, sz2 in open_trades) + sz > CAP_EXPOSURE:
            continue
        open_trades.append((tr["e1"], sz))
        out[i] = sz
    return out


def _stream(trades: list[dict], sz: np.ndarray,
            n_g: int) -> np.ndarray:
    s = np.zeros(n_g + 1)
    for tr, size in zip(trades, sz, strict=True):
        if size == 0:
            continue
        hold = max(tr["e1"] - tr["e0"], 1)
        s[tr["e0"]:tr["e1"] + 1] += size * tr["net"] / (hold + 1)
    return s[:n_g]


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)

    trades: list[dict] = []
    for s in ASSETS:
        idx, side = _cross_idx(envs[s], "donchian")
        for t, is_long in zip(idx, side, strict=True):
            tr = _trade(envs[s], int(t), bool(is_long))
            if tr is not None:
                trades.append({**tr, "sym": s})
    trades.sort(key=lambda t: (t["e0"], t["sym"]))
    n_tr = len(trades)
    print(f"global 4H grid n={n_g}, split@{split}, trades={n_tr}",
          flush=True)

    cp4h = {s: resample_4h(*read_1h(repo, s))[3] for s in ASSETS}
    s1_by = {s: _vol_sizes(cp4h[s], 0.20, 0.25, 2.0) for s in ASSETS}
    s2_by = {s: _vol_sizes(cp4h[s], 0.15, 0.15, 1.5) for s in ASSETS}
    pct_by = {s: _atr_pcts(envs[s]) for s in ASSETS}

    base_s1 = np.array([s1_by[t["sym"]][t["e0"]] for t in trades])
    base_s2 = np.array([s2_by[t["sym"]][t["e0"]] for t in trades])
    regs = np.array([REGIME_CUT if pct_by[t["sym"]][t["e0"]] > ATR_PCT_HI
                     else 1.0 for t in trades])

    configs: dict[str, tuple[np.ndarray, np.ndarray]] = {
        "S1": (base_s1, _stream(trades, base_s1, n_g)),
        "S2": (base_s2, _stream(trades, base_s2, n_g)),
        "S3": (None, None),   # cap applied chronologically below
        "S4": (None, None),
        "S5": (base_s2 * regs, _stream(trades, base_s2 * regs, n_g)),
    }
    for name, base in (("S3", base_s1), ("S4", base_s2)):
        capped = _apply_cap(trades, base)
        configs[name] = (capped, _stream(trades, capped, n_g))
        print(f"{name}: cap taken {int((capped > 0).sum())}/{n_tr}",
              flush=True)

    print("\nconfig   PRIMARY: Sh / DD / EV / pos / CI"
          "   |   F3: Sh / DD / EV / pos / CI   gates",
          flush=True)
    passing: list[tuple[str, float, float]] = []
    for name, (sizes, stream) in configs.items():
        ok_all = True
        dd_p = dd_f = float("nan")
        detail = []
        for seg, lo, hi in (("PRIMARY", 0, split),
                            ("F3", split, n_g)):
            taken = [t for t, sz in
                     zip(trades, sizes, strict=True)
                     if sz > 0 and (t["e0"] < split) == (seg == "PRIMARY")]
            net = (np.array([t["net"] for t in taken]) if taken
                   else np.array([float("nan")]))
            seg_stream = stream[lo:hi]
            sh = nw_sharpe(seg_stream)
            dd = portfolio_dd(seg_stream)
            ev = float(net.mean())
            pos = sum(1 for s in ASSETS
                      if (v := [t["net"] for t in taken
                                if t["sym"] == s])
                      and float(np.mean(v)) > 0)
            lo_ci, hi_ci = block_bootstrap_ci(seg_stream)
            checks = (sh >= 1.0, dd <= 0.25, ev >= 0.10, pos >= 7,
                      lo_ci > 0)
            ok_all = ok_all and all(checks)
            if seg == "PRIMARY":
                dd_p = dd
            else:
                dd_f = dd
            detail.append(
                f"Sh{sh:+.2f} DD{dd:.0%} EV{ev:+.2f} pos{pos} "
                f"CI[{lo_ci:+.4f},{hi_ci:+.4f}]"
                f"{'' if all(checks) else ' <-- FAIL'}")
        gates = "PASS" if ok_all else "FAIL"
        if ok_all:
            passing.append((name, dd_p, dd_f))
        print(f"{name:>6}  " + "  |  ".join(detail)
              + f"   -> {gates}", flush=True)

    print("\n==== DONCHIAN OVERLAY VERDICT ====", flush=True)
    if not passing:
        print("No config passes all gates on both segments -> "
              "track CLOSED FINAL per prereg (entry stays "
              "null-confirmed; the track is closed).", flush=True)
    else:
        passing.sort(key=lambda x: (x[1], x[2]))
        print(f"passing: {[p[0] for p in passing]} -> selected "
              f"{passing[0][0]} (risk-first: lowest PRIMARY DD)",
              flush=True)


if __name__ == "__main__":
    main()

