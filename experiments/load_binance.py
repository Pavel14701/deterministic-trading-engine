# -*- coding: utf-8 -*-
"""Binance USDT-M loader: 1H klines (full history) + OI accumulation.

Companion to load_okx (which serves the OKX OHLCV cache).  Two
products into data/binance/:

- ``kl``: 1H klines back to listing (cap 60k bars ~ 6.8y), file
  kl_{SYM}USDT_1h.parquet.  Carries taker_buy_volume -- the
  aggressor-flow feature for the TTF v1 / ProSP v2 preregs
  (STATUS.md 2026-09-21).
- ``oi``: merge-append open-interest window.  Binance caps the
  endpoint at ~30d; running this at least every 30 days grows an
  unbounded panel into oi_{SYM}USDT_1h.parquet.  Zero-regret
  accumulation track -- no backtest until ~180d contiguous.

Symbol note: TON -> GRAM rebrand on Binance USDT-M (TONUSDT is
SETTLING, GRAMUSDT is a new contract from 2026-07-02).  The TON-era
klines remain in kl_TONUSDT_1h.parquet; ``load_binance`` maps
TON-USDT -> GRAMUSDT for all new collection.

Usage:  python -m experiments.load_binance [SYM ...] [kl|oi|all]
"""

from __future__ import annotations

import sys

from pathlib import Path

from engine.infra.marketdata.binance_fetch import (
    fetch_klines,
    fetch_oi_history,
)
from experiments.funding_carry import UNIVERSE
from experiments.load_yf import _stats


REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "data" / "binance"

# Binance USDT-M symbols are the OKX inst names without the dash.
# TON was rebranded to GRAM on Binance USDT-M (TONUSDT now SETTLING;
# GRAMUSDT is a NEW contract, history from 2026-07-02 -- not a
# continuous rename).  The TON-era klines stay cached as
# kl_TONUSDT_1h.parquet; live collection continues under GRAMUSDT.
SYMBOL_ALIASES = {"TON-USDT": "GRAMUSDT"}
SYMBOLS = [SYMBOL_ALIASES.get(u, u.replace("-", "")) for u in UNIVERSE]
MAX_BARS = {"1h": 60_000}  # ~6.8y at 1h: covers TTF v1 F1 (2021-01-)


def run() -> None:
    args = list(sys.argv[1:])
    syms = [s for s in args if s in SYMBOLS] or SYMBOLS
    prods = [p for p in args if p in ("kl", "oi", "all")] or ["kl", "oi"]
    if "all" in prods:
        prods = ["kl", "oi"]
    CACHE.mkdir(parents=True, exist_ok=True)
    for sym in syms:
        if "kl" in prods:
            try:
                df = fetch_klines(
                    sym, interval="1h", max_bars=MAX_BARS["1h"],
                    cache_dir=str(CACHE),
                )
                # _stats expects the OKX tf notation ("1H", not "1h")
                print(f"{sym} kl 1h: {_stats(df, '1H')}", flush=True)
            except Exception as exc:  # keep the sweep going
                print(f"{sym} kl: FAILED {exc}", flush=True)
        if "oi" in prods:
            try:
                df = fetch_oi_history(sym, interval="1h", cache_dir=str(CACHE))
                print(
                    f"{sym} oi 1h: {df.height} rows, "
                    f"span {df.height / 24:.1f}d cumulative",
                    flush=True,
                )
            except Exception as exc:
                print(f"{sym} oi: FAILED {exc}", flush=True)


if __name__ == "__main__":
    run()
