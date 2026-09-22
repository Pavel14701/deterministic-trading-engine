# -*- coding: utf-8 -*-
"""AVSL-cross 4H + S1 vol-target sizing -- the first PASSED strategy.

This is the CORE (production) copy of the configuration that passed
its full pre-registered battery on 2026-09-22.  It is self-contained
on purpose: it must never import from ``experiments/`` (the evidence
trail), and ``experiments/avsl/risk_overlay.py`` remains the
archived research driver that produced the verdict.

PROVENANCE (STATUS.md is the single evidence trail):
  signal family   experiments/avsl (screen -> confirm -> risk-overlay)
  screen prereg   commit bb5098b  (2026-09-21)
  confirm verdict 1e0e859  -- NW-z +3.31/+3.85 real, DD 61% FAIL
  overlay prereg  b6005ca  -- S1..S4 + G1'..G5', risk-first, FROZEN
  overlay verdict e6b4b4d  -- S1 vol-target PASS 5/5, selected

FROZEN CONFIG (changing ANY signal parameter here is forbidden; a
change requires a NEW prereg and closes this module):
  entry      close crosses AVSL(70, 345) (stand_div 2.0), normal arm
  stop       max(|close - line|, 2 * ATR14) at the entry bar
  exit       TP 5R primary, MTM at HORIZON 500 bars, stop-first
             within-bar; taker fee 10 bp round trip
  universe   BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP (Binance 1H
             -> deterministic 4H resample)
  segments   PRIMARY = first 2/3 of the common 4H calendar, F3 = rest
  sizing S1  size = clip(0.20 / rv100, 0.25, 2.0); rv100 = std of
             100 pre-entry 4H log returns, annualized x sqrt(6*365)
  account    bar return = 1% x sum(open sized R accrual)

FROZEN RESULT (runs/risk_overlay.log, must reproduce bit-for-bit):
  Sharpe_NW 1.50 PRIMARY / 2.84 F3   (gates >= 1.0 both)
  portfolio DD 22% PRIMARY / 12% F3  (gates <= 25% both)
  net EV +0.17R / +0.33R per trade
  block bootstrap CI excludes 0 in both segments

FORBIDDEN for any successor (measured, recorded in STATUS):
  - concurrency caps: S3/S4 destroyed the PRIMARY edge (Sharpe 0.22,
    EV +0.02R) -- clustered entries CARRY the edge;
  - ATR-percentile regime scaling alone: S2 left DD at 57% / 28%.

DECOMPOSITION (E1..E5, 2026-09-22 -- diagnostic, does not alter the
frozen config; full text: STATUS, "DECOMPOSITION COMPLETE"):
  engine     4H grid + wide-TP asymmetry (narrow TP = 0 everywhere;
             geometry alone earns +0.135R on random entries)
  amplifier  the AVSL cross, 4H ONLY (+0.037R/+0.167R over its
             matched null; the identical pipeline at 1D is dead and
             the entry sits at the 11th pct of its 1D null)
  regime     low-vol + 2025+ (2023-24 dead on holdout; low-ATR lift
             +0.502 vs +0.067 hi on F3) -- regime monitoring is a
             mandatory live-scale read-out
  sizing     de-lever (const 0.33 fixes most of DD) + vol-timing
             (informative on F3 +0.86 Sharpe; marginal on PRIMARY)
Any change inspired by this map (trailing exits, 3xATR stop, regime
filters) requires a NEW dated prereg and closes THIS module.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from ta.src.custom.avs_base import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)
from ta.src.overlap.sma import sma_ind
from ta.src.volatility.atr import atr_ind


# ---- frozen signal config -------------------------------------------------
FAST, SLOW = 70, 345
STAND_DIV = 2.0
WARMUP = 400
K_STOP = 2.0
TP_PRIMARY = 5.0
TAKER_FEE = 0.0005          # per side; round trip = 2x
HORIZON = 500
MSEC_4H = 14_400_000
ASSETS = (
    "BTC", "AVAX", "BNB", "DOGE", "ETH",
    "LINK", "LTC", "NEAR", "SOL", "XRP",
)

# ---- frozen S1 sizing ------------------------------------------------------
ANN = 6 * 365               # 4H bars per year
VOL_WIN = 100
VOL_TARGET = 0.20
SIZE_MIN, SIZE_MAX = 0.25, 2.0
RISK_PCT = 0.01             # 1% of equity per 1.0 size unit

# ---- evaluation (frozen gates, STATUS 2026-09-22) --------------------------
SPLIT_FRAC = 2 / 3
NW_LAGS = 500
BOOT_B = 1000
BOOT_BLOCK = 500            # = HORIZON
G1_SHARPE_MIN = 1.0
G2_DD_MAX = 0.25
G3_EV_MIN = 0.10
G4_ASSETS_MIN = 7


def repo_root() -> Path:
    """Repo root (engine/passed/avsl_cross_s1.py -> repo top)."""
    return Path(__file__).resolve().parents[2]


def read_1h(repo: Path, sym: str) -> tuple:
    """Binance 1H klines parquet -> (ts, high, low, close, volume)."""
    df = pl.read_parquet(repo / f"data/binance/kl_{sym}USDT_1h.parquet")
    return (
        df["ts"].to_numpy().astype(np.int64),
        df["high"].to_numpy().astype(np.float64),
        df["low"].to_numpy().astype(np.float64),
        df["close"].to_numpy().astype(np.float64),
        df["volume"].to_numpy().astype(np.float64),
    )


def resample_4h(
    ts: np.ndarray,
    hp: np.ndarray,
    lp: np.ndarray,
    cp: np.ndarray,
    vol: np.ndarray,
) -> tuple:
    """Deterministic 1H -> 4H aggregate (first/max/min/last/sum)."""
    bucket = ts // MSEC_4H
    df = pl.DataFrame(
        {"b": bucket, "ts": ts, "hp": hp, "lp": lp, "cp": cp,
         "vol": vol},
    )
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


def fast_line(lp: np.ndarray, cp: np.ndarray, vol: np.ndarray,
              stand_div: float = STAND_DIV) -> np.ndarray:
    """NaN-safe AVSL(FAST, SLOW), mirrors the Pine donor default."""
    vpc, vpr, _vm, vpci, dev = _avs_base(
        cp, vol, FAST, SLOW, stand_div, False,
    )
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(lp, vpr, len_v, vpcc)
    adjusted = lp - price_v + dev
    return np.asarray(
        sma_ind(adjusted, SLOW, use_talib=False, nan_policy="ffill"),
        dtype=np.float64,
    )


def _sim_5r(
    hp: np.ndarray,
    lp: np.ndarray,
    cp: np.ndarray,
    t: int,
    is_long: bool,
    stop: float,
) -> float | None:
    """TP=5R outcome over HORIZON bars; conservative within-bar
    (stop wins).  Returns net-of-nothing gross R or None.
    """
    risk = cp[t] - stop if is_long else stop - cp[t]
    if risk <= 0:
        return None
    entry = cp[t]
    tp = entry + TP_PRIMARY * risk if is_long else entry - TP_PRIMARY * risk
    n = len(cp)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                return -1.0
            if hp[k] >= tp:
                return TP_PRIMARY
        else:
            if hp[k] >= stop:
                return -1.0
            if lp[k] <= tp:
                return TP_PRIMARY
    sign = 1.0 if is_long else -1.0
    return float(sign * (cp[min(t + HORIZON, n - 1)] - entry) / risk)


def collect_trades(sym: str, repo: Path | None = None) -> dict:
    """TP=5R trade table for one asset, byte-identical semantics to
    the confirm run (experiments/avsl/avsl_cross_confirm._collect).

    Returns {"trades": [{net, gross, fee, e0, e1, long}], "g0",
    "n_bars"} with e0/e1 bucket indices relative to the asset grid.
    """
    repo = repo or repo_root()
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    line = fast_line(lp, cp, vol)
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
        # exit bucket: first bar hitting stop or TP within HORIZON
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


def s1_sizes(cp: np.ndarray) -> np.ndarray:
    """S1 vol-target size series: clip(0.20 / rv100, 0.25, 2.0).

    rv100 at bar i = std of log returns over the 100 bars BEFORE i
    (own bar excluded), annualized.  NaN fallback = 1.0 (unsized).
    """
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX))
    return sizes


def sized_accrual_stream(trades: list[dict], sizes: np.ndarray,
                         n_g: int) -> np.ndarray:
    """Per-bar portfolio R stream: each open trade accrues
    size x net R linearly over its hold buckets.
    """
    s = np.zeros(n_g + 1)
    for tr in trades:
        hold = max(tr["e1"] - tr["e0"], 1)
        w = sizes[tr["e0"]] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    return s[:n_g]


def nw_sharpe(v: np.ndarray, lags: int = NW_LAGS,
              ann: int = ANN) -> float:
    """Newey-West adjusted annualized Sharpe of a per-bar stream."""
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


def block_bootstrap_ci(v: np.ndarray, b: int = BOOT_B,
                       block: int = BOOT_BLOCK) -> tuple:
    """Circular block bootstrap 95% CI of the mean (seed 11 -- the
    seed used by the archived verdict run; do not change).
    """
    v = np.asarray(v)
    n = v.size
    if n < block:
        return float("nan"), float("nan")
    rng = np.random.default_rng(11)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(b, n_blocks))
    means = np.empty(b)
    for i in range(b):
        idx = np.concatenate(
            [(np.arange(starts[i, j], starts[i, j] + block)) % n
             for j in range(n_blocks)],
        )[:n]
        means[i] = v[idx].mean()
    return float(np.percentile(means, 2.5)), \
        float(np.percentile(means, 97.5))


def portfolio_dd(stream: np.ndarray) -> float:
    """Max drawdown of cumprod(1 + 1% x bar stream)."""
    eq = np.cumprod(1.0 + RISK_PCT * stream)
    return float(np.max(1.0 - eq / np.maximum.accumulate(eq)))


def evaluate(symbols: tuple = ASSETS,
             repo: Path | None = None) -> dict:
    """Recompute the frozen gate metrics for the S1-sized portfolio.

    Returns a dict with PRIMARY / F3 Sharpe_NW, DD, net EV,
    positive-asset count and bootstrap CIs.  Must reproduce the
    frozen verdict numbers (see module docstring); any deviation
    means the signal path diverged from the evidence trail.
    """
    repo = repo or repo_root()
    per = {s: collect_trades(s, repo) for s in symbols}
    g0 = min(d["g0"] for d in per.values())
    n_g = max(d["n_bars"] + d["g0"] for d in per.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    trades = []
    for s, d in per.items():
        for tr in d["trades"]:
            trades.append({**tr, "sym": s})
    trades.sort(key=lambda t: (t["e0"], t["sym"]))
    sizes_by = {s: s1_sizes(resample_4h(*read_1h(repo, s))[3])
                for s in symbols}
    s = np.zeros(n_g + 1)
    for tr in trades:
        hold = max(tr["e1"] - tr["e0"], 1)
        w = sizes_by[tr["sym"]][tr["e0"]] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    stream = s[:n_g]
    out: dict = {"n_g": n_g, "split": split, "n_trades": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades if lo <= t["e0"] < hi]
        lo_ci, hi_ci = block_bootstrap_ci(stream[lo:hi])
        pos = 0
        for sym in symbols:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        out[seg] = {
            "n": len(seg_tr),
            "sharpe_nw": nw_sharpe(stream[lo:hi]),
            "dd": portfolio_dd(stream[lo:hi]),
            "net_ev": (float(np.mean([t["net"] for t in seg_tr]))
                       if seg_tr else float("nan")),
            "pos_assets": pos,
            "boot_ci": (lo_ci, hi_ci),
        }
    out["gates_pass"] = all(
        out[seg]["sharpe_nw"] >= G1_SHARPE_MIN
        and out[seg]["dd"] <= G2_DD_MAX
        and out[seg]["net_ev"] >= G3_EV_MIN
        and out[seg]["pos_assets"] >= G4_ASSETS_MIN
        and out[seg]["boot_ci"][0] > 0
        for seg in ("PRIMARY", "F3")
    )
    return out


def main() -> None:
    """Self-check: recompute the frozen verdict numbers on archived
    data and print PASS/DEVIATION against the frozen gates.
    """
    r = evaluate()
    print(f"global 4H grid n={r['n_g']}, "
          f"PRIMARY<{r['split']}<=F3, trades {r['n_trades']}")
    for seg in ("PRIMARY", "F3"):
        m = r[seg]
        ci = m["boot_ci"]
        print(f"{seg:>7}: Sharpe_NW={m['sharpe_nw']:+.2f} "
              f"DD={m['dd']:.0%} EV={m['net_ev']:+.2f}R "
              f"pos={m['pos_assets']}/10 "
              f"CI=[{ci[0]:+.5f},{ci[1]:+.5f}] n={m['n']}")
    print(f"FROZEN GATES: {'PASS 5/5' if r['gates_pass'] else 'DEVIATION'}")


if __name__ == "__main__":
    main()

