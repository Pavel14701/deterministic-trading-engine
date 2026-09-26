# -*- coding: utf-8 -*-
"""B1 candidate gating (per JOURNAL 2026-09-26 discipline):
levels: signal exists (DONE, PASS) -> yearly split -> cost model
-> coverage (after fetch) -> only then prereg.
This script runs the two checks that need NO fetch:
yearly split of DVOL crush, formalized cost math.
Output: runs/b1_candidate_checks.log
"""
from __future__ import annotations
__version__ = "1.0.0"
import datetime as dt
import json
import numpy as np
from experiments.options._pricing import bs
from experiments.options._runner import load_ctx, MSEC_DAY


def main():
    ctx = load_ctx()
    log = [f"b1_candidate_checks v{__version__} -- one-shot"]
    cal = json.loads((ctx["out"].parent.parent
                      / "data/events/event_calendar_2021_2026.json"
                      ).read_text())["events"]

    # ---- yearly split of DVOL crush (no filter, expiry-type focus) ----
    log.append("")
    log.append("[B1-gate yearly] DVOL crush T-1 -> T+1 by year")
    rows = []
    for e in cal:
        t_in, t_out = e["ts"] - MSEC_DAY, e["ts"] + MSEC_DAY
        if t_in < ctx["ts1"][0] or t_out > ctx["ts1"][-1]:
            continue
        c = ctx["dvol"](t_out) - ctx["dvol"](t_in)
        y = dt.datetime.utcfromtimestamp(t_in / 1000).year
        rows.append((y, e["type"], c))
    log.append("  ALL types: " + " | ".join(
        f"{y}: med {np.median([c for (yy, _, c) in rows if yy == y]):+.2f}pt "
        f"share<0 {np.mean([c < 0 for (yy, _, c) in rows if yy == y]):.0%} "
        f"n={sum(1 for (yy, _, _) in rows if yy == y)}"
        for y in sorted({r[0] for r in rows})))
    log.append("  expiry only: " + " | ".join(
        f"{y}: med {np.median([c for (yy, t, c) in rows if yy == y and t == 'expiry']):+.2f}pt "
        f"n={sum(1 for (yy, t, _) in rows if yy == y and t == 'expiry')}"
        for y in sorted({r[0] for r in rows if r[1] == 'expiry'})))
    log.append("  fomc only: " + " | ".join(
        f"{y}: med {np.median([c for (yy, t, c) in rows if yy == y and t == 'fomc']):+.2f}pt "
        f"n={sum(1 for (yy, t, _) in rows if yy == y and t == 'fomc')}"
        for y in sorted({r[0] for r in rows if r[1] == 'fomc'})))

    # ---- formalized cost math (per 1 BTC notional per leg) ----
    log.append("")
    log.append("[B1-gate cost] gross crush-vega vs round-trip cost")
    s0 = float(np.median(ctx["cp1"]))
    iv = float(np.median([ctx["dvol"](t) for t in ctx["ts1"][::240]]))
    ttm30 = 30 / 365
    prem30 = bs(s0, s0, ttm30, iv, True)
    prem7 = bs(s0, s0, 7 / 365, iv, True)
    for lab, prem, n_legs in (("2d hold, 30d legs", prem30, 2),
                              ("2d hold, 7d legs", prem7, 2)):
        gross = 1.51 * 48.7 * n_legs          # crush pt x vega x legs
        cost = 2 * 0.25 * prem * n_legs       # in/out x hc x legs
        log.append(f"  {lab:22s}: gross {gross:.0f}$ vs cost "
                   f"{cost:.0f}$ ratio {gross / cost:.2f} "
                   f"(гейт >= 3x)")
    log.append("  hold-to-expiry: cost = вход only "
               f"{0.25 * prem30 * 2:.0f}$, но PnL = crush + 30d "
               "theta/gamma -- считается только на фулл-цепи")

    out = ctx["out"].parent.parent / "runs/b1_candidate_checks.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
