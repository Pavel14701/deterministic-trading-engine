# -*- coding: utf-8 -*-
"""Mirror diagnostic: avsl_trailing_s1 with inverted entry
direction (STATUS 2026-09-25).  Descriptive; no gates."""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    WARMUP,
    nw_sharpe,
    portfolio_dd,
    repo_root,
    s1_sizes,
)
from engine.passed.avsl_trailing_s1 import (
    SPLIT_FRAC,
    build_env,
    trade_revcross,
)


def main() -> None:
    repo = repo_root()
    envs, ctxs, trades = {}, {}, []
    for sym in ASSETS:
        env = build_env(sym, repo)
        envs[sym] = env
        ctxs[sym] = {"g0": env["g0"], "n_bars": env["n_bars"],
                     "sizes": s1_sizes(env["cp"])}
        entry_idx = env["cross_idx"]
        is_longs = env["up"][entry_idx - 1]
        for t, is_long in zip(entry_idx, is_longs):
            if t < WARMUP:
                continue
            tr = trade_revcross(env, int(t), not bool(is_long))  # MIRROR
            if tr is not None:
                tr["sym"] = sym
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))

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
    print(f"mirror trades: {len(trades)}")
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in seg_tr])
        v = s[lo:hi]
        pos = sum(1 for sym in ASSETS
                  if any(t["sym"] == sym for t in seg_tr)
                  and np.mean([t["net"] for t in seg_tr
                               if t["sym"] == sym]) > 0)
        print(f"{seg:>7}: Sharpe_NW={nw_sharpe(v):+.2f} "
              f"plain={v.mean() / v.std() * np.sqrt(6 * 365):+.2f} "
              f"DD={portfolio_dd(v):.0%} EV={r.mean():+.2f}R "
              f"win%={np.mean(r > 0):.0%} pos={pos}/10 n={len(r)}")
    import datetime as dt
    yr: dict[int, list] = {}
    for tr in trades:
        y = dt.datetime.utcfromtimestamp(
            (ctxs[tr["sym"]]["g0"] + tr["e0"]) * 14_400_000
            / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("per-year net EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})


if __name__ == "__main__":
    main()
