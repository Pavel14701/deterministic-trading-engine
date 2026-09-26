# -*- coding: utf-8 -*-
"""D1 covered calls -- frozen one-shot run.
See experiments/options/covered_calls/EXPERIMENT.md (v1.0.0).
Gates G-D1a..G-D1d.  Output: runs/covered_calls.log
"""

from __future__ import annotations


__version__ = "1.0.0"

import math

import numpy as np

from experiments.options._runner import leg_specs, load_ctx, simulate


def main() -> None:
    ctx = load_ctx()
    res = simulate(ctx, [s for s in leg_specs(ctx) if s[2] == "call"],
                   {"put": -1.0, "call": -1.0})
    legs = res["legs"]
    ts1, cp1 = ctx["ts1"], ctx["cp1"]

    # BTC daily returns over the same window
    d0 = min(res["daily"])
    d1 = max(res["daily"])
    closes: dict[int, float] = {}
    lo = int(np.searchsorted(ts1, d0 * 86_400_000))
    hi = int(np.searchsorted(ts1, (d1 + 1) * 86_400_000))
    for i in range(lo, hi):
        closes[int(ts1[i] // 86_400_000)] = float(cp1[i])
    days = sorted(closes)
    btc = {}
    import itertools
    for a, b in itertools.pairwise(days):
        btc[b] = (closes[b] / closes[a] - 1) * 100

    port = {d: btc.get(d, 0.0) + res["daily"].get(d, 0.0)
            for d in sorted(set(btc) | set(res["daily"]))}

    def stats(stream: dict) -> dict:
        ds = sorted(stream)
        v = np.array([stream[d] for d in ds])
        eq = np.cumprod(1 + v / 100)
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
        mu, sd = float(v.mean()), float(v.std())
        sharpe = mu / sd * math.sqrt(365) if sd > 0 else 0.0
        yrs = (ds[-1] - ds[0]) / 365.0
        cagr = float(eq[-1] ** (1 / yrs) - 1) if eq[-1] > 0 else -1.0
        calmar = cagr / dd if dd > 0 else float("inf")
        return dict(sharpe=float(sharpe), dd=dd, total=float(eq[-1] - 1),
                    cagr=cagr, calmar=float(calmar))

    sp, sb = stats(port), stats(btc)
    yield_pct = float(sum(l["cash0"] for l in legs)) / len(legs) * 12.0
    capped = sum(1 for l in legs
                 if ctx["spot"](l["nxt"]) > l["k"] * 1.0) / len(legs)

    log = [f"covered_calls v{__version__} -- one-shot, frozen gates",
           f"legs {len(legs)}, days {len(port)}",
           f"portfolio: Sharpe {sp['sharpe']:+.2f} DD {sp['dd']:.1%} "
           f"CAGR {sp['cagr']:+.1%} Calmar {sp['calmar']:.2f}",
           f"BTC hold : Sharpe {sb['sharpe']:+.2f} DD {sb['dd']:.1%} "
           f"CAGR {sb['cagr']:+.1%} Calmar {sb['calmar']:.2f}",
           f"yield {yield_pct:.1f}%/yr, capped-upside months "
           f"{capped:.0%}"]

    g1 = sp["sharpe"] >= 0.8
    g2 = sp["dd"] <= 0.40
    g3 = sp["calmar"] > sb["calmar"]
    g4 = yield_pct >= 2.0
    log += [f"G-D1a Sharpe>=0.8: {'PASS' if g1 else 'FAIL'}",
            f"G-D1b DD<=40%: {'PASS' if g2 else 'FAIL'}",
            f"G-D1c Calmar>BTC: {'PASS' if g3 else 'FAIL'}",
            f"G-D1d yield>=2%: {'PASS' if g4 else 'FAIL'}",
            f"VERDICT: {'PASS' if all([g1, g2, g3, g4]) else 'FAIL'}"]

    out = ctx["out"].parent.parent / "runs/covered_calls.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
