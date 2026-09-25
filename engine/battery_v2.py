# -*- coding: utf-8 -*-
"""Battery v2 -- cross-sectional honesty patch (prereg
PREREG_BATTERY_V2.md, frozen 2026-09-25).  ADDITIVE: wraps the
frozen v1 battery (engine.passed.avsl_cross_s1) with cross-
sectional measurement.  Imports from passed modules only.

Verdict semantics:
  FAIL      -- v1 gates fail (family closed).
  FAIL-CORR -- v1 passes but G-ENB or G-CONC fails: signal not
               distinguishable from beta on this universe;
               closes the universe, not the hypothesis.
  PASS      -- candidate for promotion.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from engine.passed.avsl_trailing_s1 import SPLIT_FRAC, build_env

BLOCK = 500
BOOT_B = 1000
SEED = 11
ENB_MIN = 2.0
CONC_P95_MAX = 6.0
F_BARS = 180          # 30 days of 4H bars (frozen factor)


def asset_matrix(ctxs: dict, trades: list, g0g: int, n_g: int,
                 assets: tuple) -> np.ndarray:
    """Aligned asset x bar matrix of per-bar sized accrual returns."""
    idx = {s: i for i, s in enumerate(assets)}
    X = np.zeros((n_g, len(assets)))
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = min(tr["e1"] + c["g0"] - g0g, n_g - 1)
        hold = max(e1 - e0, 1)
        X[e0:e1 + 1, idx[tr["sym"]]] += (
            c["sizes"][tr["e0"]] * tr["net"] / (hold + 1))
    return X


def enb(X: np.ndarray) -> float:
    """ENB on ACTIVE bars only (calibration adjustment 1-of-1,
    STATUS 2026-09-25): the full-bar matrix is ~75-95% zero rows,
    which attenuates correlation toward zero and inflates ENB
    toward the asset count regardless of bet structure."""
    X = X[X.sum(axis=1) != 0]
    if X.shape[0] < 100:
        return float("nan")
    sd = X.std(axis=0)
    cols = X[:, sd > 0]
    if cols.shape[1] < 2:
        return float("nan")
    C = np.corrcoef(cols, rowvar=False)
    lam = np.linalg.eigvalsh(C)
    lam = np.clip(lam, 0.0, None)
    s1, s2 = lam.sum(), (lam ** 2).sum()
    return float(s1 ** 2 / s2) if s2 > 0 else float("nan")


def concurrency(trades: list, ctxs: dict, g0g: int, n_g: int):
    n_open = np.zeros(n_g)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = max(tr["e0"] + c["g0"] - g0g, 0)
        e1 = min(tr["e1"] + c["g0"] - g0g, n_g - 1)
        n_open[e0:e1 + 1] += 1
    return n_open


def xs_bootstrap_ci(X: np.ndarray) -> tuple:
    """Cross-sectional block bootstrap: bar blocks move ALL assets
    together (preserves contemporaneous correlation)."""
    n = X.shape[0]
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLOCK))
    means = np.empty(BOOT_B)
    for i in range(BOOT_B):
        starts = rng.integers(0, n, nb)
        idx = np.concatenate(
            [(np.arange(s, s + BLOCK) % n) for s in starts])[:n]
        means[i] = X[idx].sum(axis=1).mean()
    return (float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)))


def ortho_ev(trades: list, f_by_bar: dict) -> tuple:
    """Residual EV after OLS on the factor; (EV_orth, t_stat)."""
    pairs = [(t["net"], f_by_bar[t["fbar"]]) for t in trades
             if t["fbar"] in f_by_bar]
    if len(pairs) < 50:
        return float("nan"), float("nan")
    net = np.array([p[0] for p in pairs])
    f = np.array([p[1] for p in pairs])
    beta = float(np.cov(net, f)[0, 1] / np.var(f))
    res = net - beta * f
    t = float(res.mean() / res.std() * np.sqrt(len(res)))
    return float(res.mean()), t


def evaluate_v2(collect, symbols: tuple = ASSETS, repo=None,
                label: str = "") -> dict:
    """collect(symbols, repo) -> (ctxs, trades) on the TRUE grid
    (trades tagged sym/long/net/e0/e1, optional 'reason'; e0
    relative to the ASSET grid, e1 as asset bar index)."""
    repo = repo or repo_root()
    ctxs, trades = collect(symbols, repo)
    assets = tuple(sorted(ctxs))
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    X = asset_matrix(ctxs, trades, g0g, n_g, assets)
    stream = X.sum(axis=1)

    # frozen factor: BTC 30-day trailing return by global bar
    btc = build_env("BTC", repo)
    btc_cp = btc["cp"]
    fbtc = np.full(n_g, np.nan)
    for gi in range(F_BARS, n_g):
        b = g0g + gi
        j = b - btc["g0"]
        if 0 <= j - F_BARS < len(btc_cp):
            fbtc[gi] = float(np.log(btc_cp[j] / btc_cp[j - F_BARS]))
    f_by_bar = {gi: fbtc[gi] for gi in range(n_g)
                if np.isfinite(fbtc[gi])}

    # regime balance: fraction of bars with BTC below 1D SMA200
    day = (btc["b"]) // 6
    bnd = np.nonzero(np.diff(day))[0] + 1
    dnum, dclose = day[bnd - 1], btc["cp"][bnd - 1]
    csum = np.cumsum(np.insert(dclose, 0, 0.0))
    sma = np.full(len(dclose), np.nan)
    sma[199:] = (csum[200:] - csum[:-200]) / 200.0
    pos = np.searchsorted(dnum, (g0g + np.arange(n_g)) // 6) - 1
    below = np.zeros(n_g, dtype=bool)
    okp = pos >= 199
    below[okp] = dclose[pos[okp]] < sma[pos[okp]]

    for t in trades:
        t["fbar"] = t["e0"] + ctxs[t["sym"]]["g0"] - g0g
    n_open = concurrency(trades, ctxs, g0g, n_g)
    out: dict = {"label": label, "n_g": n_g, "split": split,
                 "n_trades": len(trades)}
    gates_v1 = True
    gates_v2 = True
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in seg_tr])
        pos_a = sum(1 for sym in assets
                    if [t["net"] for t in seg_tr if t["sym"] == sym]
                    and np.mean([t["net"] for t in seg_tr
                                 if t["sym"] == sym]) > 0)
        v = stream[lo:hi]
        ci1 = block_bootstrap_ci(v)
        ci2 = xs_bootstrap_ci(X[lo:hi])
        e = enb(X[lo:hi])
        nc = n_open[lo:hi]
        p95 = float(np.percentile(nc, 95))
        g1 = (nw_sharpe(v) >= 1.0 and portfolio_dd(v) <= 0.25
              and float(r.mean()) >= 0.10 and pos_a >= 7
              and ci1[0] > 0)
        g2 = e >= ENB_MIN and p95 <= CONC_P95_MAX
        gates_v1 &= g1
        gates_v2 &= g2
        out[seg] = {
            "n": len(seg_tr), "sharpe_nw": nw_sharpe(v),
            "dd": portfolio_dd(v), "net_ev": float(r.mean()),
            "pos_assets": pos_a, "ci_time": ci1, "ci_xs": ci2,
            "enb": e, "conc_p50": float(np.percentile(nc, 50)),
            "conc_p95": p95, "conc_max": float(nc.max()),
            "pct_bars_ge5": float(np.mean(nc >= 5)),
            "btc_below_sma200": float(np.mean(below[lo:hi])),
            "gates_v1": g1, "gates_v2_leg": g2,
            "legs": {}, }
        for leg, keep in (("long", lambda t: t["long"]),
                          ("short", lambda t: not t["long"])):
            lt = [t for t in seg_tr if keep(t)]
            if not lt:
                continue
            lr = np.array([t["net"] for t in lt])
            lrd = np.sort(lr)[::-1]
            hold = np.mean([t["e1"] - t["e0"] for t in lt])
            eo, tt = ortho_ev(lt, f_by_bar)
            reasons = {rr: (sum(1 for t in lt if t.get("reason") == rr),
                            float(np.sum([t["net"] for t in lt
                                          if t.get("reason") == rr])))
                       for rr in set(t.get("reason") for t in lt)
                       if rr is not None}
            out[seg]["legs"][leg] = {
                "n": len(lr), "ev": float(lr.mean()),
                "dd": portfolio_dd(stream_leg(lt, ctxs, g0g, lo, hi)),
                "avg_hold": float(hold),
                "ex_top20_ev": float(lrd[20:].mean())
                if len(lrd) > 20 else float("nan"),
                "top20_share": float(lrd[:20].sum() / lr.sum())
                if lr.sum() != 0 else float("nan"),
                "ev_orth": eo, "t_orth": tt, "reasons": reasons}
    out["gates_pass_v1"] = bool(gates_v1)
    out["gates_pass_v2"] = bool(gates_v1 and gates_v2)
    out["verdict"] = ("PASS" if out["gates_pass_v2"] else
                      ("FAIL-CORR" if gates_v1 else "FAIL"))
    return out


def stream_leg(trades: list, ctxs: dict, g0g: int, lo: int,
               hi: int) -> np.ndarray:
    s = np.zeros(hi - lo)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = min(tr["e1"] + c["g0"] - g0g, hi - 1)
        a, b = max(e0, lo), min(e1 + 1, hi)
        if b <= a:
            continue
        hold = max(e1 - e0, 1)
        s[a - lo:b - lo] += (c["sizes"][tr["e0"]] * tr["net"]
                             / (hold + 1))
    return s


def report(out: dict) -> None:
    print(f"== battery v2: {out['label']} == trades {out['n_trades']}, "
          f"grid {out['n_g']}, split {out['split']}")
    for seg in ("PRIMARY", "F3"):
        m = out[seg]
        print(f"{seg:>7}: v1 Sharpe {m['sharpe_nw']:+.2f} DD {m['dd']:.0%} "
              f"EV {m['net_ev']:+.2f}R pos {m['pos_assets']}/10 "
              f"CI_time [{m['ci_time'][0]:+.5f},{m['ci_time'][1]:+.5f}] "
              f"| ENB {m['enb']:.2f} conc p50/p95/max "
              f"{m['conc_p50']:.0f}/{m['conc_p95']:.0f}/{m['conc_max']:.0f} "
              f"(%bars>=5 {m['pct_bars_ge5']:.0%}) | "
              f"CI_xs [{m['ci_xs'][0]:+.5f},{m['ci_xs'][1]:+.5f}] | "
              f"BTC<SMA200 {m['btc_below_sma200']:.0%} "
              f"| v1 {'PASS' if m['gates_v1'] else 'FAIL'}")
        for leg, lm in m["legs"].items():
            rr = " ".join(f"{k}:{v[0]}({v[1]:+.0f}R)"
                          for k, v in lm["reasons"].items()) or "n/a"
            print(f"      {leg:>5}: n={lm['n']} EV {lm['ev']:+.2f}R "
                  f"DD {lm['dd']:.0%} hold {lm['avg_hold']:.0f} "
                  f"ex20 {lm['ex_top20_ev']:+.2f}R "
                  f"({lm['top20_share']:.0%}) "
                  f"EV_orth {lm['ev_orth']:+.3f}R t {lm['t_orth']:+.1f} "
                  f"| {rr}")
    print(f"VERDICT: {out['verdict']}")


if __name__ == "__main__":
    from engine.passed.avsl_trailing_s1 import collect_all
    report(evaluate_v2(collect_all, label="avsl_trailing_s1"))
