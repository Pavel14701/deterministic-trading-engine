# -*- coding: utf-8 -*-
"""P-L1 long-only avsl_trailing_s1 -- prereg run (STATUS
2026-09-25).  One pass."""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    block_bootstrap_ci,
    nw_sharpe,
    portfolio_dd,
    repo_root,
)
from engine.passed.avsl_trailing_s1 import SPLIT_FRAC, collect_all


def main() -> None:
    repo = repo_root()
    _envs, ctxs, all_tr = collect_all(ASSETS, repo)
    trades = [t for t in all_tr if t["long"]]
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        hold = max(e1 - e0, 1)
        s[e0:e1 + 1] += c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
    print(f"P-L1 long-only: trades {len(trades)} (promoted module: "
          f"{len(all_tr)})")
    gates = True
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in seg_tr])
        v = s[lo:hi]
        pos = sum(1 for sym in ASSETS
                  if [t["net"] for t in seg_tr if t["sym"] == sym]
                  and np.mean([t["net"] for t in seg_tr
                               if t["sym"] == sym]) > 0)
        sh, dd, ev = nw_sharpe(v), portfolio_dd(v), float(r.mean())
        lo_ci, hi_ci = block_bootstrap_ci(v)
        rd = np.sort(r)[::-1]
        g = (sh >= 1.0 and dd <= 0.25 and ev >= 0.10 and pos >= 7
             and lo_ci > 0)
        gates &= g
        print(f"{seg:>7}: Sharpe_NW={sh:+.2f} DD={dd:.0%} EV={ev:+.2f}R "
              f"pos={pos}/10 CI=[{lo_ci:+.5f},{hi_ci:+.5f}] n={len(r)} "
              f"| gates {'PASS' if g else 'FAIL'}")
        print(f"         ex-top20 EV {rd[20:].mean():+.3f}R (top20 share "
              f"{rd[:20].sum() / r.sum():.0%})")
    yr: dict[int, list] = {}
    for tr in trades:
        y = dt.datetime.utcfromtimestamp(
            (ctxs[tr["sym"]]["g0"] + tr["e0"]) * 14_400_000 / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("per-year net EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})
    print(f"P-L1 VERDICT: {'PASS' if gates else 'FAIL'}")


if __name__ == "__main__":
    main()
