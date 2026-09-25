# -*- coding: utf-8 -*-
"""F-TP1 promotion due-diligence checks (STATUS 2026-09-25,
CHK-1/2/3).  Descriptive; no gates.

CHK-1  true-grid streams for baseline (TP=5R) and F-TP1.
CHK-2  portfolio null for the trailing exit (E1/E3 procedure,
       seeds 0..99, matched counts/sides), true grid.
CHK-3  net-R distribution decomposition vs baseline.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SPLIT_FRAC,
    collect_trades,
    repo_root,
)
from engine.passed.avsl_cross_s1 import (
    read_1h,
    resample_4h,
    s1_sizes,
)
from experiments.avsl.ablation_entry import _env
from experiments.avsl.tp1_revcross import trade_revcross

WARMUP = 400
N_DRAWS = 100
MSEC_4H = 14_400_000


def true_stream(ctxs: dict, trades: list, shift: dict) -> dict:
    """Portfolio stream on the TRUE global grid."""
    from engine.passed.avsl_cross_s1 import nw_sharpe, portfolio_dd
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        hold = max(e1 - e0, 1)
        w = c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
        s[e0:e1 + 1] += w
    out = {"n_g": n_g, "split": split, "n": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        pos = 0
        for sym in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        out[seg] = {"n": len(seg_tr), "sharpe_nw": nw_sharpe(s[lo:hi]),
                    "dd": portfolio_dd(s[lo:hi]),
                    "net_ev": (float(np.mean([t["net"] for t in seg_tr]))
                               if seg_tr else float("nan")),
                    "pos_assets": pos}
    return out


def collect_all(repo) -> tuple:
    envs = {sym: _env(sym, repo) for sym in ASSETS}
    base_tr, ftp1_tr, ctxs = [], [], {}
    for sym in ASSETS:
        env = envs[sym]
        d = collect_trades(sym, repo)
        _ts, _hp, _lp, cp4, _v = resample_4h(*read_1h(repo, sym))
        ctxs[sym] = {"g0": d["g0"], "n_bars": d["n_bars"],
                     "sizes": s1_sizes(cp4)}
        for tr in d["trades"]:
            base_tr.append({**tr, "sym": sym})
        entry_idx = env["cross_idx"]
        is_longs = env["up"][entry_idx - 1]
        for t, is_long in zip(entry_idx, is_longs):
            if t < WARMUP:
                continue
            tr = trade_revcross(env, int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = sym
                ftp1_tr.append(tr)
    return envs, ctxs, base_tr, ftp1_tr


def main() -> None:
    repo = repo_root()
    print("== CHK-1: true-grid baseline vs F-TP1 ==", flush=True)
    envs, ctxs, base_tr, ftp1_tr = collect_all(repo)
    g0g = min(c["g0"] for c in ctxs.values())
    shifts = {s: ctxs[s]["g0"] - g0g for s in ASSETS}
    print("asset shifts (buckets):", {k: v for k, v in shifts.items() if v})
    mb = true_stream(ctxs, base_tr, shifts)
    mf = true_stream(ctxs, ftp1_tr, shifts)
    for seg in ("PRIMARY", "F3"):
        b, f = mb[seg], mf[seg]
        print(f"{seg:>7} TRUE: baseline Sharpe={b['sharpe_nw']:+.2f} "
              f"DD={b['dd']:.0%} EV={b['net_ev']:+.2f}R "
              f"pos={b['pos_assets']} | F-TP1 "
              f"Sharpe={f['sharpe_nw']:+.2f} DD={f['dd']:.0%} "
              f"EV={f['net_ev']:+.2f}R pos={f['pos_assets']}")

    print("\n== CHK-2: portfolio null, trailing exit "
          f"({N_DRAWS} draws) ==", flush=True)
    match = {}
    for sym in ASSETS:
        tr_s = [t for t in ftp1_tr if t["sym"] == sym]
        n = len(tr_s)
        match[sym] = {"n": n,
                      "p_long": (sum(1 for t in tr_s if t["long"])
                                 / max(n, 1))}
    res = {(seg, k): [] for seg in ("PRIMARY", "F3")
           for k in ("sharpe", "dd", "ev")}
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        draw = []
        for sym in ASSETS:
            m = match[sym]
            if m["n"] == 0:
                continue
            bars = rng.choice(
                np.arange(WARMUP, envs[sym]["n_bars"] - 1),
                size=m["n"], replace=False)
            for t in bars:
                is_long = bool(rng.random() < m["p_long"])
                tr = trade_revcross(envs[sym], int(t), is_long)
                if tr is not None:
                    tr["sym"] = sym
                    draw.append(tr)
        st = true_stream(ctxs, draw, shifts)
        for seg in ("PRIMARY", "F3"):
            res[(seg, "sharpe")].append(st[seg]["sharpe_nw"])
            res[(seg, "dd")].append(st[seg]["dd"])
            res[(seg, "ev")].append(st[seg]["net_ev"])
        if (seed + 1) % 25 == 0:
            print(f"  draw {seed + 1}/{N_DRAWS}", flush=True)
    for seg in ("PRIMARY", "F3"):
        sh = np.array(res[(seg, "sharpe")])
        dd = np.array(res[(seg, "dd")])
        ev = np.array(res[(seg, "ev")])
        f = mf[seg]
        pct = lambda v, x: float(np.mean(v < x)) * 100  # noqa: E731
        print(f"{seg:>7} NULL: Sharpe {sh.mean():+.2f}+-{sh.std():.2f} "
              f"[{sh.min():+.2f},{sh.max():+.2f}] | DD "
              f"{dd.mean():.0%}+-{dd.std():.0%} "
              f"[{dd.min():.0%},{dd.max():.0%}] | EV "
              f"{ev.mean():+.2f}+-{ev.std():.2f}")
        print(f"        F-TP1 percentile: Sharpe {pct(sh, f['sharpe_nw']):.0f}"
              f"th | DD(favourable) {pct(-dd, -f['dd']):.0f}th | EV "
              f"{pct(ev, f['net_ev']):.0f}th")

    print("\n== CHK-3: distribution decomposition (net R) ==")
    for name, trades in (("frozen TP=5R", base_tr),
                         ("F-TP1 revcross", ftp1_tr)):
        v = np.array([t["net"] for t in trades])
        wins = v[v > 0]
        losses = v[v <= 0]
        srt = np.sort(v)[::-1]
        top5 = srt[:max(len(srt) // 20, 1)].sum() / v.sum()
        print(f"{name:>15}: n={len(v)} win%={len(wins) / len(v):.0%} "
              f"p10 {np.percentile(v, 10):+.2f} med {np.median(v):+.2f} "
              f"p90 {np.percentile(v, 90):+.2f} max {v.max():+.2f} "
              f"min {v.min():+.2f}")
        print(f"                avg win {wins.mean():+.2f} avg loss "
              f"{losses.mean():+.2f} top-5% trades PnL share {top5:.0%}")
    g0g = min(c["g0"] for c in ctxs.values())
    yr = {}
    for tr in ftp1_tr:
        ts_ms = (ctxs[tr["sym"]]["g0"] + tr["e0"]) * MSEC_4H
        y = dt.datetime.utcfromtimestamp(ts_ms / 1000).year
        yr.setdefault(y, []).append(tr["net"])
    print("F-TP1 per-year net EV:",
          {y: round(float(np.mean(v)), 3) for y, v in sorted(yr.items())})


if __name__ == "__main__":
    main()
