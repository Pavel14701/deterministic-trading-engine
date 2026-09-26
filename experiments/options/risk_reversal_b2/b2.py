# -*- coding: utf-8 -*-
"""B2: risk reversal (short put 0.90 / long call 1.10) -- frozen
one-shot run.  See experiments/options/risk_reversal_b2/EXPERIMENT.md
(v1.0.0).  Gates G-B1..G-B5.
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


def main() -> None:
    ctx = load_ctx()
    cbuckets = calibrate_call_skew(ctx)
    specs = leg_specs(ctx)
    sides = {"put": -1.0, "call": 1.0}

    res = simulate(ctx, specs, sides, cbuckets=cbuckets)
    print(f"B2 v{__version__} -- risk reversal (short put 0.90 / "
          f"long call 1.10)")

    legs = res["legs"]
    puts = [l for l in legs if l["otype"] == "put"]
    calls = [l for l in legs if l["otype"] == "call"]
    pf = perf(res["daily"])
    worst = min((l["pnl"] for l in legs), default=0.0)
    real = float(np.mean([l["mode"] == "real" for l in legs])) if legs else 0.0

    # net credit per roll pair (legs are ordered put, call per roll)
    nets = [legs[i]["cash0"] + legs[i + 1]["cash0"]
            for i in range(0, len(legs) - 1, 2)
            if legs[i]["otype"] == "put" and legs[i + 1]["otype"] == "call"]
    net_med = float(np.median(nets)) if nets else float("nan")

    print(f"legs {len(legs)} (put {len(puts)} / call {len(calls)})")
    print(f"Sharpe={pf['sharpe']:+.2f} DD={pf['dd']:.1%} "
          f"total={pf['total']:+.1%} days={pf['n']}")
    print(f"  by year: "
          f"{ {k: round(x, 1) for k, x in pf.get('by_year', {}).items()} }")
    print(f"  put-leg sum {sum(l['pnl'] for l in puts):+.1f}%, "
          f"call-leg sum {sum(l['pnl'] for l in calls):+.1f}%")
    print(f"  real-print entry {real:.0%} "
          f"(put {np.mean([l['mode'] == 'real' for l in puts]):.0%} / "
          f"call {np.mean([l['mode'] == 'real' for l in calls]):.0%})")
    print(f"  net credit median {net_med:+.2f}% "
          f"(positive = received)")
    print(f"  worst leg {worst:+.1f}%")
    y2022 = pf.get("by_year", {}).get(2022, 0.0)

    p1 = pf.get("sharpe", 0.0) >= 1.0
    p2 = pf.get("dd", 1.0) <= 0.20
    p3 = worst >= -15.0
    p4 = y2022 >= -20.0
    p5 = (nets and net_med >= 0.0 and real >= 0.50)
    print(f"G-B1 Sharpe>=1.0: {'PASS' if p1 else 'FAIL'}")
    print(f"G-B2 DD<=20%: {'PASS' if p2 else 'FAIL'}")
    print(f"G-B3 worst leg>=-15%: {'PASS' if p3 else 'FAIL'}")
    print(f"G-B4 2022 PnL>=-20%: {'PASS' if p4 else 'FAIL'} "
          f"({y2022:+.1f}%)")
    print(f"G-B5 net credit>=0 & real>=50%: {'PASS' if p5 else 'FAIL'}")
    verdict = "PASS" if all([p1, p2, p3, p4, p5]) else "FAIL"
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
