# -*- coding: utf-8 -*-
"""Grid-alignment convention check for the FROZEN AVSL verdict.

Diagnostic ONLY (no gate, signal or sizing edit): recomputes the
frozen evaluate() gates on the SAME trades/sizes/thresholds with
entries shifted to the TRUE global 4H grid (absolute bucket minus
the earliest asset bucket).  Motivation: the E8b adjudication
(found e8b_adjudication.md) showed evaluate() and retest_entry
place stream trades by ASSET-LOCAL index -- late-listed assets
land up to ~2246 buckets (~374d) early in the stream.  The AVSL
frozen PRIMARY DD (22%) sits next to the 25% cap, so convention
robustness of the only issued PASS must be on the record.

Legacy numbers below must reproduce the frozen verdict
(Sharpe 1.50/2.84, DD 22%/12%) -- that is the sanity baseline;
the true-aligned numbers are the adjudication input.

Run:  uv run python -m experiments.avsl.grid_alignment_check
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SPLIT_FRAC,
    block_bootstrap_ci,
    collect_trades,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)


def main() -> None:
    repo = repo_root()
    per = {s: collect_trades(s, repo) for s in ASSETS}
    g0_min = min(d["g0"] for d in per.values())
    n_g = max(d["n_bars"] + d["g0"] for d in per.values()) - g0_min
    split = int(n_g * SPLIT_FRAC)
    sizes_by = {s: s1_sizes(resample_4h(*read_1h(repo, s))[3])
                for s in ASSETS}
    trades: list[dict] = []
    for s, d in per.items():
        off = d["g0"] - g0_min
        for tr in d["trades"]:
            trades.append({**tr, "sym": s,
                           "ge0": tr["e0"] + off,
                           "ge1": tr["e1"] + off})
    print(f"[align-check] trades={len(trades)} grid n={n_g} "
          f"split={split}", flush=True)
    leg = np.zeros(n_g + 1)
    tru = np.zeros(n_g + 1)
    for tr in trades:
        w = sizes_by[tr["sym"]][tr["e0"]] * tr["net"]
        h0 = max(tr["e1"] - tr["e0"], 1)
        leg[tr["e0"]:tr["e1"] + 1] += w / (h0 + 1)
        h1 = max(tr["ge1"] - tr["ge0"], 1)
        tru[tr["ge0"]:tr["ge1"] + 1] += w / (h1 + 1)
    leg, tru = leg[:n_g], tru[:n_g]
    print(f"{'':>7}  {'LEGACY (frozen convention)':<34}"
          f"TRUE (global grid)", flush=True)
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        sl, st = leg[lo:hi], tru[lo:hi]
        seg_tr_l = [t for t in trades if lo <= t["e0"] < hi]
        seg_tr_t = [t for t in trades if lo <= t["ge0"] < hi]
        row = []
        for stream, seg_tr in ((sl, seg_tr_l), (st, seg_tr_t)):
            ev = float(np.mean([t["net"] for t in seg_tr]))
            lo_ci, _ = block_bootstrap_ci(stream)
            pos = sum(
                1 for s in ASSETS
                if (v := [t["net"] for t in seg_tr
                          if t["sym"] == s])
                and float(np.mean(v)) > 0)
            row.append(f"Sh {nw_sharpe(stream):+5.2f} "
                       f"DD {portfolio_dd(stream):4.0%} "
                       f"EV {ev:+.2f}R {pos}/10 "
                       f"CI[{lo_ci:+.4f}] n={len(seg_tr)}")
        print(f"{seg:>7}  {row[0]:<34}{row[1]}", flush=True)


if __name__ == "__main__":
    main()
