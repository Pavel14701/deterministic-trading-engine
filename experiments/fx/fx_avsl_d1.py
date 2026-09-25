# -*- coding: utf-8 -*-
"""FX AVSL D1 -- first family on battery v2 (prereg
PREREG_FX_AVSL_D1.md, frozen 3dd0b1c).  One-shot run.

Engine port of the promoted AVSL geometry to FX daily:
entry close x fast_line(70,345) cross, exit first opposite cross,
stop max(|close-line|, 2*ATR14), S1 vol-target sizing.
1D constants (HORIZON 100, ANN 365, fee 0.5bp/side, NW/block 100)
are declared in the prereg; changing any of them closes the family.

Factor for R5 ortho-EV: DXY 30d momentum (declared substitution of
the crypto BTC-30d factor).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl

from engine.battery_v2 import (
    asset_matrix,
    concurrency,
    enb,
    ortho_ev,
    xs_bootstrap_ci,
)
from engine.passed.avsl_cross_s1 import (
    block_bootstrap_ci,
    fast_line,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from ta.src.volatility.atr import atr_ind

# ---- frozen config (PREREG_FX_AVSL_D1.md) ---------------------------------
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
         "NZDUSD", "EURJPY", "GBPJPY", "EURGBP")
FAST, SLOW, STAND_DIV = 70, 345, 2.0
WARMUP = 400
K_STOP = 2.0
HORIZON = 100
TAKER_FEE = 0.00005
VOL_WIN, VOL_TARGET, SIZE_MIN, SIZE_MAX = 100, 0.20, 0.25, 2.0
ANN_D1 = 365
RISK_PCT = 0.01
SPLIT_FRAC = 2 / 3
NW_LAGS = 100
BLOCK = 100
BOOT_B = 1000
SEED = 11
G1_SHARPE_MIN = 1.0
G2_DD_MAX = 0.25
G3_EV_MIN = 0.10
G4_ASSETS_MIN = 7
ENB_MIN = 2.0
CONC_P95_MAX = 6.0
CONC_P50_MAX = 4.0
F_BARS = 30          # DXY 30d momentum (frozen factor)


def fetch_all(repo=None) -> None:
    """One-time yfinance download into data/yf/fx_*_1D.parquet."""
    import yfinance as yf
    repo = repo or repo_root()
    out = repo / "data" / "yf"
    out.mkdir(parents=True, exist_ok=True)
    for tkr in (*PAIRS, "DXY"):
        fp = out / f"fx_{tkr}_1D.parquet"
        if fp.exists():
            continue
        sym = {"DXY": "DX-Y.NYB"}.get(tkr, f"{tkr}=X")
        df = yf.download(sym, period="max", interval="1d",
                         progress=False, auto_adjust=False)
        df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])[
            ["Open", "High", "Low", "Close"]]
        pl.from_pandas(df.reset_index()).write_parquet(fp)
        print(f"fetched {tkr}: {len(df)} rows "
              f"{df.index.min().date()} -> {df.index.max().date()}")


def _load(tkr: str, repo) -> tuple:
    """(dates list, {col: np.array}) straight from polars."""
    df = pl.read_parquet(repo / "data" / "yf" / f"fx_{tkr}_1D.parquet")
    dcol = df.columns[0]
    dts = [x.date() if hasattr(x, "date") else x
           for x in df[dcol].to_list()]
    return dts, {c: np.asarray(df[c], dtype=float)
                 for c in ("Open", "High", "Low", "Close")}


def fx_s1_sizes(cp: np.ndarray) -> np.ndarray:
    """S1 vol-target sizing at ANN 365 (same formula as passed S1)."""
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - VOL_WIN):i]) * np.sqrt(ANN_D1)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(VOL_TARGET / r, SIZE_MIN, SIZE_MAX))
    return sizes


def trade_fx(env: dict, t: int, is_long: bool) -> dict | None:
    """Reverse-cross trade, exit semantics of the promoted module
    (opposite cross at close; stop wins intrabar; MTM at HORIZON)."""
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
            "fbar": int(env["b"][t]), "reason": "mtm" if not hit else "stop"}


def collect_all(pairs: tuple = PAIRS, repo=None,
                fetch: bool = False) -> tuple:
    """Envs + true-grid contexts + all reverse-cross trades on the
    global union calendar."""
    repo = repo or repo_root()
    if fetch:
        fetch_all(repo)
    raws = {p: _load(p, repo) for p in pairs}
    dates = sorted({d for dts, _ in raws.values() for d in dts})
    pos_of = {d: i for i, d in enumerate(dates)}
    n_g = len(dates)
    envs, ctxs, trades = {}, {}, []
    for p in pairs:
        dts, arr = raws[p]
        hp, lp, cp = arr["High"], arr["Low"], arr["Close"]
        line = np.asarray(fast_line(lp, cp, np.ones_like(cp)))
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        cross_idx = np.nonzero(up | dn)[0] + 1
        b = np.array([pos_of[d] for d in dts])
        g0 = int(b[0])
        envs[p] = {"hp": hp, "lp": lp, "cp": cp, "line": line,
                   "atr": atr, "up": up, "dn": dn,
                   "cross_idx": cross_idx, "b": b, "g0": g0,
                   "n_bars": len(cp)}
        ctxs[p] = {"g0": g0, "n_bars": len(cp),
                   "sizes": fx_s1_sizes(cp)}
        for t, is_long in zip(cross_idx, up[cross_idx - 1]):
            if t < WARMUP:
                continue
            tr = trade_fx(envs[p], int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = p
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    # R5 factor: DXY 30d momentum mapped onto the global grid
    dxy_dts, dxy_arr = _load("DXY", repo)
    dxy_cp = dxy_arr["Close"]
    f_by_bar = {}
    for i in range(F_BARS, len(dxy_cp)):
        m = dxy_cp[i] / dxy_cp[i - F_BARS] - 1.0
        g = pos_of.get(dxy_dts[i])
        if g is not None and np.isfinite(m):
            f_by_bar[g] = float(m)
    return envs, ctxs, trades, dates, f_by_bar


def _stream_leg(trades: list, ctxs: dict, g0g: int, lo: int,
                hi: int) -> np.ndarray:
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


def evaluate(pairs: tuple = PAIRS, repo=None) -> dict:
    """Frozen v1+v2 gate metrics on the FX daily grid.  One shot."""
    envs, ctxs, trades, dates, f_by_bar = collect_all(pairs, repo)
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    X = asset_matrix(ctxs, trades, g0g, n_g, pairs)
    n_open = concurrency(trades, ctxs, g0g, n_g)
    stream = X.sum(axis=1)
    out = {"n_g": n_g, "split": split, "n_trades": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        sv = stream[lo:hi]
        nets = np.array([t["net"] for t in seg_tr])
        pos = sum(1 for p in pairs
                  if (v := [t["net"] for t in seg_tr if t["sym"] == p])
                  and float(np.mean(v)) > 0)
        oc = n_open[lo:hi]
        conc = oc[oc > 0]
        eff_n = (float(nets.sum() ** 2 / (nets ** 2).sum())
                 if nets.sum() != 0 else float("nan"))
        m = {"n": len(seg_tr),
             "sharpe_nw": nw_sharpe(sv, lags=NW_LAGS, ann=ANN_D1),
             "plain_ann": float(sv.mean() / sv.std() * np.sqrt(ANN_D1)),
             "dd": portfolio_dd(sv),
             "net_ev": float(nets.mean()) if len(nets) else float("nan"),
             "eff_n": eff_n,
             "pos_assets": pos,
             "ci_time": block_bootstrap_ci(sv, b=BOOT_B, block=BLOCK),
             "ci_xs": xs_bootstrap_ci(X[lo:hi]),
             "enb": enb(X[lo:hi]),
             "conc_p50": float(np.percentile(conc, 50))
             if conc.size else 0.0,
             "conc_p95": float(np.percentile(conc, 95))
             if conc.size else 0.0,
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


def report(out: dict) -> None:
    print(f"== FX AVSL D1 (battery v2) == trades {out['n_trades']}, "
          f"grid {out['n_g']}, split {out['split']}")
    for seg in ("PRIMARY", "F3"):
        m = out[seg]
        print(f"{seg:>7}: Sharpe_NW {m['sharpe_nw']:+.2f} "
              f"(plain {m['plain_ann']:+.2f}) DD {m['dd']:.0%} "
              f"EV {m['net_ev']:+.2f}R eff_n {m['eff_n']:.0f} "
              f"pos {m['pos_assets']}/10 "
              f"CI_time [{m['ci_time'][0]:+.5f},{m['ci_time'][1]:+.5f}]")
        print(f"        CI_xs [{m['ci_xs'][0]:+.5f},{m['ci_xs'][1]:+.5f}] "
              f"| ENB {m['enb']:.2f} conc p50/p95/max "
              f"{m['conc_p50']:.0f}/{m['conc_p95']:.0f}"
              f"/{m['conc_max']:.0f} "
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
    report(evaluate())


