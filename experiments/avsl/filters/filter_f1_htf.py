# -*- coding: utf-8 -*-
"""F1 HTF-trend filter -- frozen prereg (STATUS 2026-09-25,
AVSL TREND-FILTER PROGRAM, F1 SPEC).  One pass.

Keeps AVSL-cross trades only in the direction of the completed
daily trend: long iff previous completed UTC daily close >
SMA50(50 completed daily closes), short iff <.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    RISK_PCT,
    SPLIT_FRAC,
    collect_trades,
    evaluate,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)

DAY = 86_400_000
SMA_N = 50
W12_BARS = 2190          # trailing 12m window in 4H bars (read-out)


def daily_closes(ts: np.ndarray, cp: np.ndarray) -> tuple:
    """(day-bucket keys, last 1H close per UTC day)."""
    g = pl.DataFrame({"b": ts // DAY, "cp": cp}).group_by(
        "b", maintain_order=True).agg(pl.last("cp"))
    return (g["b"].to_numpy().astype(np.int64),
            g["cp"].to_numpy().astype(np.float64))


def sym_ctx(repo, sym: str) -> dict:
    """One asset: 4H grid, trade table, S1 sizes, daily closes."""
    ts1, hp1, lp1, cp1, vol1 = read_1h(repo, sym)
    ts4, _hp, _lp, cp4, _vol = resample_4h(ts1, hp1, lp1, cp1, vol1)
    d = collect_trades(sym, repo)
    dk, dc = daily_closes(ts1, cp1)
    return {"ts4": ts4, "sizes": s1_sizes(cp4), "dkeys": dk, "dc": dc,
            "g0": d["g0"], "n_bars": d["n_bars"], "trades": d["trades"]}


def f1_keep(c: dict, tr: dict) -> bool:
    """Frozen F1 rule (uses the entry bar close time only)."""
    t4 = tr["e0"]                     # dense 4H bucket grid
    m = int(c["ts4"][t4]) + MSEC_4H   # entry bar close time
    di = m // DAY - 1                 # last completed UTC day
    j = int(np.searchsorted(c["dkeys"], di, side="right")) - 1
    if j < SMA_N or c["dkeys"][j] != di:
        return False
    c_prev = c["dc"][j]
    sma = float(np.mean(c["dc"][j - SMA_N + 1:j + 1]))
    return bool(c_prev > sma) if tr["long"] else bool(c_prev < sma)


def stream_metrics(ctxs: dict, trades: list) -> dict:
    """Rebuild the frozen portfolio stream with the given trades."""
    from engine.passed.avsl_cross_s1 import nw_sharpe, portfolio_dd
    g0 = min(c["g0"] for c in ctxs.values())
    n_g = max(c["n_bars"] + c["g0"] for c in ctxs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in sorted(trades, key=lambda t: (t["e0"], t["sym"])):
        c = ctxs[tr["sym"]]
        hold = max(tr["e1"] - tr["e0"], 1)
        w = c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    out = {"n_g": n_g, "split": split, "n": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades if lo <= t["e0"] < hi]
        pos = 0
        for sym in ASSETS:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        out[seg] = {
            "n": len(seg_tr),
            "sharpe_nw": nw_sharpe(s[lo:hi]),
            "dd": portfolio_dd(s[lo:hi]),
            "net_ev": (float(np.mean([t["net"] for t in seg_tr]))
                       if seg_tr else float("nan")),
            "pos_assets": pos,
        }
    return out


def neg_windows(ctxs: dict, trades: list) -> int:
    """PF-G4-style trailing 12m negative windows (read-out)."""
    g0 = min(c["g0"] for c in ctxs.values())
    n_g = max(c["n_bars"] + c["g0"] for c in ctxs.values()) - g0
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        hold = max(tr["e1"] - tr["e0"], 1)
        w = c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    eq = np.cumprod(1.0 + RISK_PCT * s[:n_g])
    if n_g <= W12_BARS:
        return 0
    lr = np.log(eq)
    r = np.lib.stride_tricks.sliding_window_view(lr, W12_BARS + 1)
    return int(np.sum(r[:, -1] - r[:, 0] < 0))


def main() -> None:
    repo = repo_root()
    print("== baseline recompute (sanity, must match frozen) ==")
    base = evaluate()
    for seg in ("PRIMARY", "F3"):
        m = base[seg]
        print(f"{seg:>7}: Sharpe={m['sharpe_nw']:+.2f} "
              f"DD={m['dd']:.0%} EV={m['net_ev']:+.2f}R "
              f"pos={m['pos_assets']}/10 n={m['n']}")
    ok = (abs(base["PRIMARY"]["net_ev"] - 0.17) < 0.05
          and abs(base["F3"]["net_ev"] - 0.33) < 0.05)
    print(f"sanity vs frozen EV 0.17/0.33: "
          f"{'OK' if ok else 'DEVIATION - ABORT'}")
    if not ok:
        return

    ctxs = {sym: sym_ctx(repo, sym) for sym in ASSETS}
    data = {"base": [], "filt": []}
    for sym in ASSETS:
        for tr in ctxs[sym]["trades"]:
            data["base"].append({**tr, "sym": sym})
            if f1_keep(ctxs[sym], tr):
                data["filt"].append({**tr, "sym": sym})

    nb, nf = len(data["base"]), len(data["filt"])
    print(f"\n== F1 ==\ntrades: base {nb} -> filtered {nf} "
          f"({nf / nb:.0%} kept)")
    mb = stream_metrics(ctxs, data["base"])
    mf = stream_metrics(ctxs, data["filt"])
    gates = []
    for seg in ("PRIMARY", "F3"):
        b, f = mb[seg], mf[seg]
        dd_ok = f["dd"] <= 0.8 * b["dd"]
        ev_ok = f["net_ev"] >= 0.9 * b["net_ev"]
        g4_ok = f["pos_assets"] >= 7
        gates.append(dd_ok and ev_ok and g4_ok)
        print(f"{seg:>7}: base DD={b['dd']:.0%} EV={b['net_ev']:+.2f}R "
              f"| F1 DD={f['dd']:.0%} EV={f['net_ev']:+.2f}R "
              f"Sharpe={f['sharpe_nw']:+.2f} pos={f['pos_assets']}/10 "
              f"n={f['n']}")
        print(f"        gate: DD<=0.8x base {'PASS' if dd_ok else 'FAIL'}"
              f"; EV>=0.9x base {'PASS' if ev_ok else 'FAIL'}; "
              f"G4>=7 {'PASS' if g4_ok else 'FAIL'}")
    print(f"neg 12m windows: base {neg_windows(ctxs, data['base'])} "
          f"-> F1 {neg_windows(ctxs, data['filt'])}")
    print(f"F1 VERDICT: {'PASS' if all(gates) else 'FAIL'}")


if __name__ == "__main__":
    main()
