# -*- coding: utf-8 -*-
"""F-TP1 reverse-cross exit -- frozen prereg (STATUS 2026-09-25,
AVSL TP-ABLATION PROGRAM, F-TP1 SPEC).  One pass.

Entry/stop/sizing identical to the passed module; exit = first
OPPOSITE cross bar (taken at its close), capped at HORIZON=500
(exact E3 arm-D semantics); stop checked intrabar and wins.
Gates: the module's full battery on BOTH segments AND PRIMARY
portfolio DD strictly below baseline.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    HORIZON,
    block_bootstrap_ci,
    evaluate,
    repo_root,
    s1_sizes,
)
from experiments.avsl.decomposition.ablation_entry import _env
from experiments.avsl.cross_confirm.avsl_cross_confirm import _nw_z
from experiments.avsl.filters.filter_f1_htf import neg_windows, stream_metrics

TAKER_FEE = 0.0005


def trade_revcross(env: dict, t: int, is_long: bool) -> dict | None:
    """E3-D exit walker; returns net/e0/e1/long."""
    hp, lp, cp = env["hp"], env["lp"], env["cp"]
    line, atr = env["line"], env["atr"]
    risk = max(abs(cp[t] - line[t]), 2.0 * atr[t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    n = len(cp)
    dirs = env["up"][env["cross_idx"] - 1]
    want_up = not is_long
    bars = env["cross_idx"][dirs == want_up]
    nxt = bars[bars > t]
    k_exit = int(min(nxt[0], t + HORIZON)) if nxt.size else -1
    if k_exit < 0:
        k_exit = n - 1
    pnl = 0.0
    hit = False
    e1 = k_exit
    for k in range(t + 1, min(k_exit + 1, n)):
        if is_long:
            if lp[k] <= stop:
                pnl, hit, e1 = -1.0, True, k
                break
        else:
            if hp[k] >= stop:
                pnl, hit, e1 = -1.0, True, k
                break
    if not hit:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": e1, "long": is_long}


def main() -> None:
    repo = repo_root()
    base = evaluate()
    ok = (abs(base["PRIMARY"]["net_ev"] - 0.17) < 0.05
          and abs(base["F3"]["net_ev"] - 0.33) < 0.05)
    print(f"baseline sanity: {'OK' if ok else 'DEVIATION - ABORT'}")
    if not ok:
        return
    print(f"baseline: PRIMARY Sharpe {base['PRIMARY']['sharpe_nw']:+.2f} "
          f"DD {base['PRIMARY']['dd']:.0%} EV {base['PRIMARY']['net_ev']:+.2f}R"
          f" | F3 Sharpe {base['F3']['sharpe_nw']:+.2f} "
          f"DD {base['F3']['dd']:.0%} EV {base['F3']['net_ev']:+.2f}R")

    ctxs = {}
    trades = []
    holds = []
    for sym in ASSETS:
        env = _env(sym, repo)
        from engine.passed.avsl_cross_s1 import resample_4h, read_1h
        _ts, _hp, _lp, cp4, _v = resample_4h(*read_1h(repo, sym))
        d = env
        entry_idx = d["cross_idx"]
        is_longs = d["up"][entry_idx - 1]
        ctx = {"g0": d["g0"], "n_bars": d["n_bars"],
               "sizes": s1_sizes(cp4)}
        ctxs[sym] = ctx
        for t, is_long in zip(entry_idx, is_longs):
            if t < 400:  # WARMUP
                continue
            tr = trade_revcross(d, int(t), bool(is_long))
            if tr is None:
                continue
            tr["sym"] = sym
            trades.append(tr)
            holds.append(tr["e1"] - tr["e0"])

    holds = np.array(holds)
    print(f"\n== F-TP1 ==\ntrades: {len(trades)} (frozen TP run had "
          f"2941) | hold bars: med {np.median(holds):.0f} "
          f"p90 {np.percentile(holds, 90):.0f}")
    mf = stream_metrics(ctxs, trades)
    gates = []
    for seg in ("PRIMARY", "F3"):
        b, f = base[seg], mf[seg]
        print(f"{seg:>7}: F-TP1 Sharpe={f['sharpe_nw']:+.2f} "
              f"DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"pos={f['pos_assets']}/10 n={f['n']}")
        g1 = f["sharpe_nw"] >= 1.0
        g2 = f["dd"] <= 0.25
        g3 = f["net_ev"] >= 0.10
        g4 = f["pos_assets"] >= 7
        gates.append(g1 and g2 and g3 and g4)
        print(f"        battery: Sharpe>=1 {'PASS' if g1 else 'FAIL'}"
              f"; DD<=25% {'PASS' if g2 else 'FAIL'}; EV>=0.10R "
              f"{'PASS' if g3 else 'FAIL'}; pos>=7 "
              f"{'PASS' if g4 else 'FAIL'}")
    dd_relief = mf["PRIMARY"]["dd"] < base["PRIMARY"]["dd"]
    print(f"PRIMARY DD relief ({base['PRIMARY']['dd']:.0%} -> "
          f"{mf['PRIMARY']['dd']:.0%}): "
          f"{'PASS' if dd_relief else 'FAIL'}")
    gates.append(dd_relief)
    print(f"neg 12m windows: F-TP1 {neg_windows(ctxs, trades)}")
    # per-year net EV read-out (trade entry year via the global grid)
    import datetime as dt
    g0 = min(c["g0"] for c in ctxs.values())
    yr: dict[int, list] = {}
    for tr in trades:
        y = dt.datetime.utcfromtimestamp(
            (g0 + tr["e0"]) * 14_400_000 / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("per-year net EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})
    print(f"F-TP1 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
