# -*- coding: utf-8 -*-
"""Why shorts are dead: four-hypothesis discrimination
(STATUS 2026-09-25).  Descriptive; no gates."""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import ASSETS, WARMUP, repo_root
from engine.passed.avsl_trailing_s1 import build_env, trade_revcross

HS = (1, 4, 12, 48, 168)


def main() -> None:
    repo = repo_root()
    up_rets = {h: [] for h in HS}
    dn_rets = {h: [] for h in HS}
    all_rets = {h: [] for h in HS}
    up_mfe, dn_mfe, up_mae, dn_mae = [], [], [], []
    holds = {"long": [], "short": []}
    wins = {"long": [], "short": []}

    for sym in ASSETS:
        env = build_env(sym, repo)
        cp, hp, lp, line, atr = (env["cp"], env["hp"], env["lp"],
                                 env["line"], env["atr"])
        n = len(cp)
        risk = np.maximum(np.abs(cp - line), 2.0 * atr)
        # (a) unconditional control on every bar with a full window
        for h in HS:
            ok = np.arange(n - h)
            all_rets[h].append(cp[ok + h] / cp[ok] - 1.0)
        for t, up in zip(env["cross_idx"], env["up"][env["cross_idx"] - 1]):
            t = int(t)
            if t < WARMUP:
                continue
            for h in HS:
                if t + h >= n:
                    continue
                r = cp[t + h] / cp[t] - 1.0
                (up_rets if up else dn_rets)[h].append(np.array([r]))
            # (b) MFE/MAE in R units over H=48
            if t + 48 < n and np.isfinite(risk[t]) and risk[t] > 0:
                hi = hp[t + 1:t + 49].max()
                lo = lp[t + 1:t + 49].min()
                up_mfe.append((hi - cp[t]) / risk[t] if up else np.nan)
                up_mae.append((lo - cp[t]) / risk[t] if up else np.nan)
                dn_mfe.append((cp[t] - lo) / risk[t] if not up else np.nan)
                dn_mae.append((cp[t] - hi) / risk[t] if not up else np.nan)
            # (c) walker trade for hold/tail
            tr = trade_revcross(env, t, bool(up))
            if tr is not None:
                side = "long" if up else "short"
                holds[side].append(tr["e1"] - tr["e0"])
                wins[side].append(tr["net"])

    print("== (a) forward-return sign / mean by cross direction ==")
    print("H(bars) | P(+|up) P(+|dn) P(+|all) | meanR bp: up dn all")
    for h in HS:
        u = np.concatenate(up_rets[h])
        d = np.concatenate(dn_rets[h])
        a = np.concatenate(all_rets[h])
        print(f"{h:>7} | {np.mean(u > 0):.3f} {np.mean(d > 0):.3f} "
              f"{np.mean(a > 0):.3f} | {np.mean(u) * 1e4:+.1f} "
              f"{np.mean(d) * 1e4:+.1f} {np.mean(a) * 1e4:+.1f}")

    print("\n== (b) MFE/MAE in R units, H=48 ==")
    for nm, mfe, mae in (("up-cross (long side)", up_mfe, up_mae),
                         ("dn-cross (short side)", dn_mfe, dn_mae)):
        m = np.array(mfe)[np.isfinite(np.array(mfe, dtype=float))]
        e = np.array(mae)[np.isfinite(np.array(mae, dtype=float))]
        print(f"{nm:>22}: MFE med {np.median(m):+.2f}R p90 "
              f"{np.percentile(m, 90):+.2f}R max {m.max():+.2f}R | "
              f"MAE med {np.median(e):+.2f}R p90 "
              f"{np.percentile(e, 90):+.2f}R")

    print("\n== (c) walker trades: hold & win tail by side ==")
    for side in ("long", "short"):
        h_ = np.array(holds[side])
        w_ = np.array(wins[side])
        print(f"{side:>5}: n={len(w_)} hold med {np.median(h_):.0f} "
              f"p90 {np.percentile(h_, 90):.0f} | EV {w_.mean():+.3f}R "
              f"win {np.mean(w_ > 0):.0%} p99 win {np.percentile(w_, 99):+.1f}R "
              f"max {w_.max():+.1f}R | top-20 share "
              f"{np.sort(w_)[::-1][:20].sum() / w_.sum():.0%}")


if __name__ == "__main__":
    main()
