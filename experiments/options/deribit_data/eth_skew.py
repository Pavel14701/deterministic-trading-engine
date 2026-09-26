# -*- coding: utf-8 -*-
"""ETH skew read-out (one-shot, no gates) -- wave-2 step 2.

Mirror of vol_readout section 4 for ETH: median (print-IV -
DVOL_ETH) by moneyness bucket x year, puts and calls separately,
over data/deribit/eth_trades (subset: last-monthly-expiry rule).
Purpose: decide whether an ETH-side leg of B4 has a stable skew
structure before any B4 prereg is written.

Output: runs/eth_skew.log.  Single run; results are read once and
journalised (docs/JOURNAL.md).
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


def main() -> None:
    log: list[str] = [f"eth_skew v{__version__} -- one-shot read-out"]

    dvol = json.loads((OUT / "dvol_ETH_1D.json").read_text())
    dv_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dv_v = np.array([d[4] for d in dvol], dtype=np.float64)

    def dvol_at(ts: float) -> float:
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(dv_v[max(j, 0)])

    df = pl.read_parquet(repo_root()
                         / "data/binance/kl_ETHUSDT_1h.parquet")
    ts1 = df["ts"].to_numpy().astype(np.int64)
    cp1 = df["close"].to_numpy().astype(np.float64)

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    subset = json.loads((OUT / "eth_subset.json").read_text())

    books: dict[tuple, list[float]] = {}
    n_ok = n_bad = n_trades = n_iv = 0
    for name, meta in sorted(subset.items()):
        p = OUT / "eth_trades" / f"{name}.json"
        if not p.exists():
            continue
        try:
            tr = json.loads(p.read_text())["result"]["trades"]
        except Exception:
            n_bad += 1
            continue
        n_ok += 1
        for x in tr:
            n_trades += 1
            iv = x.get("iv")
            if not iv:
                continue
            n_iv += 1
            ts = x["timestamp"]
            m = meta["strike"] / spot(ts)
            bkt = (int(m / 0.05) * 5, meta["option_type"][0].upper(),
                   dt.datetime.utcfromtimestamp(ts / 1000).year)
            books.setdefault(bkt, []).append(float(iv) - dvol_at(ts))

    log.append(f"files ok={n_ok} corrupt={n_bad}; trades={n_trades} "
               f"with_iv={n_iv}")
    log.append("median(iv-dvol) by moneyness bucket x year "
               "(rows m%, C/P split), n>=10")
    buckets = sorted({k[0] for k in books})
    years = sorted({k[2] for k in books})
    for otype in ("P", "C"):
        log.append(f"  [{otype}] " + "".join(f"{y:>10d}" for y in years))
        for bkt in buckets:
            cells = []
            for y in years:
                a = books.get((bkt, otype, y), [])
                cells.append(f"{np.median(a):+7.1f}({len(a):5d})"
                             if len(a) >= 10 else "         -        ")
            log.append(f"    [{bkt:3d},{bkt + 3})" + "".join(cells))

    out = repo_root() / "runs/eth_skew.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
