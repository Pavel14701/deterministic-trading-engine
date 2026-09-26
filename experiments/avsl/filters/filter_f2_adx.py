# -*- coding: utf-8 -*-
"""F2 ADX x sizing filter -- frozen prereg (STATUS 2026-09-25,
AVSL TREND-FILTER PROGRAM, F2 SPEC).  One pass.

size_mult = clip(ADX14(4H at entry bar) / 25, 0.5, 1.5).
No trades dropped; the S1 size is multiplied.  SIZING, not a
skip gate (the ADX>25 skip gate already FAILED in E-history).
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from ta.src.trend.adx import adx_ind

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    collect_trades,
    evaluate,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.filters.filter_f1_htf import neg_windows, stream_metrics

ADX_LEN = 14
ADX_DEN = 25.0
MULT_MIN, MULT_MAX = 0.5, 1.5


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
    mults = []
    for sym in ASSETS:
        ts1, hp1, lp1, cp1, vol1 = read_1h(repo, sym)
        ts4, hp4, lp4, cp4, _v = resample_4h(ts1, hp1, lp1, cp1, vol1)
        d = collect_trades(sym, repo)
        adx = np.asarray(adx_ind(hp4, lp4, cp4, ADX_LEN,
                                 use_talib=False)[0])
        sizes = s1_sizes(cp4)
        ctxs[sym] = {"ts4": ts4, "sizes": sizes, "g0": d["g0"],
                     "n_bars": d["n_bars"], "trades": d["trades"]}
        for tr in d["trades"]:
            data["base"].append({**tr, "sym": sym})
            a = adx[tr["e0"]]
            if not np.isfinite(a):
                mult = MULT_MIN
            else:
                mult = float(np.clip(a / ADX_DEN, MULT_MIN, MULT_MAX))
            mults.append(mult)
            data["filt"].append({**tr, "sym": sym, "mult": mult})

    nb = len(data["base"])
    print(f"== F2 ==\ntrades: {nb} (all kept, size-scaled)")
    print(f"mult distribution: p10 {np.percentile(mults, 10):.2f} "
          f"med {np.median(mults):.2f} p90 {np.percentile(mults, 90):.2f}")
    mb = stream_metrics(ctxs, data["base"])
    # scaled stream: rebuild with mult, bypassing stream_metrics'
    # fixed sizes -> emulate by folding mult into a copied ctx
    import copy
    from experiments.avsl.filters.filter_f1_htf import \
        stream_metrics as _sm  # noqa: F401 (unused, clarity)

    class Scaled(dict):
        pass

    # simplest honest route: rebuild the stream here
    from engine.passed.avsl_cross_s1 import (
        RISK_PCT,
        SPLIT_FRAC,
        nw_sharpe,
        portfolio_dd,
    )
    g0 = min(c["g0"] for c in ctxs.values())
    n_g = max(c["n_bars"] + c["g0"] for c in ctxs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in sorted(data["filt"], key=lambda t: (t["e0"], t["sym"])):
        c = ctxs[tr["sym"]]
        hold = max(tr["e1"] - tr["e0"], 1)
        w = c["sizes"][tr["e0"]] * tr["mult"] * tr["net"] / (hold + 1)
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
              f"| F2 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"neg 12m windows: base {neg_windows(ctxs, data['base'])}")
    print(f"F2 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
