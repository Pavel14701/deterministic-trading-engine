# -*- coding: utf-8 -*-
"""Wave-3 step 1: term-structure read-out (one-shot, no gates).

No new data needed: the slope is computed on the frozen strangle
rolls -- at roll_i there are real print-IVs for two neighbouring
expiries:

  front = put m~0.90 expiring nxt_i   (tenor ~30d)
  back  = put m~0.90 expiring nxt_{i+1} (tenor ~60d)

Read-out questions (prereg decision afterwards):
1. Is there a stable structure in slope = IV(back) - IV(front)
   (level and sign by year, pair coverage with double prints)?
2. Is the slope predictive: terciles of (IV_front - IV_back)
   vs subsequent realized vol over the front window (t_r, nxt).
3. IV-RV by tenor: front vs back (where does premium vs
   subsequent realized vol sit).

Output: runs/ts_readout.log.  Single run; results are read once
and journalised (docs/JOURNAL.md).
"""

from __future__ import annotations


__version__ = "1.0.0"

import datetime as dt
import math

import numpy as np

from experiments.options._runner import (
    MSEC_DAY,
    entry_iv,
    instrument_name,
    leg_specs,
    load_ctx,
)


def rv_window(ctx: dict, t0: float, t1: float) -> float:
    """Annualized realized vol (% ) on daily closes over [t0, t1)."""
    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    b0, b1 = int(t0 // MSEC_DAY), int(t1 // MSEC_DAY)
    days: dict[int, float] = {}
    lo = int(np.searchsorted(ts1, b0 * MSEC_DAY))
    hi = int(np.searchsorted(ts1, b1 * MSEC_DAY))
    for i in range(lo, hi):
        days[int(ts1[i] // MSEC_DAY)] = float(cp1[i])
    xs = np.array([days[d] for d in sorted(days)])
    if len(xs) < 10:
        return float("nan")
    return float(np.std(np.diff(np.log(xs))) * math.sqrt(365) * 100)


def main() -> None:
    ctx = load_ctx()
    log: list[str] = [f"ts_readout v{__version__} -- one-shot, no gates"]

    puts = [(t_r, nxt, k) for (t_r, nxt, otype, k) in leg_specs(ctx)
            if otype == "put"]
    puts.sort()

    rows = []
    n_front_only = 0
    for i in range(len(puts) - 1):
        t_r, nxt, k = puts[i]
        _, nxt2, k2 = puts[i + 1]
        if nxt2 <= nxt:          # нужна следующая экспирация
            continue
        iv_f = entry_iv(ctx, instrument_name(nxt, k, False), t_r)
        iv_b = entry_iv(ctx, instrument_name(nxt2, k2, False), t_r)
        if iv_f is None:
            n_front_only += 1
            continue
        if iv_b is None:
            n_front_only += 1
            continue
        rv_f = rv_window(ctx, t_r, nxt)
        rv_b = rv_window(ctx, t_r, nxt2)
        rows.append(dict(t_r=t_r, y=dt.datetime.utcfromtimestamp(
            t_r / 1000).year, iv_f=iv_f, iv_b=iv_b, slope=iv_b - iv_f,
            rv_f=rv_f, rv_b=rv_b))

    log.append(f"rolls {len(puts)}, pairs both-prints {len(rows)}, "
               f"front/back-no-print {n_front_only}")
    if len(rows) < 5:
        log.append("INSUFFICIENT COVERAGE -- no structure check")
        (ctx["out"].parent.parent / "runs/ts_readout.log").write_text(
            "\n".join(log) + "\n", encoding="utf-8")
        print("written runs/ts_readout.log")
        return

    sl = np.array([r["slope"] for r in rows])
    yrs = sorted({r["y"] for r in rows})
    log.append("slope = IV(back,60d) - IV(front,30d), put m~0.90")
    log.append("  by year: median / share>0 / n")
    for y in yrs:
        s = np.array([r["slope"] for r in rows if r["y"] == y])
        log.append(f"    {y}: {np.median(s):+6.1f}pt  "
                   f"{np.mean(s > 0):5.0%}  n={len(s)}")
    log.append(f"  ALL: median {np.median(sl):+.1f}pt "
               f"share>0 {np.mean(sl > 0):.0%} "
               f"IQR [{np.quantile(sl, .25):+.1f}, "
               f"{np.quantile(sl, .75):+.1f}] n={len(sl)}")

    # 2) предиктивность: терцили (IV_front - IV_back) против RV окна фронт-ноги
    pred = -sl                      # >0 = backwardation
    rvf = np.array([r["rv_f"] for r in rows])
    ok = np.isfinite(rvf)
    p_, r_ = pred[ok], rvf[ok]
    from scipy.stats import spearmanr
    rho, _ = spearmanr(p_, r_)
    log.append(f"predict: spearman(IVf-IVb, RV front-window) = {rho:+.2f}")
    qs = np.quantile(p_, [1 / 3, 2 / 3])
    for lab, lo, hi in (("t1_back", -1e9, qs[0]), ("t2", qs[0], qs[1]),
                        ("t3_cont", qs[1], 1e9)):
        sel = (p_ >= lo) & (p_ < hi) if hi != 1e9 else (p_ >= lo)
        if sel.sum():
            log.append(f"  {lab:8s}: n={sel.sum():2d} "
                       f"RV(med) {np.median(r_[sel]):5.1f}%  "
                       f"IVf(med) "
                       f"{np.median([rows[i]['iv_f'] for i in np.where(ok)[0][sel]]):5.1f}%")

    # 3) IV-RV по тенорам
    ivf = np.array([r["iv_f"] for r in rows])
    ivb = np.array([r["iv_b"] for r in rows])
    rvb = np.array([r["rv_b"] for r in rows])
    vrp_f, vrp_b = ivf - rvf, ivb - rvb
    okf, okb = np.isfinite(vrp_f), np.isfinite(vrp_b)
    log.append(f"VRP front(30d): med {np.median(vrp_f[okf]):+.1f}pt "
               f"(n={okf.sum()}) | back(60d): med "
               f"{np.median(vrp_b[okb]):+.1f}pt (n={okb.sum()})")

    out = ctx["out"].parent.parent / "runs/ts_readout.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
