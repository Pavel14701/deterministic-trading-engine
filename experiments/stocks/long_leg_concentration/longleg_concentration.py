# -*- coding: utf-8 -*-
"""DIAGNOSTIC (no gates, no verdict, family stays CLOSED):
concentration analysis of the stocks long-leg disclosure
(fx.. stocks transfer test A: long EV_orth +0.272R t+5.2).

Question: is the long-leg edge homogeneous across decades and
size, or concentrated in 2010+ mega-caps (= buyback beta)?

Size proxy: trailing 252-bar median dollar volume, cross-sectional
rank WITHIN entry year -> terciles (market cap unavailable;
liquidity is the standard proxy -- disclosed).
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.battery_v2 import ortho_ev
from engine.passed.avsl_cross_s1 import repo_root
from experiments.stocks.d1_transfer.avsl_d1_screen import TICKERS, _load
from experiments.stocks.d1_transfer.avsl_d1_transfer import GRID_START, collect, factor_by_bar


def main() -> None:
    repo = repo_root()
    ctxs, trades, dates, n_g = collect(repo, True)
    pos_of = {d: i for i, d in enumerate(dates)}
    f_by_bar = factor_by_bar(repo, dates, pos_of)
    g0g = min(c["g0"] for c in ctxs.values())

    # trailing liquidity per ticker (median DVOL over 252 bars up to entry)
    raws = {t: _load(t, repo) for t in TICKERS}
    liq = {}
    for tr in trades:
        if not tr["long"]:
            continue
        sym = tr["sym"]
        if sym not in liq:
            dts, arr = raws[sym]
            med = np.array([np.median(arr["DVOL"][max(0, i - 252):i + 1])
                            if i >= 60 else np.nan
                            for i in range(len(dts))])
            liq[sym] = (dts, med)
    longs = [t for t in trades if t["long"]]
    print(f"long trades total: {len(longs)}")

    # assign year + liquidity tercile rank within year
    for t in longs:
        gi = t["e0"] + ctxs[t["sym"]]["g0"] - g0g
        t["year"] = dates[gi].year
        dts, med = liq[t["sym"]]
        t["liq"] = med[t["e0"]]
    by_year = {}
    for t in longs:
        by_year.setdefault(t["year"], []).append(t)
    for year, ts in by_year.items():
        vals = sorted(x["liq"] for x in ts if np.isfinite(x["liq"]))
        if len(vals) >= 6:
            t33, t66 = vals[len(vals) // 3], vals[2 * len(vals) // 3]
            for x in ts:
                x["size_bucket"] = ("small" if x["liq"] < t33
                                    else "mid" if x["liq"] < t66 else "large")

    def show(name: str, buckets: dict) -> None:
        print(f"\n-- {name} --")
        for key in sorted(buckets):
            ts = buckets[key]
            if len(ts) < 20:
                continue
            eo, tt = ortho_ev(ts, f_by_bar)
            ev = float(np.mean([t["net"] for t in ts]))
            yrs = sorted({t["year"] for t in ts})
            print(f"{key:>10}: n={len(ts):4d} EV {ev:+.2f}R "
                  f"EV_orth {eo:+.3f}R t {tt:+.1f}  [{yrs[0]}-{yrs[-1]}]")

    decades = {}
    for t in longs:
        decades.setdefault(f"{(t['year'] // 10) * 10}s", []).append(t)
    show("long EV_orth by decade", decades)
    sizes = {}
    for t in longs:
        if "size_bucket" in t:
            sizes.setdefault(t["size_bucket"], []).append(t)
    show("long EV_orth by liquidity tercile (within-year rank)",
         sizes)
    cross = {}
    for t in longs:
        if "size_bucket" not in t:
            continue
        dec = f"{(t['year'] // 10) * 10}s"
        cross.setdefault((dec, t["size_bucket"]), []).append(t)
    show("long EV_orth decade x size", {f"{k[0]} {k[1]}": v
                                        for k, v in cross.items()})


if __name__ == "__main__":
    main()
