# -*- coding: utf-8 -*-
"""EXPLORATORY screen: AVSL-revcross D1 engine on liquid US stocks.

NOT a prereg family run: no gates, no verdict, no promotion path
(any promotion requires a NEW frozen prereg).  Purpose: see how the
engine behaves on equities and measure the volume quirks.

Declared quirks / disclaimers:
  - survivorship bias: universe = today's mega-caps -> upward bias;
  - yf volume is raw shares: a 2:1 split halves prices and doubles
    volume -> fake volume jump.  Mitigation: dollar volume
    (close x volume); ALSO run vol=ones as control;
  - auto_adjust=True prices (split+div adjusted, total-return-ish);
  - zero volume rows in old data clamped to 1;
  - mixed listing dates; per-asset segments start at their own data.

Engine: experiments/fx/fx_avsl_d1 (trade_fx, fx_s1_sizes) reused
as-is; constants HORIZON 100, ANN 365, fee 0.5bp/side (equity
spread+impact is higher -- disclosed, not tuned).
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import (
    block_bootstrap_ci,
    fast_line,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from experiments.fx.avsl_d1.fx_avsl_d1 import (
    ANN_D1,
    NW_LAGS,
    SPLIT_FRAC,
    WARMUP,
    fx_s1_sizes,
    trade_fx,
)
from ta.src.volatility.atr import atr_ind

TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
           "JPM", "XOM", "JNJ", "WMT", "PG")
SPLIT = SPLIT_FRAC
BOOT_B, BLOCK, SEED = 1000, 100, 11


def fetch(repo=None) -> None:
    import pandas as pd
    import polars as pl
    import yfinance as yf
    out = repo / "data" / "yf"
    out.mkdir(parents=True, exist_ok=True)
    for tkr in TICKERS:
        fp = out / f"st_{tkr}_1D.parquet"
        if fp.exists():
            continue
        df = yf.download(tkr, period="max", interval="1d",
                         progress=False, auto_adjust=True)
        df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        vol = np.maximum(df["Volume"].to_numpy(float), 1.0)
        d = df[["High", "Low", "Close"]].copy()
        d["DVOL"] = df["Close"].to_numpy(float) * vol
        pl.from_pandas(d.reset_index()).write_parquet(fp)
        print(f"fetched {tkr}: {len(df)} rows "
              f"{df.index.min().date()} -> {df.index.max().date()}")


def _load(tkr: str, repo) -> tuple:
    import polars as pl
    df = pl.read_parquet(repo / "data" / "yf" / f"st_{tkr}_1D.parquet")
    dcol = df.columns[0]
    dts = [x.date() if hasattr(x, "date") else x
           for x in df[dcol].to_list()]
    return dts, {c: np.asarray(df[c], dtype=float)
                 for c in ("High", "Low", "Close", "DVOL")}


def collect(repo, use_volume: bool):
    raws = {t: _load(t, repo) for t in TICKERS}
    dates = sorted({d for dts, _ in raws.values() for d in dts})
    pos_of = {d: i for i, d in enumerate(dates)}
    n_g = len(dates)
    envs, ctxs, trades = {}, {}, []
    for tkr in TICKERS:
        dts, arr = raws[tkr]
        hp, lp, cp = arr["High"], arr["Low"], arr["Close"]
        vol = arr["DVOL"] if use_volume else np.ones_like(cp)
        line = np.asarray(fast_line(lp, cp, vol))
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        cross_idx = np.nonzero(up | dn)[0] + 1
        b = np.array([pos_of[d] for d in dts])
        g0 = int(b[0])
        envs[tkr] = {"hp": hp, "lp": lp, "cp": cp, "line": line,
                     "atr": atr, "up": up, "dn": dn,
                     "cross_idx": cross_idx, "b": b, "g0": g0,
                     "n_bars": len(cp)}
        ctxs[tkr] = {"g0": g0, "n_bars": len(cp),
                     "sizes": fx_s1_sizes(cp)}
        for t, is_long in zip(cross_idx, up[cross_idx - 1]):
            if t < WARMUP:
                continue
            tr = trade_fx(envs[tkr], int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = tkr
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    return ctxs, trades, dates, n_g


def run(label: str, repo, use_volume: bool) -> None:
    ctxs, trades, dates, n_g = collect(repo, use_volume)
    g0g = min(c["g0"] for c in ctxs.values())
    split = int(n_g * SPLIT)
    s = np.zeros(n_g)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = min(tr["e1"] + c["g0"] - g0g, n_g - 1)
        hold = max(e1 - e0, 1)
        s[e0:e1 + 1] += c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
    print(f"\n==== {label} ==== trades {len(trades)}, grid {n_g}, "
          f"split {split}")
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        sv = s[lo:hi]
        nets = np.array([t["net"] for t in seg_tr])
        pos = sum(1 for t_ in TICKERS
                  if (v := [x["net"] for x in seg_tr if x["sym"] == t_])
                  and float(np.mean(v)) > 0)
        ci = block_bootstrap_ci(sv, b=BOOT_B, block=BLOCK)
        print(f"{seg:>7}: n={len(seg_tr)} "
              f"Sharpe_NW {nw_sharpe(sv, lags=NW_LAGS, ann=ANN_D1):+.2f} "
              f"plain {sv.mean()/sv.std()*np.sqrt(ANN_D1):+.2f} "
              f"DD {portfolio_dd(sv):.0%} EV {nets.mean():+.2f}R "
              f"pos {pos}/{len(TICKERS)} "
              f"CI [{ci[0]:+.5f},{ci[1]:+.5f}]")
        for leg, keep in (("long", lambda t: t["long"]),
                          ("short", lambda t: not t["long"])):
            lt = [t for t in seg_tr if keep(t)]
            if not lt:
                continue
            lr = np.array([t["net"] for t in lt])
            srt = np.sort(lr)[::-1]
            years = {}
            for t in lt:
                y = dates[t["e0"] + ctxs[t["sym"]]["g0"] - g0g].year
                years.setdefault(y, []).append(t["net"])
            negy = sum(1 for yy in years.values() if np.mean(yy) < 0)
            print(f"      {leg:>5}: n={len(lr)} EV {lr.mean():+.2f}R "
                  f"ex20 {srt[20:].mean():+.2f}R "
                  f"top20share {srt[:20].sum()/lr.sum():.0%} "
                  f"neg_years {negy}/{len(years)}")
    yrs = {}
    for tr in trades:
        y = dates[tr["e0"] + ctxs[tr["sym"]]["g0"] - g0g].year
        yrs.setdefault(y, []).append(tr["net"])
    row = " ".join(f"{y}:{np.mean(v):+.2f}" for y, v in sorted(yrs.items())
                   if len(v) >= 5)
    print("  per-year EV:", row)


if __name__ == "__main__":
    repo = repo_root()
    fetch(repo)
    run("STOCKS dollar-volume", repo, True)
    run("STOCKS vol=ones control", repo, False)

