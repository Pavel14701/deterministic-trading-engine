# -*- coding: utf-8 -*-
"""Extend the okx21 raw cache: 36-asset universe, deep history.

Wraps engine.infra.marketdata.okx_fetch.fetch_candles (public REST,
no keys, resumable page-cache = the raw files themselves).  Writes /
extends data/okx21/raw_{SYM}-USDT_{TF}.parquet -- the same directory,
naming and schema (ts Int64 epoch-ms + OHLCV Float64) the AVSL /
stats experiments already read.

Depth caps (bars): 15m 100k (~2.9y), 1H 40k (~4.6y), 4H 20k (~9y),
1D 5000 (~13.7y, capped by each coin's listing date).  Re-runs are
incremental: when the cached file is shorter than the cap the fetcher
walks backwards from the oldest cached bar, so depth grows run over
run.  New (2026) listings simply end where the coin was listed.

Usage:  python -m engine.experiments.load_okx [SYM ...] [15m|1H|4H|1D|all]
"""

from __future__ import annotations

import sys

from pathlib import Path

from engine.experiments.load_yf import _stats
from engine.infra.marketdata.okx_fetch import fetch_candles


REPO = Path(__file__).resolve().parent.parent.parent
CACHE = REPO / "data" / "okx21"

# The 10 assets already cached in data/okx21 (depth extension) ...
BASE = [
    "BTC", "ETH", "SOL", "XRP", "DOGE",
    "AVAX", "LINK", "LTC", "NEAR", "BNB",
]
# ... and the 24 added for the stats universe (all verified against
# /public/instruments SPOT).  VET-USDT and TON-USDT are NOT on OKX
# (delisted; code 51001) -- those two exist only in the yf set, so the
# okx universe is 34 assets vs 36 on yf.
NEW = [
    "ADA", "DOT", "UNI", "ATOM", "APT", "ARB", "OP", "FIL", "INJ",
    "SUI", "TIA", "SEI", "FET", "AAVE", "GRT", "ALGO", "ICP",
    "HBAR", "ETC", "BCH", "TRX", "SHIB", "PEPE", "WIF",
]
ALL = BASE + NEW
MAX_BARS = {"15m": 100_000, "1H": 40_000, "4H": 20_000, "1D": 5_000}
TFS = ["15m", "1H", "4H", "1D"]


def run() -> None:
    args = list(sys.argv[1:])
    syms = [s for s in args if s in ALL] or ALL
    tfs = [t for t in args if t in (*TFS, "all")] or TFS
    if "all" in tfs:
        tfs = TFS
    CACHE.mkdir(parents=True, exist_ok=True)
    for sym in syms:
        for tf in tfs:
            try:
                df = fetch_candles(
                    f"{sym}-USDT",
                    bar=tf,
                    max_bars=MAX_BARS[tf],
                    cache_dir=str(CACHE),
                )
            except (RuntimeError, Exception) as exc:  # keep the sweep going
                print(f"{sym} {tf}: FAILED {exc}", flush=True)
                continue
            print(f"{sym} {tf}: {_stats(df, tf)}", flush=True)


if __name__ == "__main__":
    run()
