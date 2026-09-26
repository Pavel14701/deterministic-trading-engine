# -*- coding: utf-8 -*-
"""IV-RV timer read-out (frozen one-shot, no gates).
See experiments/options/iv_rv_timer/EXPERIMENT.md (v1.0.0).
"""

from __future__ import annotations


__version__ = "1.0.0"

import datetime as dt
import json

import numpy as np

from experiments.options._runner import MSEC_DAY, load_ctx


def main() -> None:
    ctx = load_ctx()
    print(f"IV-RV timer v{__version__} -- forward-VRP read-out")

    # daily grid: DVOL days with timer and forward RV30 defined
    out = ctx["out"]
    dvol = json.loads((out / "dvol_BTC_1D.json").read_text())
    dv_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dv_v = np.array([d[4] for d in dvol], dtype=np.float64)

    timer = np.full(len(dv_ts), np.nan)
    fwd = np.full(len(dv_ts), np.nan)
    for i, t in enumerate(dv_ts):
        rv0 = ctx["rv30"](t)
        rv1 = ctx["rv30"](t + 30 * MSEC_DAY)
        if np.isfinite(rv0):
            timer[i] = dv_v[i] - rv0
        if np.isfinite(rv0) and np.isfinite(rv1):
            fwd[i] = dv_v[i] - rv1

    ok = np.isfinite(timer) & np.isfinite(fwd)
    tv, fv, tsv = timer[ok], fwd[ok], dv_ts[ok]
    q1, q2 = np.quantile(tv, [1 / 3, 2 / 3])
    print(f"n={len(tv)} tercile edges {q1:+.2f} / {q2:+.2f}")
    print("tercile     n    fwdVRP mean  median  share>0")
    means = {}
    for lab, lo, hi in (("t1_lo", -1e9, q1), ("t2", q1, q2),
                        ("t3_hi", q2, 1e9)):
        m = (tv >= lo) & (tv < hi) if hi != 1e9 else (tv >= lo)
        a = fv[m]
        means[lab] = float(a.mean()) if len(a) else float("nan")
        print(f"  {lab:6s} {len(a):5d}   {a.mean() if len(a) else float('nan'):+7.2f}")
        if len(a):
            print(f"        median {np.median(a):+7.2f} "
                  f"share>0 {np.mean(a > 0):5.0%}")

    # top tercile by year
    print("t3_hi by year (mean fwdVRP, n):")
    m3 = tv >= q2
    yr = {}
    for t, f in zip(tsv[m3], fv[m3]):
        y = dt.datetime.utcfromtimestamp(t / 1000).year
        yr.setdefault(y, []).append(f)
    for y in sorted(yr):
        a = np.array(yr[y])
        print(f"  {y}: {a.mean():+7.2f} n={len(a)}")

    # cross: timer tercile x DVOL quartile (share of overlap)
    print("cross timer-tercile x DVOL-pct-quartile (row shares):")
    pctv = np.array([ctx["pct_at"](t) for t in tsv])
    for lab, lo, hi in (("t1_lo", -1e9, q1), ("t2", q1, q2),
                        ("t3_hi", q2, 1e9)):
        m = (tv >= lo) & (tv < hi) if hi != 1e9 else (tv >= lo)
        p = pctv[m]
        if len(p) == 0:
            continue
        qd = np.minimum((p * 4).astype(int), 3)
        shares = [float(np.mean(qd == k)) for k in range(4)]
        print(f"  {lab:6s} q1..q4: "
              + " ".join(f"{s:.0%}" for s in shares))

    d = means["t3_hi"] - means["t1_lo"]
    valid = means["t3_hi"] >= 5.0 and d >= 3.0
    print(f"candidate-check (read-out, not gate): t3>=+5pt and "
          f"t3-t1>=+3pt: {valid} (t3={means['t3_hi']:+.2f}, "
          f"spread={d:+.2f})")
    print("done")


if __name__ == "__main__":
    main()
