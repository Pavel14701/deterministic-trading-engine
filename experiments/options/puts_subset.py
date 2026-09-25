# -*- coding: utf-8 -*-
"""Build the puts subset (union over matched AVSL long entries)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import collect_trades, repo_root

OUT = Path(repo_root() / "data/deribit")


def main() -> None:
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    puts = sorted((i for i in inst if i["option_type"] == "put"),
                  key=lambda i: (i["expiration_timestamp"], i["strike"]))
    by_expiry: dict[int, list] = {}
    for i in puts:
        by_expiry.setdefault(i["expiration_timestamp"], []).append(i)
    expiries = sorted(by_expiry)

    _df = pl.read_parquet(repo_root() / "data/binance/kl_BTCUSDT_1h.parquet")
    spot_ts = _df["ts"].to_numpy().astype(np.int64)
    spot_px = _df["close"].to_numpy().astype(np.float64)

    def spot(ts_ms: float) -> float:
        j = int(np.searchsorted(spot_ts, ts_ms, side="right")) - 1
        return float(spot_px[max(j, 0)])

    subset: dict[str, dict] = {}
    d = collect_trades("BTC")
    g0 = d["g0"]
    n_long = 0
    for t in d["trades"]:
        if not t["long"]:
            continue
        entry_ts = (g0 + t["e0"]) * 14_400_000
        if dt.datetime.utcfromtimestamp(entry_ts / 1000) < \
                dt.datetime(2021, 4, 1):
            continue
        n_long += 1
        px = spot(entry_ts)
        exp = next((e for e in expiries
                    if e / 1000 >= entry_ts / 1000 + 27 * 86400), None)
        if exp is None:
            continue
        for i in by_expiry[exp]:
            if 0.90 * px <= i["strike"] <= 0.98 * px:
                subset[i["instrument_name"]] = {
                    "expiration_timestamp": i["expiration_timestamp"],
                    "strike": i["strike"]}
    (OUT / "puts_subset2.json").write_text(json.dumps(subset, indent=0))
    print(f"longs matched: {n_long}; subset: {len(subset)} instruments")


if __name__ == "__main__":
    main()
