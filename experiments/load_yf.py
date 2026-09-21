# -*- coding: utf-8 -*-
"""Load crypto OHLCV from yfinance into the okx21 parquet schema.

Downloads BTC-USD style tickers for the project universe and writes
data/yf/raw_{SYM}_{TF}.parquet with the same schema as okx21 files
(ts Int64 epoch-ms, open/high/low/close/volume Float64), so engine
experiments run unchanged.  Yahoo limits: 15m -> 60d, 1h -> 730d,
1d -> full history.  4H is resampled from 1H.  Prints per-file
stats: bars, span, missing bars, zero-volume bars.

Usage:  uv run python -m experiments.load_yf [15m|1H|4H|1D|all]
"""

from __future__ import annotations

import sys
import time

from pathlib import Path

import numpy as np
import polars as pl
import yfinance as yf


REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "data" / "yf"

TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "LTC": "LTC-USD",
    "NEAR": "NEAR-USD",
    "BNB": "BNB-USD",
    "ADA": "ADA-USD",
    "DOT": "DOT-USD",
    "UNI": "CRV-USD",
    "ATOM": "ATOM-USD",
    "APT": "EOS-USD",
    "ARB": "ARB-USD",
    "OP": "OP-USD",
    "FIL": "FIL-USD",
    "INJ": "INJ-USD",
    "SUI": "KSM-USD",
    "TIA": "TIA-USD",
    "SEI": "SEI-USD",
    "FET": "FET-USD",
    "AAVE": "AAVE-USD",
    "GRT": "SAND-USD",
    "ALGO": "ALGO-USD",
    "VET": "VET-USD",
    "ICP": "ICP-USD",
    "HBAR": "HBAR-USD",
    "ETC": "ETC-USD",
    "BCH": "BCH-USD",
    "TRX": "TRX-USD",
    "SHIB": "SHIB-USD",
    "PEPE": "FLOKI-USD",
    "WIF": "WIF-USD",
    "TON": "TON-USD",
}
PERIODS = {"15m": "60d", "1H": "730d", "1D": "max"}
BARS_PER_DAY = {"15m": 96, "1H": 24, "4H": 6, "1D": 1}


def _fetch(sym: str, ysym: str, tf: str) -> pl.DataFrame | None:
    df = yf.download(
        ysym,
        interval=tf.lower() if tf != "1H" else "1h",
        period=PERIODS[tf],
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        print(f"{sym} {tf}: EMPTY", flush=True)
        return None
    if df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    out = pl.DataFrame(
        {
            "ts": (df.index.astype("int64") // 1_000_000).to_numpy().astype(np.int64),
            "open": df["Open"].to_numpy().astype(np.float64),
            "high": df["High"].to_numpy().astype(np.float64),
            "low": df["Low"].to_numpy().astype(np.float64),
            "close": df["Close"].to_numpy().astype(np.float64),
            "volume": df["Volume"].to_numpy().astype(np.float64),
        }
    )
    return out


def _resample_4h(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.sort("ts")
        .with_columns(pl.from_epoch("ts", time_unit="ms").alias("dt"))
        .group_by_dynamic("dt", every="4h", closed="left", label="left")
        .agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
        )
        .with_columns(pl.col("dt").dt.epoch("ms").alias("ts"))
        .select("ts", "open", "high", "low", "close", "volume")
        .drop_nulls()
    )


def _stats(df: pl.DataFrame, tf: str) -> str:
    step = 86_400_000 // BARS_PER_DAY[tf]
    ts = df["ts"]
    gaps = int((np.diff(ts.to_numpy()) > step).sum())
    zero_vol = int((df["volume"] <= 0).sum())
    d0 = ts.min() // 86_400_000
    d1 = ts.max() // 86_400_000
    return (
        f"bars={df.height} span={(d1 - d0) / 365.25:.2f}y "
        f"gaps={gaps} zero_vol={zero_vol} "
        f"last_close={df['close'][-1]:.2f}"
    )


def run() -> None:
    args = list(sys.argv[1:]) or ["all"]
    syms = [s for s in args if s in TICKERS] or list(TICKERS)
    tfs = [t for t in args if t in ("15m", "1H", "4H", "1D", "all")]
    if "all" in tfs:
        tfs = ["15m", "1H", "4H", "1D"]
    if not tfs:
        tfs = ["15m", "1H", "4H", "1D"]
    OUT.mkdir(parents=True, exist_ok=True)
    for i, sym in enumerate(syms):
        if i:
            time.sleep(2)  # be gentle with Yahoo rate limits
        ysym = TICKERS[sym]
        base: dict[str, pl.DataFrame] = {}
        for tf in tfs:
            if tf == "4H":
                if "1H" not in base and (OUT / f"raw_{sym}_1H.parquet").exists():
                    base["1H"] = pl.read_parquet(OUT / f"raw_{sym}_1H.parquet")
                if "1H" not in base:
                    base["1H"] = _fetch(sym, ysym, "1H")
                    if base["1H"] is not None:
                        base["1H"].write_parquet(OUT / f"raw_{sym}_1H.parquet")
                if base.get("1H") is None:
                    continue
                df = _resample_4h(base["1H"])
            else:
                df = _fetch(sym, ysym, tf)
            if df is None or df.is_empty():
                continue
            df.write_parquet(OUT / f"raw_{sym}_{tf}.parquet")
            print(f"{sym} {tf}: {_stats(df, tf)}", flush=True)


if __name__ == "__main__":
    run()
