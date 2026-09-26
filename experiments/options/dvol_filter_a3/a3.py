# -*- coding: utf-8 -*-
"""A3: DVOL-filter short strangle -- frozen one-shot run.
See experiments/options/dvol_filter_a3/EXPERIMENT.md (v1.0.0).
Gates G-A1..G-A5 on the filtered stream; unfiltered stream is
read-out only.
"""

from __future__ import annotations


__version__ = "1.0.0"

import numpy as np

from experiments.options._runner import (
    calibrate_call_skew,
    leg_specs,
    load_ctx,
    perf,
    simulate,
)


OUT_LOG = "runs/a3_dvol_filter.log"
MIN_PCT = 0.75


def main() -> None:
    ctx = load_ctx()
    cbuckets = calibrate_call_skew(ctx)
    specs = leg_specs(ctx)
    sides = {"put": -1.0, "call": -1.0}

    res = simulate(ctx, specs, sides, min_dvol_pct=MIN_PCT,
                   cbuckets=cbuckets)
    ref = simulate(ctx, specs, sides, cbuckets=cbuckets)  # read-out only

    print(f"A3 v{__version__} -- DVOL-filter short strangle "
          f"(pct>={MIN_PCT})")
    print(f"legs total {len(specs)}, entered {len(res['legs'])}")

    legs = res["legs"]
    pf = perf(res["daily"])
    rpf = perf(ref["daily"])
    ivrv = [l["ivrv"] for l in legs if np.isfinite(l["ivrv"])]
    worst = min((l["pnl"] for l in legs), default=0.0)
    real = float(np.mean([l["mode"] == "real" for l in legs])) if legs else 0.0

    print(f"filtered: Sharpe={pf['sharpe']:+.2f} DD={pf['dd']:.1%} "
          f"total={pf['total']:+.1%} days={pf['n']}")
    print(f"  by year: "
          f"{ {k: round(x, 1) for k, x in pf.get('by_year', {}).items()} }")
    print(f"  real-print entry {real:.0%}, worst leg {worst:+.1f}%")
    if ivrv:
        print(f"  IV-RV med {float(np.median(ivrv)):+.2f} "
              f"share>0 {float(np.mean(np.array(ivrv) > 0)):.0%}")
    print(f"unfiltered (read-out): Sharpe={rpf['sharpe']:+.2f} "
          f"DD={rpf['dd']:.1%} total={rpf['total']:+.1%}")

    p1 = pf.get("sharpe", 0.0) >= 1.0
    p2 = pf.get("dd", 1.0) <= 0.20
    p3 = (ivrv and float(np.median(ivrv)) > 2.0
          and float(np.mean(np.array(ivrv) > 0)) >= 0.60)
    p4 = worst >= -15.0
    p5 = len(legs) >= 25
    print(f"G-A1 Sharpe>=1.0: {'PASS' if p1 else 'FAIL'}")
    print(f"G-A2 DD<=20%: {'PASS' if p2 else 'FAIL'}")
    print(f"G-A3 IV-RV>2pt & share>=60%: {'PASS' if p3 else 'FAIL'}")
    print(f"G-A4 worst leg>=-15%: {'PASS' if p4 else 'FAIL'}")
    print(f"G-A5 coverage>=25: {'PASS' if p5 else 'FAIL'} "
          f"(n={len(legs)})")
    verdict = "PASS" if all([p1, p2, p3, p4, p5]) else "FAIL"
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
