# -*- coding: utf-8 -*-
"""One-off diagnostic for the G2' DD window (not a gate run)."""
from datetime import datetime, timezone

import numpy as np

from experiments.avsl.avsl_cross_confirm import _collect
from experiments.avsl.avsl_cross_confirm2 import _accrual_stream
from experiments.avsl.avsl_cross_tf import ASSETS, MSEC_4H


def main() -> None:
    data = {s: _collect(s) for s in ASSETS}
    g0 = min(d["g0"] for d in data.values())
    n_g = max(d["n_bars"] + d["g0"] for d in data.values()) - g0
    trs = [{**t, "sym": s} for s, d in data.items()
           for t in d["trades"] if t["tp"] == 5.0]
    split = int(n_g * 2 / 3)
    stream = _accrual_stream(trs, n_g)
    eq = np.cumprod(1 + 0.01 * stream[:split])
    peak = np.maximum.accumulate(eq)
    dd = 1 - eq / peak
    k = int(np.argmax(dd))
    pk = int(np.argmax(peak[:k + 1]))
    rec = next((i for i in range(k, split) if eq[i] >= peak[k]), -1)

    def f(i: int) -> str:
        ts = (g0 + i) * MSEC_4H / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m")

    print(f"max DD {dd[k]:.1%}: trough {f(k)}, peak from {f(pk)}, "
          f"recovered "
          f"{f(rec) if rec >= 0 else 'NEVER within PRIMARY'}")
    conc = np.zeros(n_g)
    for t in trs:
        conc[t["e0"]:t["e1"] + 1] += 1
    print(f"concurrency: mean {conc.mean():.1f}, "
          f"p90 {int(np.percentile(conc[:split], 90))}, "
          f"max {int(conc.max())}")
    print(f"equity multiple over PRIMARY: {eq[-1]:.1f}x")
    print(f"buckets with DD>50%: {int((dd > 0.5).sum())} of {split}")
    # yearly equity to see where the pain is
    yr = 6 * 365
    for y0 in range(0, split, yr):
        seg = eq[y0:y0 + yr]
        d = float(np.max(1 - seg / np.maximum.accumulate(seg)))
        print(f"  year {f(y0)}: dd {d:.0%}")


if __name__ == "__main__":
    main()
