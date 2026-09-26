# -*- coding: utf-8 -*-
"""Component-level predictive diagnostic, crypto 4H -- prereg run.

Frozen prereg: PREREG_COMPONENT_DIAG_2026-09-26.md (commit 074c847).
Measurement only: IC / decile spread / conditional AVSL EV / overlap /
stability for each candidate component SEPARATELY.  No gates, no
mixing, no strategy change.  One run per component; re-runs only for
bug fixes (logged in EXPERIMENT.md).

Components (prereg section 2):
  C1  Hurst DFA-1, W in {100, 200}          (4H log returns)
  C2  funding_raw / funding_z30 / funding_hi30
  C3  oi_chg_1 / oi_chg_24 / oi_z30         (coverage 2026-08-21..09-21)
  C4  liquidations -- SKIPPED: no free data (prereg rule: skip + log)
  C5  tbi_1 / tbi_6 (taker buy/sell imbalance)
  C6  btc_ret_1 lags {1, 2, 3}              (alts only)

Run:
  python -m experiments.avsl.component_diagnostic.v1_diag
Output: runs/component_diagnostic.log
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    SPLIT_FRAC,
    collect_trades,
    fast_line,
    read_1h,
    repo_root,
    resample_4h,
)

__version__ = "1.0.0"

HORIZONS = (1, 3, 6, 12, 24)
HURST_WINDOWS = (100, 200)
C6_LAGS = (1, 2, 3)
ROLL30 = 180              # 30d in 4H bars
ROLL30_MIN = 60
SEED = 11
BOOT_B = 1000
BOOT_BLOCK = 24           # 4H bars
NW_LAGS = 3               # x horizon at call site
FUNDING_START = "2023-09" # logged coverage note

# verdict thresholds (prereg section 7)
V_SIGN_ASSETS = 8         # of 10 (9 for C6 alts)
V_EV_SPREAD = 0.15        # R


def _rank(x: np.ndarray) -> np.ndarray:
    """Average-tie ranks (1-based), NaN preserved."""
    out = np.full(len(x), np.nan)
    m = np.isfinite(x)
    v = x[m]
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v))
    r[order] = np.arange(1, len(v) + 1, dtype=np.float64)
    # average ties
    sv = v[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    out[m] = r
    return out


def _pairs(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m = np.isfinite(x) & np.isfinite(y)
    return x[m], y[m]


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    """Spearman rank correlation + n (NaN pairs dropped)."""
    xs, ys = _pairs(x, y)
    if len(xs) < 30:
        return float("nan"), len(xs)
    rx, ry = _rank(xs), _rank(ys)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan"), len(xs)
    ic = float(np.corrcoef(rx, ry)[0, 1])
    return ic, int(len(xs))


def nw_tstat(x: np.ndarray, y: np.ndarray, lags: int) -> tuple[float, int]:
    """Newey-West t-stat of the OLS slope rank(y) ~ rank(x).

    HAC Bartlett kernel with `lags` lags on OLS residuals; valid under
    h-overlap autocorrelation (prereg section 3.1).
    """
    xs, ys = _pairs(x, y)
    n = len(xs)
    if n < 30:
        return float("nan"), n
    rx, ry = _rank(xs) - _rank(xs).mean(), _rank(ys) - _rank(ys).mean()
    denom = float(rx @ rx)
    if denom == 0:
        return float("nan"), n
    beta = float(rx @ ry) / denom
    e = ry - beta * rx
    s0 = float(e @ e)
    s = s0
    for l in range(1, min(lags, n - 1) + 1):
        w = 1.0 - l / (lags + 1.0)
        s += 2.0 * w * float(e[l:] @ e[:-l])
    se = np.sqrt(s / denom**2) if s > 0 else np.inf
    return float(beta / se), n


def decile_spread(comp: np.ndarray, y: np.ndarray,
                  rng: np.random.Generator) -> tuple[float, float, float, int]:
    """Mean fwd return top decile minus bottom decile of comp;
    circular block bootstrap CI (block 24, B 1000, seed frozen)."""
    m = np.isfinite(comp) & np.isfinite(y)
    c, v = comp[m], y[m]
    n = len(c)
    if n < 100:
        return float("nan"), float("nan"), float("nan"), n
    k = max(n // 10, 1)
    order = np.argsort(c, kind="mergesort")
    spread = float(v[order[-k:]].mean() - v[order[:k]].mean())
    n_blocks = int(np.ceil(n / BOOT_BLOCK))
    starts = rng.integers(0, n, size=(BOOT_B, n_blocks))
    means = np.empty(BOOT_B)
    for b in range(BOOT_B):
        idx = np.concatenate(
            [(starts[b, j] + np.arange(BOOT_BLOCK)) % n
             for j in range(n_blocks)],
        )[:n]
        cb, cc = c[idx], v[idx]
        ko = np.argsort(cb, kind="mergesort")
        means[b] = cc[ko[-k:]].mean() - cc[ko[:k]].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return spread, float(lo), float(hi), n


def tertile_ev(comp_at_entry: np.ndarray, net: np.ndarray,
               ) -> tuple[list[float], list[int]]:
    """Promoted-ledger trade EV by comp tertile at entry (per asset)."""
    m = np.isfinite(comp_at_entry) & np.isfinite(net)
    c, v = comp_at_entry[m], net[m]
    if len(c) < 30:
        return [float("nan")] * 3, [0, 0, 0]
    q1, q2 = np.quantile(c, [1 / 3, 2 / 3])
    masks = [c <= q1, (c > q1) & (c <= q2), c > q2]
    evs = [float(np.mean(v[mm])) if mm.sum() else float("nan")
           for mm in masks]
    ns = [int(mm.sum()) for mm in masks]
    return evs, ns


def mannwhitney_z(a: np.ndarray, b: np.ndarray) -> tuple[float, int, int]:
    """Mann-Whitney U normal-approx z (a vs b), NaN dropped."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 30 or len(b) < 30:
        return float("nan"), len(a), len(b)
    pooled = _rank(np.concatenate([a, b]))
    r_a = pooled[:len(a)].sum()
    n1, n2 = len(a), len(b)
    u = r_a - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    sd = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    return float((u - mu) / sd), n1, n2


