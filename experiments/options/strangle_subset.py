# -*- coding: utf-8 -*-
"""Build the short-strangle instrument subset (puts + calls).

Roll cadence (to be frozen in the prereg): at every Deribit BTC
monthly expiry timestamp (settlement_period == "month"), sell the
strangle for the NEXT monthly expiry.  Strikes: grid strike
nearest 0.90x and 1.10x spot at the roll timestamp (delta ~0.15
per wing at 30d under the measured skew).  Window 2021-04 ..
latest cached.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import read_1h, repo_root

OUT = Path(repo_root() / "data/deribit")
D0 = int(dt.datetime(2021, 4, 1).timestamp() * 1000)


def main() -> None:
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    monthlies = [i for i in inst
                 if i.get("settlement_period") == "month"
                 and i["expiration_timestamp"] >= D0]
    expiries = sorted({i["expiration_timestamp"] for i in monthlies})
    expiries = [e for e in expiries
                if e <= max(i["expiration_timestamp"] for i in inst)
                - 30 * 86400_000]
    by_exp: dict[int, dict[str, list]] = {}
    for i in monthlies:
        by_exp.setdefault(i["expiration_timestamp"], {}).setdefault(
            i["option_type"], []).append(i)

    _df = pl.read_parquet(repo_root() / "data/binance/kl_BTCUSDT_1h.parquet")
    ts1 = _df["ts"].to_numpy().astype(np.int64)
    cp1 = _df["close"].to_numpy().astype(np.float64)

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    subset: dict[str, dict] = {}
    rolls = []
    for e in expiries:
        nexts = [x for x in expiries if x > e]
        if not nexts:
            break
        nxt = nexts[0]
        s0 = spot(e)
        for target, otype in ((0.90, "put"), (1.10, "call")):
            legs = by_exp.get(nxt, {}).get(otype, [])
            if not legs:
                continue

            def pick_near(tgt: float):
                return min(legs, key=lambda i: abs(i["strike"]
                                                   - tgt * s0))

            for tgt2 in (target, 0.80, 0.85, 0.95, 1.05, 1.15, 1.25):
                i = pick_near(tgt2)
                subset[i["instrument_name"]] = {
                    "expiration_timestamp": i["expiration_timestamp"],
                    "strike": i["strike"], "option_type": otype}
        rolls.append({"roll_ts": e, "next_exp": nxt, "spot": s0})
    (OUT / "strangle_subset.json").write_text(json.dumps(subset, indent=0))
    (OUT / "strangle_rolls.json").write_text(json.dumps(rolls))
    names = sorted(subset)
    (OUT / "strangle_names.txt").write_text("\n".join(names))
    n_put = sum(1 for v in subset.values() if v["option_type"] == "put")
    print(f"rolls: {len(rolls)} | instruments: {len(subset)} "
          f"(puts {n_put}, calls {len(subset) - n_put})")


if __name__ == "__main__":
    main()
