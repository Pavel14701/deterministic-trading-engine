# -*- coding: utf-8 -*-
"""Skew calibration probe: IV of prints vs DVOL, by moneyness.

Uses BOTH cached subsets (0.70-0.92 and 0.90-0.98 bands).
Question: is (print_iv - dvol) stable enough per moneyness bucket
and across years to freeze a proxy pricing rule
premium = BS(spot, K, dvol + skew(m)) for entries without prints?
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import repo_root

OUT = Path(repo_root() / "data/deribit")


def main() -> None:
    inst = json.loads((OUT / "instruments_BTC.json").read_text())
    exp_of = {i["instrument_name"]: i["expiration_timestamp"]
              for i in inst}

    _df = pl.read_parquet(repo_root() / "data/binance/kl_BTCUSDT_1h.parquet")
    spot_ts = _df["ts"].to_numpy().astype(np.int64)
    spot_px = _df["close"].to_numpy().astype(np.float64)
    dvol = json.loads((OUT / "dvol_BTC_1D.json").read_text())
    dvol_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dvol_v = np.array([d[4] for d in dvol], dtype=np.float64)

    def spot(ts: float) -> float:
        j = int(np.searchsorted(spot_ts, ts, side="right")) - 1
        return float(spot_px[max(j, 0)])

    def dv(ts: float) -> float:
        j = int(np.searchsorted(dvol_ts, ts, side="right")) - 1
        return float(dvol_v[max(j, 0)])

    rows = []   # (moneyness, ttm_days, iv, dvol, year)
    for sub in ("puts_subset.json", "puts_subset2.json"):
        names = json.loads((OUT / sub).read_text())
        for name in names:
            p = OUT / ("puts_trades" if "subset." in sub
                       else "puts_trades2") / f"{name}.json"
            if not p.exists():
                continue
            try:
                tr = json.loads(p.read_text())["result"]["trades"]
            except Exception:
                continue
            ttm0 = (exp_of[name] - (tr[0]["timestamp"] if tr else 0)) \
                / 86_400_000
            for x in tr:
                iv = x.get("iv")
                if not iv:
                    continue
                ts = x["timestamp"]
                px = spot(ts)
                m = names[name]["strike"] / px
                rows.append((m, ttm0, iv * 1.0, dv(ts),
                             dt.datetime.utcfromtimestamp(ts / 1000).year))

    a = np.array([(m, t, iv, d, y) for m, t, iv, d, y in rows])
    print(f"prints with iv: {len(a)}")
    sk = a[:, 2] - a[:, 3]
    a = np.column_stack([a, sk])
    print(f"overall skew offset (iv-dvol): median {np.median(sk):+.3f} "
          f"p25 {np.percentile(sk, 25):+.3f} p75 {np.percentile(sk, 75):+.3f}")
    print("\nper moneyness bucket (strike/spot):")
    for lo in np.arange(0.6, 1.0, 0.05):
        sel = a[(a[:, 0] >= lo) & (a[:, 0] < lo + 0.05)]
        if len(sel) < 10:
            continue
        s = sel[:, 5]
        by_year = {int(y): f"{v:+.2f}" for y, v in
                   zip(*np.unique(sel[:, 4], return_counts=False),
                   )} if False else {}
        yrs = sorted(set(int(y) for y in sel[:, 4]))
        ymed = {y: np.median(sel[sel[:, 4] == y][:, 5]) for y in yrs}
        print(f"  [{lo:.2f},{lo+0.05:.2f}): n={len(sel):5d} "
              f"skew med {np.median(s):+.3f} iqr "
              f"[{np.percentile(s, 25):+.3f},{np.percentile(s, 75):+.3f}] "
              f"per-year med {{"
              + ", ".join(f"{y}:{v:+.2f}" for y, v in ymed.items()) + "}")


if __name__ == "__main__":
    main()