# ---- series helpers --------------------------------------------------------

def rolling_nan_z(x: np.ndarray, w: int, min_valid: int) -> np.ndarray:
    """Trailing z-score over w bars (min_valid finite), NaN-safe."""
    n = len(x)
    out = np.full(n, np.nan)
    valid = np.isfinite(x)
    xv = np.where(valid, x, 0.0)
    cs = np.cumsum(xv)
    cs2 = np.cumsum(xv * xv)
    cn = np.cumsum(valid.astype(np.int64))
    for i in range(n):
        j = max(0, i - w)
        cnt = cn[i] - (cn[j - 1] if j > 0 else 0)
        if cnt < min_valid:
            continue
        s = cs[i] - (cs[j - 1] if j > 0 else 0.0)
        s2 = cs2[i] - (cs2[j - 1] if j > 0 else 0.0)
        mu = s / cnt
        var = max(s2 / cnt - mu * mu, 0.0)
        sd = np.sqrt(var)
        if sd > 0 and np.isfinite(x[i]):
            out[i] = (x[i] - mu) / sd
    return out


def rolling_sum(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    cs = np.concatenate([[0.0], np.cumsum(np.where(np.isfinite(x), x, 0.0))])
    ok = np.isfinite(x)
    for i in range(w - 1, len(x)):
        if ok[i - w + 1:i + 1].all():
            out[i] = cs[i + 1] - cs[i + 1 - w]
    return out


def _dfa_projection(s: int) -> np.ndarray:
    """Residual-maker for per-block linear detrending (DFA-1)."""
    xcol = np.arange(s, dtype=np.float64)
    X = np.stack([np.ones(s), xcol], axis=1)
    return np.eye(s) - X @ np.linalg.inv(X.T @ X) @ X.T


def hurst_dfa_series(ret: np.ndarray, w: int, n_scales: int = 12,
                     s_min: int = 8) -> np.ndarray:
    """Rolling DFA-1 Hurst exponent, H at bar t uses ret[t-w:t].

    Scales log-spaced in [s_min, w/4]; H = OLS slope of log F(s)
    on log s.  NaN until enough history (and on NaN inputs).
    """
    n = len(ret)
    out = np.full(n, np.nan)
    scales = np.unique(np.round(
        np.logspace(np.log10(s_min), np.log10(w // 4), n_scales),
    ).astype(int))
    proj = {int(s): _dfa_projection(int(s)) for s in scales}
    logs = np.log(scales.astype(np.float64))
    for t in range(w, n + 1):
        win = ret[t - w:t]
        if not np.isfinite(win).all():
            continue
        prof = np.cumsum(win - win.mean())
        logf = np.empty(len(scales))
        for k, s in enumerate(scales):
            m = w // int(s)
            blocks = prof[:m * int(s)].reshape(m, int(s))
            resid = blocks @ proj[int(s)].T
            logf[k] = 0.5 * np.log(max(float((resid**2).mean()), 1e-300))
        out[t - 1] = float(np.polyfit(logs, logf, 1)[0])
    return out


# ---- per-asset component builders -----------------------------------------

def load_kl_raw(repo: Path, sym: str) -> pl.DataFrame:
    return pl.read_parquet(repo / f"data/binance/kl_{sym}USDT_1h.parquet")


def funding_series(repo: Path, sym: str, ts4: np.ndarray) -> np.ndarray:
    """Binance 8h funding -> 4H buckets (value valid at bucket end)."""
    f = pl.read_parquet(repo / f"data/funding_binance/fbnb_{sym}USDT.parquet")
    fts = f["ts"].to_numpy().astype(np.int64)
    fr = f["rate"].to_numpy().astype(np.float64)
    end_ts = ts4 + MSEC_4H
    idx = np.searchsorted(fts, end_ts, side="left") - 1
    out = np.where(idx >= 0, fr[np.clip(idx, 0, None)], np.nan)
    out[idx < 0] = np.nan
    return out


def oi_series(repo: Path, sym: str, buckets: np.ndarray) -> np.ndarray:
    """1h OI -> 4H last value per bucket (ffill over gaps)."""
    o = pl.read_parquet(repo / f"data/binance/oi_{sym}USDT_1h.parquet")
    ob = o["ts"].to_numpy().astype(np.int64) // MSEC_4H
    oval = o["oi"].to_numpy().astype(np.float64)
    lut = dict(zip(ob.tolist(), oval.tolist()))
    out = np.array([lut.get(int(b), np.nan) for b in buckets])
    last = np.nan
    for i in range(len(out)):  # ffill
        if np.isfinite(out[i]):
            last = out[i]
        else:
            out[i] = last
    return out


def tbi_series(kl: pl.DataFrame, ts4: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Taker buy/sell imbalance: per-4H-bar and rolling 24h sum."""
    b = (kl["ts"].to_numpy().astype(np.int64)) // MSEC_4H
    buy = kl["taker_buy_volume"].to_numpy().astype(np.float64)
    vol = kl["volume"].to_numpy().astype(np.float64)
    df = pl.DataFrame({"b": b, "buy": buy, "vol": vol}).group_by(
        "b", maintain_order=True,
    ).agg(pl.sum("buy"), pl.sum("vol"))
    buy4, vol4 = df["buy"].to_numpy(), df["vol"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        tbi1 = np.where(vol4 > 0, (2 * buy4 - vol4) / vol4, np.nan)
    return tbi1, rolling_sum(tbi1, 6)


def build_components(repo: Path, sym: str,
                     btc_ret_by_bucket: dict[int, float] | None,
                     ) -> tuple[dict, dict]:
    """All component series for one asset on its own 4H grid.

    Returns (comps, aux): comps maps name -> np.ndarray; aux carries
    entry-bar data (trades, line state, hurst/none stats inputs).
    """
    ts, hp, lp, cp, vol = resample_4h(*read_1h(repo, sym))
    n = len(cp)
    buckets = ts // MSEC_4H
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    comps: dict[str, np.ndarray] = {}

    # C1 Hurst DFA-1
    for w in HURST_WINDOWS:
        comps[f"C1_H{w}"] = hurst_dfa_series(lr, w)

    # C2 funding
    fr = funding_series(repo, sym, ts)
    comps["C2_funding_raw"] = fr
    comps["C2_funding_z30"] = rolling_nan_z(fr, ROLL30, ROLL30_MIN)
    comps["C2_funding_hi30"] = rolling_nan_hi(fr, ROLL30, 0.90)

    # C3 OI
    oi = oi_series(repo, sym, buckets)
    lo = np.full(n, np.nan)
    lo[1:] = np.log(np.where(oi[1:] > 0, oi[1:], np.nan)
                    / np.where(oi[:-1] > 0, oi[:-1], np.nan))
    lo24 = np.full(n, np.nan)
    lo24[6:] = np.log(np.where(oi[6:] > 0, oi[6:], np.nan)
                      / np.where(oi[:-6] > 0, oi[:-6], np.nan))
    comps["C3_oi_chg_1"] = lo
    comps["C3_oi_chg_24"] = lo24
    comps["C3_oi_z30"] = rolling_nan_z(lo24, ROLL30, ROLL30_MIN)

    # C5 taker imbalance
    tbi1, tbi6 = tbi_series(load_kl_raw(repo, sym), ts)
    comps["C5_tbi_1"] = tbi1
    comps["C5_tbi_6"] = tbi6

    # C6 BTC lead-lag (alts only)
    if sym != "BTC" and btc_ret_by_bucket is not None:
        for lag in C6_LAGS:
            v = np.array([
                btc_ret_by_bucket.get(int(b) - lag, np.nan) for b in buckets
            ])
            comps[f"C6_btc_lag{lag}"] = v

    # forward log returns
    fwd = {}
    for h in HORIZONS:
        f = np.full(n, np.nan)
        f[:-h] = np.log(cp[h:] / cp[:-h])
        fwd[h] = f

    # AVSL ledger + arm state
    led = collect_trades(sym, repo)
    line = fast_line(lp, cp, vol)
    state = np.sign(cp - line)
    aux = {"led": led, "state": state, "fwd": fwd, "cp": cp,
           "ts": ts, "buckets": buckets}
    return comps, aux


def rolling_nan_hi(x: np.ndarray, w: int, q: float) -> np.ndarray:
    """1 if x[i] > q-quantile of trailing w bars (min 60), else 0."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(n):
        win = x[max(0, i - w):i]
        win = win[np.isfinite(win)]
        if len(win) < ROLL30_MIN or not np.isfinite(x[i]):
            continue
        out[i] = float(x[i] > np.quantile(win, q))
    return out


# ---- evaluation ------------------------------------------------------------

def decile_monotone(comp: np.ndarray, y: np.ndarray) -> bool:
    """True if decile means of y vs comp are monotone:
    abs(Spearman(decile index, decile mean)) >= 0.9 (prereg section
    7.3: 'monotone decile spread, not top-vs-rest only').  A V/U-shape
    fails (rank corr near 0); monotone-with-noise passes."""
    m = np.isfinite(comp) & np.isfinite(y)
    c, v = comp[m], y[m]
    if len(c) < 100:
        return False
    qs = np.quantile(c, np.linspace(0, 1, 11))
    means = []
    for k in range(10):
        mm = (c >= qs[k]) & (c <= qs[k + 1] if k == 9 else c < qs[k + 1])
        means.append(float(np.mean(v[mm])) if mm.sum() else np.nan)
    means = np.array(means)
    ok = np.isfinite(means)
    if ok.sum() < 8:
        return False
    idx = np.arange(10, dtype=np.float64)[ok]
    rho = float(np.corrcoef(idx, means[ok])[0, 1])
    return bool(abs(rho) >= 0.9)


def segment_bounds(n: int) -> dict[str, tuple[int, int]]:
    split = int(n * SPLIT_FRAC)
    return {"PRIMARY": (0, split), "F3": (split, n), "FULL": (0, n)}


def eval_component(name: str, comp_name: str, per_asset: dict,
                   lines: list[str]) -> dict:
    """Full read-out for one component series across assets/horizons."""
    L = lines
    L.append(f"{name} ({comp_name}):")
    res: dict = {"ic": {}, "ev_spread": [], "mono_frac": [],
                 "stability": [], "overlap": []}
    sign_full, sign_seg = [], []
    for sym, (comps, aux) in per_asset.items():
        comp = comps.get(comp_name)
        if comp is None:
            continue
        segs = segment_bounds(len(comp))
        best = (float("nan"), "", "")
        for h in HORIZONS:
            fwd = aux["fwd"][h]
            for seg, (lo, hi) in segs.items():
                ic, n = spearman(comp[lo:hi], fwd[lo:hi])
                t, _ = nw_tstat(comp[lo:hi], fwd[lo:hi], NW_LAGS * h)
                res["ic"][(sym, h, seg)] = (ic, t, n)
                if seg == "FULL" and np.isfinite(ic):
                    sign_full.append((sym, ic))
                    if not np.isfinite(best[0]) or abs(ic) > abs(best[0]):
                        best = (ic, h, sym)
            # stability
            ic_p = res["ic"].get((sym, h, "PRIMARY"), (np.nan,))[0]
            ic_f = res["ic"].get((sym, h, "F3"), (np.nan,))[0]
            if np.isfinite(ic_p) and np.isfinite(ic_f):
                res["stability"].append(
                    bool(np.sign(ic_p) == np.sign(ic_f)))
            # decile spread (FULL)
            rng = np.random.default_rng(SEED)
            sp, lo_ci, hi_ci, n = decile_spread(comp, fwd, rng)
            mono = decile_monotone(comp, fwd)
            res["mono_frac"].append(mono)
            L.append(
                f"  {sym} h={h}: IC {ic:+.3f} (t {t:+.1f}, n={n}) "
                f"decile {sp:+.4%} CI [{lo_ci:+.4%},{hi_ci:+.4%}] "
                f"mono={mono}")
        # overlap with AVSL arm state
        ovl = []
        for seg, (lo, hi) in segs.items():
            o, n = spearman(comp[lo:hi], aux["state"][lo:hi])
            if np.isfinite(o):
                ovl.append(abs(o))
        res["overlap"].append(max(ovl) if ovl else np.nan)
        # conditional AVSL EV by tertile at entry
        led = aux["led"]["trades"]
        if len(led) >= 30:
            idx = np.array([tr["e0"] for tr in led])
            net = np.array([tr["net"] for tr in led])
            evs, ns = tertile_ev(comp[idx], net)
            spread = evs[2] - evs[0]
            if np.isfinite(spread):
                res["ev_spread"].append(spread)
            L.append(
                f"  {sym} cond AVSL EV: Q1 {evs[0]:+.2f}R "
                f"Q2 {evs[1]:+.2f}R Q3 {evs[2]:+.2f}R "
                f"(n={ns[0]}/{ns[1]}/{ns[2]}); spread {spread:+.2f}R")
    # summary across assets (best feature variant handled by caller)
    ic_by_asset: dict[str, float] = {}
    for (sym, h, seg), (ic, _t, _n) in res["ic"].items():
        if seg == "FULL" and np.isfinite(ic):
            ic_by_asset.setdefault(sym, ic)
    ics = np.array(list(ic_by_asset.values()))
    ics = ics[np.isfinite(ics)]
    pos = int((ics > 0).sum())
    L.append(
        f"  >> {name}: mean IC {np.nanmean(ics):+.3f} "
        f"sign {pos}/{len(ics)} assets; "
        f"stability {sum(res['stability'])}/{len(res['stability'])} "
        f"PRIMARY/F3 sign-consistent; "
        f"mean overlap {np.nanmean(res['overlap']):.2f}; "
        f"mono frac {np.nanmean(res['mono_frac']):.2f}; "
        f"mean EV spread {np.nanmean(res['ev_spread']):+.2f}R")
    res["sign_pos"] = pos
    res["sign_n"] = len(ics)
    res["stab"] = (sum(res["stability"]), len(res["stability"]))
    res["ev_mean"] = float(np.nanmean(res["ev_spread"]))
    res["mono_mean"] = float(np.nanmean(res["mono_frac"]))
    return res


def verdict(res: dict) -> str:
    """Prereg section 7: all four criteria must hold for a follow-up."""
    c1 = res["sign_pos"] >= V_SIGN_ASSETS or (
        res["sign_n"] - res["sign_pos"]) >= V_SIGN_ASSETS
    c2 = res["stab"][1] > 0 and res["stab"][0] / res["stab"][1] >= 0.8
    c3 = res["mono_mean"] >= 0.5
    c4 = np.isfinite(res["ev_mean"]) and res["ev_mean"] > V_EV_SPREAD
    ok = all([c1, c2, c3, c4])
    return ("FOLLOW-UP" if ok else
            "descriptive" + ("" if not c4 else " (EV spread only)"))


def main() -> None:
    """Single frozen run: all components, all assets, one log."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/component_diagnostic.log")
    ap.add_argument("--assets", nargs="*", default=list(ASSETS))
    ap.add_argument("--components", nargs="*",
                    default=["C1", "C2", "C3", "C5", "C6"])
    args = ap.parse_args()
    repo = repo_root()
    lines: list[str] = [
        f"component diagnostic v{__version__}  "
        f"prereg PREREG_COMPONENT_DIAG_2026-09-26.md (074c847)",
        f"assets {args.assets}; components {args.components}",
        "C4 liquidations: SKIPPED (no free data; prereg section 2)",
        f"C2 note: Binance funding coverage from {FUNDING_START}; "
        "IC on overlap only",
        "C3 note: OI coverage 2026-08-21..09-21 (thin; stability N/A)",
        "",
    ]
    # BTC first (lead-lag source), then alts
    order = ["BTC"] + [a for a in args.assets if a != "BTC"]
    per_asset: dict[str, tuple[dict, dict]] = {}
    btc_ret: dict[int, float] | None = None
    for sym in order:
        comps, aux = build_components(repo, sym, btc_ret)
        per_asset[sym] = (comps, aux)
        if sym == "BTC":
            lr = np.full(len(aux["cp"]), np.nan)
            lr[1:] = np.log(aux["cp"][1:] / aux["cp"][:-1])
            btc_ret = dict(zip(aux["buckets"].tolist(), lr.tolist()))
        print(f"loaded {sym}: {len(aux['cp'])} 4H bars, "
              f"{len(aux['led']['trades'])} trades", flush=True)
    summary = []
    for c in args.components:
        variants = sorted(
            vn for a in order
            for vn in per_asset[a][0]
            if vn.startswith(c + "_"))
        for vn in variants:
            res = eval_component(c, vn, per_asset, lines)
            summary.append((c, vn, res, verdict(res)))
            lines.append("")
    lines.append("=== SUMMARY (best variant per component) ===")
    lines.append("Component        | mean IC | sign  | stab  | mono | "
                 "EV spread | overlap | verdict")
    best_by_c: dict[str, tuple] = {}
    for c, vn, res, v in summary:
        ic = np.nanmean([ic for (s, h, g), (ic, t, n) in res["ic"].items()
                         if g == "FULL" and np.isfinite(ic)])
        if c not in best_by_c or abs(ic) > best_by_c[c][1]:
            best_by_c[c] = (vn, ic, res, v)
    for c, (vn, ic, res, v) in sorted(best_by_c.items()):
        lines.append(
            f"{c:16s} | {ic:+.3f} | "
            f"{res['sign_pos']}/{res['sign_n']} | "
            f"{res['stab'][0]}/{res['stab'][1]} | "
            f"{res['mono_mean']:.2f} | {res['ev_mean']:+.2f}R | "
            f"{np.nanmean(res['overlap']):.2f} | {v}  [{vn}]")
    lines.append("")
    lines.append(
        "Verdict per prereg section 7 (follow-up needs ALL: "
        f"sign >= {V_SIGN_ASSETS} assets, stab >= 80%, "
        f"mono >= 0.5, EV spread > {V_EV_SPREAD}R). C4 skipped.")
    out = repo / args.out
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
