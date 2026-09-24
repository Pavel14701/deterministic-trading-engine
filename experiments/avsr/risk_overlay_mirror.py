# -*- coding: utf-8 -*-
"""AVSR-mirror risk-overlay track (prereg frozen in STATUS
2026-09-24, BEFORE this run; NEW dated prereg under P-2).

Mirror of the frozen AVSL battery: AVSR(70,345) =
SMA(high + price_v(high) - DeV) on the identical AVS base,
cross semantics IDENTICAL to AVSL (above = long, below =
short).  Configs S1..S4 and gates G1'..G5' byte-equivalent to
experiments/avsl/risk_overlay.py; the frozen engine module is
imported read-only (helpers only, never modified).

Run:  python -m experiments.avsr.risk_overlay_mirror
"""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,
    ASSETS,
    HORIZON,
    K_STOP,
    MSEC_4H,
    NW_LAGS,
    RISK_PCT,
    STAND_DIV,
    TAKER_FEE,
    TP_PRIMARY,
    WARMUP,
    _sim_5r,
    read_1h,
    repo_root,
    resample_4h,
)
from ta.src.custom.avs_base import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)
from ta.src.overlap.sma import sma_ind
from ta.src.volatility.atr import atr_ind

# ---- frozen gate config (identical to AVSL overlay b6005ca) ----
SPLIT_FRAC = 2 / 3
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


def avsr_line(hp: np.ndarray, cp: np.ndarray, vol: np.ndarray,
              stand_div: float = STAND_DIV) -> np.ndarray:
    """AVSR(FAST, SLOW) mirror: SMA(high + price_v(high) - DeV)."""
    vpc, vpr, _vm, vpci, dev = _avs_base(
        cp, vol, 70, 345, stand_div, False,
    )
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(hp, vpr, len_v, vpcc)
    adjusted = hp + price_v - dev
    return np.asarray(
        sma_ind(adjusted, 345, use_talib=False, nan_policy="ffill"),
        dtype=np.float64,
    )


def collect_trades(sym: str) -> dict:
    """TP=5R trade table, byte-identical semantics to the frozen
    AVSL collect_trades except the line is AVSR."""
    repo = repo_root()
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    line = avsr_line(hp, cp, vol)
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
        pnl = _sim_5r(hp, lp, cp, int(t), is_long, float(stop))
        if pnl is None:
            continue
        n = len(cp)
        k_exit = min(int(t) + HORIZON, n - 1)
        tp_px = cp[t] + TP_PRIMARY * risk if is_long \
            else cp[t] - TP_PRIMARY * risk
        for k in range(int(t) + 1, min(int(t) + 1 + HORIZON, n)):
            if is_long:
                hit = lp[k] <= stop or hp[k] >= tp_px
            else:
                hit = hp[k] >= stop or lp[k] <= tp_px
            if hit:
                k_exit = k
                break
        trades.append({
            "net": pnl - fee_r,
            "gross": pnl,
            "fee": fee_r,
            "e0": int(b[t]) - g0,
            "e1": int(b[k_exit]) - g0,
            "long": is_long,
        })
    return {"trades": trades, "g0": g0, "n_bars": int(b[-1]) - g0 + 1}


def _sizing_inputs(sym: str) -> tuple[np.ndarray, np.ndarray]:
    """rv100 (ann) and ATR14 pct within 500 bars, per 4H bar."""
    repo = repo_root()
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    rv = np.full(n, np.nan)
    for i in range(1, n):
        rv[i] = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN)
    a = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    pct = np.full(n, np.nan)
    for i in range(n):
        w = a[max(0, i - REG_WIN):i + 1]
        w = w[np.isfinite(w)]
        if w.size and np.isfinite(a[i]):
            pct[i] = float((w <= a[i]).mean() * 100.0)
    return rv, pct


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


def _block_boot_mean_ci(v: np.ndarray, b: int, block: int):
    n = v.size
    rng = np.random.default_rng(11)
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


def _apply_config(name: str, trs: list[dict],
                  aux: dict) -> list[dict]:
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
    data = {s: collect_trades(s) for s in ASSETS}
    g0 = min(d["g0"] for d in data.values())
    n_g = max(d["n_bars"] + d["g0"] for d in data.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    trs = []
    for s, d in data.items():
        for t in d["trades"]:
            trs.append({**t, "sym": s})
    trs.sort(key=lambda t: (t["e0"], t["sym"]))
    print(f"AVSR-MIRROR one-shot; global 4H grid n={n_g}, "
          f"PRIMARY<{split}<=F3, TP=5R trades {len(trs)}", flush=True)
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

    print("\n==== AVSR-MIRROR VERDICT (risk-first) ====", flush=True)
    passers = [c for c in CONFIGS if summary[c][0]]
    for c in CONFIGS:
        print(f"  {c}: {'PASS' if summary[c][0] else 'FAIL'} "
              f"(skipped {summary[c][1]}, kept {summary[c][2]})",
              flush=True)
    if not passers:
        print("0/4 configs pass -> AVSR-MIRROR TRACK CLOSED",
              flush=True)
    else:
        pick = min(passers, key=lambda c: PICK_ORDER[c])
        print(f"passers: {passers} -> selected (most conservative): "
              f"{pick}", flush=True)


if __name__ == "__main__":
    main()


