# -*- coding: utf-8 -*-
"""Puts-overlay feasibility: match frozen AVSL 4H long entries to the
Deribit put instruments that a 30d 0.10-0.20 delta overlay would
trade.  Sizes the trades fetch (step 2) BEFORE any prereg.

Declared matching rule (fixed here, will be frozen in the prereg):
  put expiry  = first instrument expiry >= entry_date + 27d
  put strike  = within [0.70, 0.92] x spot at entry (BTC)
                (delta 0.10-0.20 band under Black-76 ~ 10-30% OTM)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from engine.passed.avsl_cross_s1 import collect_trades, repo_root

OUT = Path(repo_root() / "data/deribit")


def main() -> None:
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    puts = sorted(
        (i for i in inst if i["option_type"] == "put"),
        key=lambda i: (i["expiration_timestamp"], i["strike"]),
    )
    by_expiry: dict[int, list] = {}
    for i in puts:
        by_expiry.setdefault(i["expiration_timestamp"], []).append(i)
    expiries = sorted(by_expiry)

    total_long = needed_insts = 0
    missing_warmup = 0
    # spot at entry: Binance 1H close (frozen data path)
    import polars as pl
    _df = pl.read_parquet(repo_root() / "data/binance/kl_BTCUSDT_1h.parquet")
    spot_ts = _df["ts"].to_numpy().astype(np.int64)
    spot_px = _df["close"].to_numpy().astype(np.float64)

    def spot(ts_ms: float) -> float:
        j = int(np.searchsorted(spot_ts, ts_ms, side="right")) - 1
        return float(spot_px[max(j, 0)])

    for sym in ("BTC",):
        d = collect_trades(sym)
        g0 = d["g0"]
        for t in d["trades"]:
            if not t["long"]:
                continue
            entry_ts = (g0 + t["e0"]) * 14_400_000
            entry_date = dt.datetime.utcfromtimestamp(entry_ts / 1000)
            if entry_date < dt.datetime(2021, 4, 1):
                missing_warmup += 1   # no DVOL / thin options before
                continue
            total_long += 1
            px = spot(entry_ts)
            # first expiry >= entry + 27d
            want = entry_ts / 1000 + 27 * 86400
            exp = next((e for e in expiries
                        if e / 1000 >= want), None)
            if exp is None:
                continue
            sel = {i["instrument_name"] for i in by_expiry[exp]
                   if 0.70 * px <= i["strike"] <= 0.92 * px}
            needed_insts += len(sel)

    print(f"AVSL 4H long entries (BTC, 2021-04+): {total_long} "
          f"(skipped pre-DVOL: {missing_warmup})")
    print(f"unique put instruments needed (8-25 pct strikes per "
          f"matched expiry): ~{needed_insts}")
    print(f"fetch cost estimate: ~{needed_insts * 2} requests "
          f"~{needed_insts * 2 * 0.4 / 60:.0f} min at conservative "
          f"pacing")


if __name__ == "__main__":
    main()
