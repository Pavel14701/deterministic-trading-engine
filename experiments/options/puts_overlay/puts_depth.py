# -*- coding: utf-8 -*-
"""Measure data depth for the puts overlay (NO backtest yet).

For each AVSL 4H long entry (2021-04+): look at the matched put
instruments (expiry >= entry+27d, strike 0.70-0.92 x spot) and
measure, per entry:
  - nearest put trade print at-or-before the entry timestamp and
    its age (hours) -- per strike, best strike = closest to 0.85x
    spot (the 0.10-0.20 delta band mid);
  - whether that print carries an `iv` field;
  - trades-per-instrument stats for the subset.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import collect_trades, repo_root

OUT = Path(repo_root() / "data/deribit")
TRADES = OUT / "puts_trades2"


def main() -> None:
    subset = json.loads((OUT / "puts_subset2.json").read_text())
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    exp_of = {i["instrument_name"]: i["expiration_timestamp"]
              for i in inst}

    _df = pl.read_parquet(repo_root() / "data/binance/kl_BTCUSDT_1h.parquet")
    spot_ts = _df["ts"].to_numpy().astype(np.int64)
    spot_px = _df["close"].to_numpy().astype(np.float64)

    def spot(ts_ms: float) -> float:
        j = int(np.searchsorted(spot_ts, ts_ms, side="right")) - 1
        return float(spot_px[max(j, 0)])

    # load all cached trade files once
    cache: dict[str, list] = {}
    n_tr = []
    for name in subset:
        p = TRADES / f"{name}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text()).get("result", {})
        tr = r.get("trades", [])
        cache[name] = tr
        n_tr.append(len(tr))
    n_tr_a = np.array(n_tr)
    print(f"cached instruments: {len(cache)}/{len(subset)}")
    print(f"trades/inst: median {np.median(n_tr_a):.0f} "
          f"p10 {np.percentile(n_tr_a, 10):.0f} "
          f"p90 {np.percentile(n_tr_a, 90):.0f} "
          f"zero {(n_tr_a == 0).sum()}")

    # per-entry coverage: next print AT/AFTER entry
    d = collect_trades("BTC")
    g0 = d["g0"]
    lags_after, prices_after = [], []
    matched_after = 0
    for t in d["trades"]:
        if not t["long"]:
            continue
        entry_ts = (g0 + t["e0"]) * 14_400_000
        if dt.datetime.utcfromtimestamp(entry_ts / 1000) < \
                dt.datetime(2021, 4, 1):
            continue
        px = spot(entry_ts)
        best = None
        for name, tr in cache.items():
            if exp_of[name] / 1000 < entry_ts / 1000 + 27 * 86400:
                continue
            k = subset[name]["strike"]
            if not (0.70 * px <= k <= 0.92 * px):
                continue
            nxt = [x for x in tr if x["timestamp"] >= entry_ts]
            if not nxt:
                continue
            first = nxt[0]
            age_h = (first["timestamp"] - entry_ts) / 3_600_000
            score = abs(np.log(k / (0.85 * px))) + 0.004 * age_h
            if best is None or score < best[0]:
                best = (score, name, age_h, first["price"])
        if best is None:
            continue
        matched_after += 1
        _, name, age_h, price = best
        lags_after.append(age_h)
        prices_after.append(price)

    la = np.array(lags_after)
    print(f"entries with a print AT/AFTER entry in-band: "
          f"{matched_after}/131")
    if matched_after:
        print(f"next-print lag (h): median {np.median(la):.1f} "
              f"p75 {np.percentile(la, 75):.1f} p90 {np.percentile(la, 90):.1f} "
              f"max {la.max():.1f}; price>0: "
              f"{sum(1 for p in prices_after if p > 0)}/{matched_after}")


if __name__ == "__main__":
    main()
