# -*- coding: utf-8 -*-
"""STOCKS AVSL D1 (calendar-matched AVSL 12/58) -- valid transfer
test A (prereg PREREG_STOCKS_AVSL_D1.md, frozen fc6b3aa).  One shot.

Config-mapping (prereg table): 12/58/67/83/83/ANN 252 -- calendar
equivalence to crypto-4H 70/345/400/500.  Grid starts 2001-01-02
(regime-homogeneous); universe = 12 mega-caps (survivorship bias
declared).  Battery v2 gates.  Primary volume input = dollar volume;
vol=ones control printed, verdict from the primary run only.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.battery_v2 import (
    asset_matrix,
    concurrency,
    enb,
    ortho_ev,
    xs_bootstrap_ci,
)
from engine.passed.avsl_cross_s1 import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from engine.passed.avsl_cross_s1 import sma_ind
from experiments.stocks.avsl_d1_screen import TICKERS, _load, fetch

# ---- frozen config (PREREG_STOCKS_AVSL_D1.md) -----------------------------
FAST, SLOW, STAND_DIV = 12, 58, 2.0
WARMUP = 67
K_STOP = 2.0
HORIZON = 83
TAKER_FEE = 0.0005
ANN = 252
NW_LAGS = 83
BLOCK = 83
BOOT_B = 1000
SEED = 11
SPLIT_FRAC = 2 / 3
GRID_START = dt.date(2001, 1, 2)
F_BARS = 30
G1_SHARPE_MIN = 1.0
G2_DD_MAX = 0.25
G3_EV_MIN = 0.10
G4_ASSETS_MIN = 8
ENB_MIN = 2.0
CONC_P95_MAX = 6.0
CONC_P50_MAX = 4.0


def fast_line_p(lp: np.ndarray, cp: np.ndarray, vol: np.ndarray) -> np.ndarray:
    """AVSL(FAST, SLOW) with prereg parameters (calendar-matched)."""
    vpc, vpr, _vm, vpci, dev = _avs_base(
        cp, vol, FAST, SLOW, STAND_DIV, False)
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(lp, vpr, len_v, vpcc)
    adjusted = lp - price_v + dev
    return np.asarray(
        sma_ind(adjusted, SLOW, use_talib=False, nan_policy="ffill"),
        dtype=np.float64)


def trade_st(env: dict, t: int, is_long: bool) -> dict | None:
    """Reverse-cross trade with THIS prereg's constants (fee 5bp,
    HORIZON 83).  Exit semantics of the promoted module."""
    hp, lp, cp = env["hp"], env["lp"], env["cp"]
    line, atr = env["line"], env["atr"]
    risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    n = len(cp)
    dirs = env["up"][env["cross_idx"] - 1]
    bars = env["cross_idx"][dirs == (not is_long)]
    nxt = bars[bars > t]
    k_exit = int(min(nxt[0], t + HORIZON)) if nxt.size else -1
    if k_exit < 0:
        k_exit = n - 1
    pnl, hit, e1 = 0.0, False, k_exit
    for k in range(t + 1, min(k_exit + 1, n)):
        if is_long:
            if lp[k] <= stop:
                pnl, hit, e1 = -1.0, True, k
                break
        elif hp[k] >= stop:
            pnl, hit, e1 = -1.0, True, k
            break
    if not hit:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {"net": pnl - fee_r, "e0": t, "e1": e1, "long": is_long,
            "fbar": int(env["b"][t]),
            "reason": "mtm" if not hit else "stop"}


def collect(repo, use_volume: bool):
    raws = {t: _load(t, repo) for t in TICKERS}
    dates = sorted({d for dts, _ in raws.values() for d in dts
                    if d >= GRID_START})
    pos_of = {d: i for i, d in enumerate(dates)}
    n_g = len(dates)
    ctxs, trades = {}, []
    for tkr in TICKERS:
        dts, arr = raws[tkr]
        keep = [i for i, d in enumerate(dts) if d >= GRID_START]
        if len(keep) < WARMUP + HORIZON:
            continue
        hp, lp, cp = arr["High"][keep], arr["Low"][keep], arr["Close"][keep]
        vol = arr["DVOL"][keep] if use_volume else np.ones_like(cp)
        line = fast_line_p(lp, cp, vol)
        atr = atr_of(hp, lp, cp)
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        cross_idx = np.nonzero(up | dn)[0] + 1
        b = np.array([pos_of[d] for d in dts if d >= GRID_START])
        g0 = int(b[0])
        env = {"hp": hp, "lp": lp, "cp": cp, "line": line, "atr": atr,
               "up": up, "dn": dn, "cross_idx": cross_idx, "b": b,
               "g0": g0, "n_bars": len(cp)}
        ctxs[tkr] = {"g0": g0, "n_bars": len(cp),
                     "sizes": fx_s1_sizes_ann(cp)}
        for t, is_long in zip(cross_idx, up[cross_idx - 1]):
            if t < WARMUP:
                continue
            tr = trade_st(env, int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = tkr
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    return ctxs, trades, dates, n_g


def atr_of(hp, lp, cp):
    from ta.src.volatility.atr import atr_ind
    return np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))


def fx_s1_sizes_ann(cp: np.ndarray) -> np.ndarray:
    """S1 vol-target sizing at ANN 252 (same formula, prereg ANN)."""
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - 100):i]) * np.sqrt(ANN)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(0.20 / r, 0.25, 2.0))
    return sizes


def factor_by_bar(repo, dates, pos_of):
    import polars as pl
    fp = repo / "data" / "yf" / "st_SPY_1D.parquet"
    if not fp.exists():
        import yfinance as yf
        import polars as pl
        df = yf.download("SPY", period="max", interval="1d",
                         progress=False, auto_adjust=True)
        df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        pl.from_pandas(df.reset_index()).write_parquet(fp)
    df = pl.read_parquet(fp)
    dcol = df.columns[0]
    dts = [x.date() if hasattr(x, "date") else x
           for x in df[dcol].to_list()]
    cp = np.asarray(df["Close"], dtype=float)
    out = {}
    for i in range(F_BARS, len(cp)):
        g = pos_of.get(dts[i])
        if g is not None:
            m = cp[i] / cp[i - F_BARS] - 1.0
            if np.isfinite(m):
                out[g] = float(m)
    return out


def _stream_leg(trades, ctxs, g0g, lo, hi):
    s = np.zeros(hi - lo)
    for tr in trades:
        e0 = tr["e0"] + ctxs[tr["sym"]]["g0"] - g0g
        e1 = min(tr["e1"] + ctxs[tr["sym"]]["g0"] - g0g, hi - 1)
        a, b = max(e0, lo), min(e1 + 1, hi)
        if b <= a:
            continue
        hold = max(e1 - e0, 1)
        s[a - lo:b - lo] += (ctxs[tr["sym"]]["sizes"][tr["e0"]]
                             * tr["net"] / (hold + 1))
    return s


def evaluate(repo, use_volume: bool = True) -> dict:
    """One-shot frozen v1+v2 battery on the calendar-matched config."""
    ctxs, trades, dates, n_g = collect(repo, use_volume)
    pos_of = {d: i for i, d in enumerate(dates)}
    f_by_bar = factor_by_bar(repo, dates, pos_of)
    g0g = min(c["g0"] for c in ctxs.values())
    n_full = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_full * SPLIT_FRAC)
    X = asset_matrix(ctxs, trades, g0g, n_full, TICKERS)
    n_open = concurrency(trades, ctxs, g0g, n_full)
    stream = X.sum(axis=1)
    out = {"n_g": n_full, "split": split, "n_trades": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_full)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        sv = stream[lo:hi]
        nets = np.array([t["net"] for t in seg_tr])
        pos = sum(1 for t_ in TICKERS
                  if (v := [x["net"] for x in seg_tr if x["sym"] == t_])
                  and float(np.mean(v)) > 0)
        oc = n_open[lo:hi]
        conc = oc[oc > 0]
        eff_n = (float(nets.sum() ** 2 / (nets ** 2).sum())
                 if nets.sum() != 0 else float("nan"))
        m = {"n": len(seg_tr),
             "sharpe_nw": nw_sharpe(sv, lags=NW_LAGS, ann=ANN),
             "plain_ann": float(sv.mean() / sv.std() * np.sqrt(ANN)),
             "dd": portfolio_dd(sv),
             "net_ev": float(nets.mean()) if len(nets) else float("nan"),
             "eff_n": eff_n, "pos_assets": pos,
             "ci_time": block_bootstrap_ci(sv, b=BOOT_B, block=BLOCK),
             "ci_xs": xs_bootstrap_ci(X[lo:hi]),
             "enb": enb(X[lo:hi]),
             "conc_p50": float(np.percentile(conc, 50)) if conc.size else 0.0,
             "conc_p95": float(np.percentile(conc, 95)) if conc.size else 0.0,
             "conc_max": float(conc.max()) if conc.size else 0.0,
             "legs": {}}
        for leg, keep in (("long", lambda t: t["long"]),
                          ("short", lambda t: not t["long"])):
            lt = [t for t in seg_tr if keep(t)]
            if not lt:
                continue
            lr = np.array([t["net"] for t in lt])
            srt = np.sort(lr)[::-1]
            eo, tt = ortho_ev(lt, f_by_bar)
            years = {}
            for t in lt:
                y = dates[t["e0"] + ctxs[t["sym"]]["g0"] - g0g].year
                years.setdefault(y, []).append(t["net"])
            m["legs"][leg] = {
                "n": len(lr), "ev": float(lr.mean()),
                "dd": portfolio_dd(_stream_leg(lt, ctxs, g0g, lo, hi)),
                "avg_hold": float(np.mean([t["e1"] - t["e0"] for t in lt])),
                "ex_top20_ev": float(srt[20:].mean())
                if len(srt) > 20 else float("nan"),
                "top20_share": float(srt[:20].sum() / lr.sum())
                if lr.sum() != 0 else float("nan"),
                "ev_orth": eo, "t_orth": tt,
                "neg_years": sum(1 for y in years.values()
                                 if float(np.mean(y)) < 0),
                "n_years": len(years)}
        g1 = (m["sharpe_nw"] >= G1_SHARPE_MIN and m["dd"] <= G2_DD_MAX
              and m["net_ev"] >= G3_EV_MIN
              and m["pos_assets"] >= G4_ASSETS_MIN
              and m["ci_time"][0] > 0)
        g2 = (m["enb"] >= ENB_MIN and m["conc_p95"] <= CONC_P95_MAX
              and m["conc_p50"] <= CONC_P50_MAX)
        out[seg] = m
        out[seg]["gates_v1"], out[seg]["gates_v2"] = bool(g1), bool(g2)
    ok1 = all(out[s]["gates_v1"] for s in ("PRIMARY", "F3"))
    ok2 = all(out[s]["gates_v2"] for s in ("PRIMARY", "F3"))
    out["verdict"] = ("PASS" if ok1 and ok2
                      else ("FAIL-CORR" if ok1 else "FAIL"))
    return out


def report(out: dict, label: str) -> None:
    print(f"== {label} == trades {out['n_trades']}, grid {out['n_g']}, "
          f"split {out['split']}")
    for seg in ("PRIMARY", "F3"):
        m = out[seg]
        print(f"{seg:>7}: Sharpe_NW {m['sharpe_nw']:+.2f} "
              f"(plain {m['plain_ann']:+.2f}) DD {m['dd']:.0%} "
              f"EV {m['net_ev']:+.2f}R eff_n {m['eff_n']:.0f} "
              f"pos {m['pos_assets']}/{len(TICKERS)} "
              f"CI_time [{m['ci_time'][0]:+.5f},{m['ci_time'][1]:+.5f}]")
        print(f"        CI_xs [{m['ci_xs'][0]:+.5f},{m['ci_xs'][1]:+.5f}] "
              f"| ENB {m['enb']:.2f} conc p50/p95/max "
              f"{m['conc_p50']:.0f}/{m['conc_p95']:.0f}/{m['conc_max']:.0f} "
              f"| v1 {'PASS' if m['gates_v1'] else 'FAIL'} "
              f"v2 {'PASS' if m['gates_v2'] else 'FAIL'}")
        for leg, lm in m["legs"].items():
            print(f"      {leg:>5}: n={lm['n']} EV {lm['ev']:+.2f}R "
                  f"DD {lm['dd']:.0%} hold {lm['avg_hold']:.0f} "
                  f"ex20 {lm['ex_top20_ev']:+.2f}R "
                  f"({lm['top20_share']:.0%}) "
                  f"EV_orth {lm['ev_orth']:+.3f}R t {lm['t_orth']:+.1f} "
                  f"neg_years {lm['neg_years']}/{lm['n_years']}")
    print(f"VERDICT: {out['verdict']}")


if __name__ == "__main__":
    repo = repo_root()
    fetch(repo)
    report(evaluate(repo, True),
           "STOCKS AVSL(12,58) D1 dollar-volume [PRIMARY RUN]")
    report(evaluate(repo, False),
           "STOCKS AVSL(12,58) D1 vol=ones [control read-out]")
