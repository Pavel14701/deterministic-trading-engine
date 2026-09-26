# -*- coding: utf-8 -*-
"""AVSL 15m wide-TP: two-stage intraday branch test (prereg frozen
in STATUS 2026-09-24 BEFORE this run).

Stage A (standing-rule KILL gate): gross edge first -- per-asset
gross EV > 0 AND gross WR > break-even at 5R on >= 5/10 assets in
BOTH segments; matched random-entry null reported.
Stage B (only if A passes): S1 sizing (ANN adapted to 15m),
TRUE-grid stream, gates G1'-G5' identical thresholds.

Signal logic copied from the frozen engine module (TF-adapted);
gates/helpers imported read-only.

Run:  python -m experiments.avsl.wide_tp_15m.avsl_15m_wide_tp
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    BOOT_B,
    BOOT_BLOCK,
    HORIZON,
    K_STOP,
    NW_LAGS,
    TP_PRIMARY,
    TAKER_FEE,
    WARMUP,
    block_bootstrap_ci,
    fast_line,
    nw_sharpe,
    portfolio_dd,
)
from ta.src.volatility.atr import atr_ind

REPO = Path(__file__).resolve().parents[2]
MSEC_15M = 900_000
ANN_15M = 4 * 24 * 365
VOL_WIN, VOL_TARGET, SIZE_MIN, SIZE_MAX = 100, 0.20, 0.25, 2.0
ASSETS_10 = (
    "BTC", "AVAX", "BNB", "DOGE", "ETH",
    "LINK", "LTC", "NEAR", "SOL", "XRP",
)
W12M = 12 * 30 * 24 * 4
N_NULL = 2000


def read_15m(sym: str):
    df = pl.read_parquet(REPO / f"data/okx21/raw_{sym}-USDT_15m.parquet")
    ts = df["ts"].to_numpy().astype(np.int64)
    if ts.max() < 10**11:
        ts = ts * 1000
    b = ts // MSEC_15M
    df = pl.DataFrame({
        "b": b, "ts": ts,
        "hp": df["high"].to_numpy().astype(np.float64),
        "lp": df["low"].to_numpy().astype(np.float64),
        "cp": df["close"].to_numpy().astype(np.float64),
        "vol": df["volume"].to_numpy().astype(np.float64),
    }).unique(subset="b", keep="last", maintain_order=True)
    return (
        df["ts"].to_numpy().astype(np.int64),
        df["hp"].to_numpy(), df["lp"].to_numpy(),
        df["cp"].to_numpy(), df["vol"].to_numpy(),
    )


def _sim_tp(hp, lp, cp, t: int, is_long: bool, stop: float,
            tp_mult: float) -> tuple[float, int] | None:
    """Gross R + exit bar; conservative within-bar (stop wins)."""
    risk = cp[t] - stop if is_long else stop - cp[t]
    if risk <= 0:
        return None
    entry = cp[t]
    tp = entry + tp_mult * risk if is_long else entry - tp_mult * risk
    n = len(cp)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                return -1.0, k
            if hp[k] >= tp:
                return tp_mult, k
        else:
            if hp[k] >= stop:
                return -1.0, k
            if lp[k] <= tp:
                return tp_mult, k
    sign = 1.0 if is_long else -1.0
    return float(sign * (cp[min(t + HORIZON, n - 1)] - entry) / risk), \
        min(t + HORIZON, n - 1)


def collect(sym: str, tp_mult: float = TP_PRIMARY):
    ts, hp, lp, cp, vol = read_15m(sym)
    line = fast_line(lp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = ts // MSEC_15M
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
        res = _sim_tp(hp, lp, cp, int(t), is_long, float(stop), tp_mult)
        if res is None:
            continue
        gross, k_exit = res
        trades.append({
            "net": gross - fee_r, "gross": gross, "fee_r": fee_r,
            "e0": int(b[t]) - g0, "e1": int(b[k_exit]) - g0,
            "long": is_long,
        })
    return {"trades": trades, "g0": g0,
            "n_bars": int(b[-1]) - g0 + 1, "cp": cp}


def s1_15m(cp: np.ndarray) -> np.ndarray:
    """S1 formula, annualization adapted to 15m (declared)."""
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN_15M)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX))
    return sizes


def seg_stats(trs: list[dict]) -> dict:
    if not trs:
        return {"n": 0, "ev_gross": float("nan"),
                "wr": float("nan"), "ev_net": float("nan"),
                "fee_r": float("nan")}
    g = np.array([t["gross"] for t in trs])
    nt = np.array([t["net"] for t in trs])
    return {"n": len(trs), "ev_gross": float(g.mean()),
            "wr": float((g > 0).mean()), "ev_net": float(nt.mean()),
            "fee_r": float(np.mean([t["fee_r"] for t in trs]))}


def main() -> None:
    print("AVSL 15M WIDE-TP one-shot (prereg 2026-09-24)", flush=True)
    data = {}
    for s in ASSETS_10:
        data[s] = collect(s)
        print(f"  {s:<5} crosses taken: {len(data[s]['trades'])}",
              flush=True)

    g0c = max(d["g0"] for d in data.values())
    n_g = min(d["g0"] + d["n_bars"] for d in data.values()) - g0c
    split = int(n_g * 2 / 3)
    print(f"common 15m grid n={n_g}, PRIMARY<{split}<=F3", flush=True)

    # ---- Stage A: gross edge first (KILL) ---------------------------
    print("\n--- STAGE A: gross edge (5R, fees excluded) ---", flush=True)
    a_fail: list[str] = []
    be = 1 / (1 + TP_PRIMARY)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        ok_ev = ok_wr = 0
        print(f"  {seg}: (BE WR = {be:.1%})", flush=True)
        for s, d in data.items():
            trs = [t for t in d["trades"]
                   if lo <= d["g0"] + t["e0"] - g0c < hi]
            st = seg_stats(trs)
            ok_ev += st["ev_gross"] > 0
            ok_wr += st["wr"] > be
            print(f"    {s:<5} n={st['n']:>5}  EVgross={st['ev_gross']:+.3f}R"
                  f"  WR={st['wr']:>6.1%}  fee_r={st['fee_r']:.2f}",
                  flush=True)
        if ok_ev < 5 or ok_wr < 5:
            a_fail.append(seg)
        print(f"  {seg}: EV>0 on {ok_ev}/10, WR>BE on {ok_wr}/10",
              flush=True)

    # matched random-entry null (read-out, seed 11)
    rng = np.random.default_rng(11)
    nulls = []
    for s in ASSETS_10:
        _ts, hp, lp, cp, _v = read_15m(s)
        a = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        picks = rng.integers(WARMUP, len(cp) - HORIZON - 1, N_NULL)
        vals = []
        for t in picks:
            is_long = bool(rng.integers(0, 2))
            risk = 2.0 * a[t]
            if not np.isfinite(risk) or risk <= 0:
                continue
            stop = cp[t] - risk if is_long else cp[t] + risk
            r = _sim_tp(hp, lp, cp, int(t), is_long, float(stop),
                        TP_PRIMARY)
            if r is not None:
                vals.append(r[0])
        nulls.append(float(np.mean(vals)))
        print(f"  null {s:<5} mean gross {nulls[-1]:+.4f}R", flush=True)
    print(f"  random-entry null mean gross: {np.mean(nulls):+.4f}R "
          f"(signal must clear this, not zero)", flush=True)

    if a_fail:
        print(f"\nSTAGE A FAIL: {a_fail} -> intraday AVSL branch "
              "CLOSED (Stage B not run)", flush=True)
        return

    # ---- Stage B: S1 + gates ----------------------------------------
    print("\n--- STAGE B: S1 sized stream, gates ---", flush=True)
    stream = np.zeros(n_g)
    seg_tr: dict[str, list] = {"PRIMARY": [], "F3": []}
    for s, d in data.items():
        sizes = s1_15m(d["cp"])
        for t in d["trades"]:
            e0 = d["g0"] + t["e0"] - g0c
            if e0 < 0:
                continue
            e1 = min(d["g0"] + t["e1"] - g0c, n_g - 1)
            seg = "PRIMARY" if e0 < split else "F3"
            seg_tr[seg].append({**t, "sym": s})
            hold = max(t["e1"] - t["e0"], 1)
            stream[e0:e1 + 1] += sizes[t["e0"]] * t["net"] / (hold + 1)

    fails: list[str] = []
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        v = stream[lo:hi]
        sh = nw_sharpe(v, NW_LAGS, ANN_15M)
        dd = portfolio_dd(v)
        trs = seg_tr[seg]
        ev = float(np.mean([t["net"] for t in trs]))
        pos = sum(
            1 for s in ASSETS_10
            if (vv := [t["net"] for t in trs if t["sym"] == s])
            and float(np.mean(vv)) > 0
        )
        lo_ci, hi_ci = block_bootstrap_ci(v, BOOT_B, BOOT_BLOCK)
        for name, ok in (("G1p", sh >= 1.0), ("G2p", dd <= 0.25),
                         ("G3p", ev >= 0.10), ("G4p", pos >= 7),
                         ("G5p", lo_ci > 0)):
            if not ok:
                fails.append(f"{name}:{seg}")
        print(f"  {seg:>7} (n={len(trs)}): Sh_NW={sh:+.2f} | "
              f"DD={dd:.1%} | EV={ev:+.3f}R | assets+ {pos}/10 | "
              f"CI [{lo_ci:+.6f},{hi_ci:+.6f}]", flush=True)

    roll = np.convolve(stream, np.ones(W12M), mode="valid")
    print(f"  PF-G4 read-out (NOT gated): {int(np.sum(roll <= 0))}/"
          f"{len(roll)} trailing 12m windows negative", flush=True)

    # fee sensitivity read-out (maker-ish, informational)
    for seg, trs in seg_tr.items():
        for fee_rt in (0.0005, 0.0002, 0.0001):
            evs = float(np.mean([t["gross"] - t["fee_r"] * fee_rt
                                 / TAKER_FEE for t in trs]))
            print(f"  fee read-out {seg}: EV @ {fee_rt * 1e4:.0f}bp RT "
                  f"= {evs:+.3f}R", flush=True)

    print("\n==== AVSL-15M VERDICT ====", flush=True)
    if fails:
        print(f"FAIL (Stage B): {', '.join(fails)} -> intraday AVSL "
              "branch CLOSED", flush=True)
    else:
        print("PASS (Stage A + G1'-G5') -> intraday AVSL track opens",
              flush=True)


if __name__ == "__main__":
    main()
