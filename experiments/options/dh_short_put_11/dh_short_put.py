# -*- coding: utf-8 -*-
"""1.1: delta-hedged short put -- frozen one-shot run.
See experiments/options/dh_short_put_11/EXPERIMENT.md (v1.0.0).
Gates G-H1..G-H5.  Only legs with a real print-IV are hedged.
"""

from __future__ import annotations


__version__ = "1.0.0"

import numpy as np

from experiments.options._hedge import delta_hedge
from experiments.options._runner import (
    entry_iv,
    instrument_name,
    leg_specs,
    load_ctx,
    perf,
)


def main() -> None:
    ctx = load_ctx()
    specs = [(t_r, nxt, k) for (t_r, nxt, otype, k) in leg_specs(ctx)
             if otype == "put"]
    ts1, cp1 = ctx["ts1"], ctx["cp1"]

    daily: dict[int, float] = {}
    legs = []
    n_skip = 0
    for (t_r, nxt, k) in specs:
        iv = entry_iv(ctx, instrument_name(nxt, k, False), t_r)
        if iv is None:
            n_skip += 1
            continue
        s0 = ctx["spot"](t_r)
        lo = int(np.searchsorted(ts1, t_r, side="left"))
        hi = int(np.searchsorted(ts1, nxt, side="left"))
        path = [(int(ts1[i]), float(cp1[i])) for i in range(lo, hi)
                if ts1[i] < nxt]
        res = delta_hedge(path, float(k), nxt, iv, -1.0, is_call=False,
                          band=0.10)
        scale = 1.0 / s0 * 10.0        # NOTIONAL 0.10 -> % equity
        leg_pnl = res["pnl"] * scale
        # daily stream: per-leg value DIFFS (like strangle runner);
        # levels are per-leg and disappear after settle -> use diffs
        leg_days = sorted(res["daily"])
        prev = 0.0
        for d in leg_days:
            dv = (res["daily"][d] - prev) * scale
            daily[d] = daily.get(d, 0.0) + dv
            prev = res["daily"][d]
        legs.append(dict(t_r=t_r, pnl=leg_pnl, iv=iv,
                         ivrv=ctx["dvol"](t_r) - ctx["rv30"](t_r),
                         n_rebal=res["n_rebal"]))

    print(f"1.1 v{__version__} -- delta-hedged short put 0.90 "
          f"(band 0.10, prints-only)")
    print(f"legs total {len(specs)}, hedged {len(legs)}, "
          f"skipped-no-print {n_skip}")
    if not legs:
        print("VERDICT: FAIL (no legs)")
        return

    pf = perf(daily)

    pnls = np.array([l["pnl"] for l in legs])
    worst = float(pnls.min())
    real_share = len(legs) / len(specs)
    print(f"Sharpe={pf['sharpe']:+.2f} DD={pf['dd']:.1%} "
          f"total={pf['total']:+.1%} days={pf['n']}")
    print(f"  by year: "
          f"{ {k: round(x, 1) for k, x in pf.get('by_year', {}).items()} }")
    print(f"  leg pnl: mean {pnls.mean():+.2f}% median "
          f"{np.median(pnls):+.2f}% worst {worst:+.2f}%")
    print(f"  rebal mean {np.mean([l['n_rebal'] for l in legs]):.1f} "
          f"per leg")
    ivrv = np.array([l["ivrv"] for l in legs])
    ok = np.isfinite(ivrv)
    print(f"  entry IV-RV med {np.median(ivrv[ok]):+.2f} "
          f"share>0 {np.mean(ivrv[ok] > 0):.0%}")
    # VRP terciles vs hedged pnl (read-out)
    qs = np.quantile(ivrv[ok], [1 / 3, 2 / 3])
    for lab, lo, hi in (("t1_lo", -1e9, qs[0]), ("t2", qs[0], qs[1]),
                        ("t3_hi", qs[1], 1e9)):
        sel = (ivrv >= lo) & (ivrv < hi) if hi != 1e9 else (ivrv >= lo)
        if sel.sum():
            print(f"  IV-RV {lab:6s}: n={sel.sum():3d} "
                  f"leg pnl med {np.median(pnls[sel]):+.2f}%")

    p1 = pf.get("sharpe", 0.0) >= 1.0
    p2 = pf.get("dd", 1.0) <= 0.20
    p3 = float(np.median(pnls)) >= 0.0 and float(pnls.mean()) >= 0.0
    p4 = worst >= -15.0
    p5 = len(legs) >= 25
    print(f"G-H1 Sharpe>=1.0: {'PASS' if p1 else 'FAIL'}")
    print(f"G-H2 DD<=20%: {'PASS' if p2 else 'FAIL'}")
    print(f"G-H3 leg median>=0 & mean>=0: {'PASS' if p3 else 'FAIL'}")
    print(f"G-H4 worst leg>=-15%: {'PASS' if p4 else 'FAIL'}")
    print(f"G-H5 coverage>=25: {'PASS' if p5 else 'FAIL'} "
          f"(n={len(legs)}, prints {real_share:.0%})")
    verdict = "PASS" if all([p1, p2, p3, p4, p5]) else "FAIL"
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
