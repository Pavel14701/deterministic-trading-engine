# -*- coding: utf-8 -*-
"""ETH trades-subset builder for wave-2 (B4, ETH skew table).

Frozen selection rule (declared BEFORE fetch, no tuning):
  - expiries: the LAST expiry of each calendar month with expiry in
    [2021-06-01, 2026-08-31] (DVOL-era, ends before data freeze);
  - reference spot per expiry: ETHUSDT 1H close at expiry - 30 days;
  - put targets m in {0.70 ... 0.95}, call targets m in
    {1.00 ... 1.40}, 0.05 grid; nearest available strike per target;
  - unique instrument names -> data/deribit/eth_subset.json and
    eth_names.txt (one per line, for the trades fetcher).
Writes nothing else; resumable.
"""

from __future__ import annotations

__version__ = "1.0.0"

import datetime as dt
import json

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import repo_root

MSEC_DAY = 86_400_000
OUT = repo_root() / "data/deribit"
PUT_TARGETS = np.arange(0.70, 0.951, 0.05)
CALL_TARGETS = np.arange(1.00, 1.401, 0.05)


def main() -> None:
    inst = json.loads((OUT / "instruments_ETH.json").read_text())
    df = pl.read_parquet(repo_root()
                         / "data/binance/kl_ETHUSDT_1h.parquet")
    ts1 = df["ts"].to_numpy().astype(np.int64)
    cp1 = df["close"].to_numpy().astype(np.float64)

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)]) if j >= 0 else float("nan")

    lo = int(dt.datetime(2021, 6, 1).timestamp() * 1000)
    hi = int(dt.datetime(2026, 8, 31, 23, 59).timestamp() * 1000)

    # last expiry per calendar month
    by_month: dict[str, float] = {}
    for i in inst:
        e = i["expiration_timestamp"]
        if not (lo <= e <= hi):
            continue
        key = dt.datetime.utcfromtimestamp(e / 1000).strftime("%Y-%m")
        if e > by_month.get(key, 0):
            by_month[key] = e
    expiries = sorted(set(by_month.values()))
    print(f"expiries: {len(expiries)} "
          f"({dt.datetime.utcfromtimestamp(expiries[0] / 1000):%Y-%m} -> "
          f"{dt.datetime.utcfromtimestamp(expiries[-1] / 1000):%Y-%m})")

    by_exp: dict[float, list[dict]] = {}
    for i in inst:
        e = i["expiration_timestamp"]
        if e in set(expiries):
            by_exp.setdefault(e, []).append(i)

    subset: dict[str, dict] = {}
    for e in expiries:
        s0 = spot(e - 30 * MSEC_DAY)
        if not np.isfinite(s0):
            continue
        for otype, targets in (("put", PUT_TARGETS),
                               ("call", CALL_TARGETS)):
            pool = [o for o in by_exp[e] if o["option_type"] == otype]
            if not pool:
                continue
            for tgt in targets:
                best = min(pool, key=lambda o: abs(o["strike"] - tgt * s0))
                subset[best["instrument_name"]] = {
                    "strike": best["strike"],
                    "option_type": otype,
                    "expiration_timestamp": e,
                }
    names = sorted(subset)
    (OUT / "eth_subset.json").write_text(json.dumps(subset, indent=0))
    (OUT / "eth_names.txt").write_text("\n".join(names) + "\n")
    n_put = sum(1 for v in subset.values() if v["option_type"] == "put")
    print(f"subset: {len(names)} instruments "
          f"(put {n_put} / call {len(names) - n_put})")
    print(f"written {OUT / 'eth_names.txt'}")


if __name__ == "__main__":
    main()
