# -*- coding: utf-8 -*-
"""F5 Realized-vol regime sizing -- frozen prereg (STATUS
2026-09-25, AVSL TREND-FILTER PROGRAM, F5 SPEC).  One pass.

vol_d = std(last 90 DAILY log returns) of the asset's own
daily closes.  size mult = 1.2 if vol_d < median(vol_d over
the prior 365-day window of vol_d values), else 0.8.
Insufficient daily history (<90+365 days) -> mult 1.0
(neutral; count disclosed).  Distinct measurement from the
FAILED S2 (ATR-percentile): realized daily vol vs its own
1y median, no percentiles.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    collect_trades,
    evaluate,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.filters.filter_f1_htf import (
    DAY,
    daily_closes,
    neg_windows,
    stream_metrics,
)

VOL_WIN = 90
MED_WIN = 365
HI_MULT, LO_MULT = 0.8, 1.2


def main() -> None:
    repo = repo_root()
    base = evaluate()
    ok = (abs(base["PRIMARY"]["net_ev"] - 0.17) < 0.05
          and abs(base["F3"]["net_ev"] - 0.33) < 0.05)
    print(f"baseline sanity: {'OK' if ok else 'DEVIATION - ABORT'}")
    if not ok:
        return

    ctxs = {}
    data = {"base": [], "filt": []}
    n_neutral = 0
    mults = []
    for sym in ASSETS:
        ts1, hp1, lp1, cp1, vol1 = read_1h(repo, sym)
        ts4, _hp, _lp, cp4, _v = resample_4h(ts1, hp1, lp1, cp1, vol1)
        d = collect_trades(sym, repo)
        dk, dc = daily_closes(ts1, cp1)
        lr = np.diff(np.log(dc))
        # rolling 90d std, keyed by day index (ends at day j)
        roll_std = np.full(len(lr), np.nan)
        c = np.cumsum(np.insert(lr ** 2, 0, 0.0))
        cs = np.cumsum(np.insert(lr, 0, 0.0))
        idx = np.arange(VOL_WIN - 1, len(lr))
        roll_std[idx] = np.sqrt(
            (c[idx + 1] - c[idx + 1 - VOL_WIN]) / VOL_WIN
            - ((cs[idx + 1] - cs[idx + 1 - VOL_WIN]) / VOL_WIN) ** 2)
        ctxs[sym] = {"ts4": ts4, "sizes": s1_sizes(cp4),
                     "dkeys": dk, "g0": d["g0"],
                     "n_bars": d["n_bars"], "trades": d["trades"]}
        for tr in d["trades"]:
            data["base"].append({**tr, "sym": sym})
            m = int(ts4[tr["e0"]]) + MSEC_4H
            j = int(np.searchsorted(dk, m // DAY - 1, side="right")) - 1
            # lr index for day j: day j+1 open->close return = lr[j]
            if j < MED_WIN + VOL_WIN or not np.isfinite(roll_std[j]):
                mult = 1.0
                n_neutral += 1
            else:
                vol_d = roll_std[j]
                med = np.nanmedian(roll_std[j - MED_WIN:j + 1])
                mult = LO_MULT if vol_d < med else HI_MULT
            mults.append(mult)
            data["filt"].append({**tr, "sym": sym, "mult": mult})

    nb = len(data["base"])
    print(f"== F5 ==\ntrades: {nb} (all kept, size-scaled; "
          f"neutral-1.0: {n_neutral})")
    print(f"mult share: hi(1.2) {np.mean(np.array(mults) > 1):.0%} "
          f"lo(0.8) {np.mean(np.array(mults) < 1):.0%}")
    mb = stream_metrics(ctxs, data["base"])
    from engine.passed.avsl_cross_s1 import (
        SPLIT_FRAC,
        nw_sharpe,
        portfolio_dd,
    )
    g0 = min(v["g0"] for v in ctxs.values())
    n_g = max(v["n_bars"] + v["g0"] for v in ctxs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in sorted(data["filt"], key=lambda t: (t["e0"], t["sym"])):
        v = ctxs[tr["sym"]]
        hold = max(tr["e1"] - tr["e0"], 1)
        w = v["sizes"][tr["e0"]] * tr["mult"] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    mf = {"n": len(data["filt"])}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in data["filt"] if lo <= t["e0"] < hi]
        pos = 0
        for sym in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        mf[seg] = {"n": len(seg_tr), "sharpe_nw": nw_sharpe(s[lo:hi]),
                   "dd": portfolio_dd(s[lo:hi]),
                   "net_ev": (float(np.mean([t["net"] for t in seg_tr]))
                              if seg_tr else float("nan")),
                   "pos_assets": pos}
    gates = []
    for seg in ("PRIMARY", "F3"):
        b, f = mb[seg], mf[seg]
        dd_ok = f["dd"] <= 0.8 * b["dd"]
        ev_ok = f["net_ev"] >= 0.9 * b["net_ev"]
        g4_ok = f["pos_assets"] >= 7
        gates.append(dd_ok and ev_ok and g4_ok)
        print(f"{seg:>7}: base DD={b['dd']:.0%} EV={b['net_ev']:+.2f}R "
              f"| F5 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"F5 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
