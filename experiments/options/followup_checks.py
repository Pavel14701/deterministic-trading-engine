# -*- coding: utf-8 -*-
"""Blocking checks before any prereg (one-shot):
C2-A year split of extreme-flow signal; C2-B RV control;
B1 precondition: DVOL crush around all 111 events;
D1 cost math for the IV-spread trade.
Output: runs/followup_checks.log
"""
from __future__ import annotations


__version__ = "1.0.0"
import datetime as dt
import json
import math

import numpy as np

from experiments.options._pricing import bs, bs_greeks
from experiments.options._runner import MSEC_DAY, load_ctx


H = 86_400_000


def main():
    ctx = load_ctx()
    log = [f"followup_checks v{__version__} -- one-shot"]

    # ---------- C2: rebuild hourly flow ----------
    hourly: dict[int, float] = {}
    for name, meta in sorted(ctx["subset"].items()):
        try:
            tr = json.loads((ctx["out"] / "strangle_trades"
                             / f"{name}.json").read_text()
                            )["result"]["trades"]
        except Exception:
            continue
        ic = meta["option_type"] == "call"
        for x in tr:
            d = x.get("direction")
            amt = float(x.get("amount") or 0)
            if d not in ("buy", "sell") or amt <= 0:
                continue
            sgn = (1 if d == "buy" else -1) * (1 if ic else -1)
            hourly[x["timestamp"] // H] = \
                hourly.get(x["timestamp"] // H, 0.0) + sgn * amt

    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    ph: dict[int, float] = {}
    for t, c in zip(ts1, cp1):
        ph[int(t // H)] = float(c)
    hours = sorted(ph)
    fwd, frv = {}, {}
    for i in range(len(hours) - 24):
        h = hours[i]
        fwd[h] = (ph[hours[i + 24]] / ph[h] - 1) * 100
        r = [math.log(ph[hours[i + k + 1]] / ph[hours[i + k]])
             for k in range(24)]
        frv[h] = float(np.std(r) * math.sqrt(365 * 24) * 100)

    rows = []
    for h, f in hourly.items():
        if h in fwd:
            rows.append((h, f, fwd[h], frv.get(h, float("nan"))))
    x = np.array([r[1] for r in rows])
    y = np.array([r[2] for r in rows])
    yrs = np.array([dt.datetime.utcfromtimestamp(
        r[0] * H / 1000).year for r in rows])
    q90, q10 = np.quantile(x, [0.9, 0.1])
    hi, lo = x >= q90, x <= q10

    log.append("")
    log.append("[C2-A] extreme-flow year split (top10 vs bottom10)")
    for yy in sorted(set(yrs)):
        m = yrs == yy
        h_, l_ = hi & m, lo & m
        if h_.sum() >= 3 and l_.sum() >= 3:
            log.append(f"  {yy}: n(hi/lo) {h_.sum()}/{l_.sum()} "
                       f"EV hi {y[h_].mean():+.2f}% lo {y[l_].mean():+.2f}% "
                       f"spread {y[h_].mean() - y[l_].mean():+.2f}%")
        else:
            log.append(f"  {yy}: n(hi/lo) {h_.sum()}/{l_.sum()} "
                       f"-- недостаточно")

    log.append("")
    log.append("[C2-B] RV control")
    rv = np.array([r[3] for r in rows])
    from scipy.stats import spearmanr
    okr = np.isfinite(rv)
    log.append(f"spearman(flow, fwd RV24) = "
               f"{spearmanr(x[okr], rv[okr]).statistic:+.3f} (n={okr.sum()})")
    rqs = np.quantile(rv[okr], [1 / 3, 2 / 3])
    for lab, m in (("RV lo", rv <= rqs[0]), ("RV mid",
                   (rv > rqs[0]) & (rv <= rqs[1])), ("RV hi", rv > rqs[1])):
        m2 = m & okr
        h_, l_ = hi & m2, lo & m2
        if h_.sum() >= 5 and l_.sum() >= 5:
            log.append(f"  {lab:7s}: EV hi {y[h_].mean():+.2f}% "
                       f"lo {y[l_].mean():+.2f}% "
                       f"spread {y[h_].mean() - y[l_].mean():+.2f}% "
                       f"(n {h_.sum()}/{l_.sum()})")

    # ---------- B1 precondition: DVOL crush on ALL events ----------
    log.append("")
    log.append("[B1-pre] DVOL crush T-1 -> T+1 on ALL events (no filter)")
    cal = json.loads((ctx["out"].parent.parent
                      / "data/events/event_calendar_2021_2026.json"
                      ).read_text())["events"]
    byt: dict[str, list] = {}
    for e in cal:
        t_in, t_out = e["ts"] - MSEC_DAY, e["ts"] + MSEC_DAY
        if t_in < ts1[0] or t_out > ts1[-1]:
            continue
        c = ctx["dvol"](t_out) - ctx["dvol"](t_in)
        byt.setdefault(e["type"], []).append(c)
    for t_, cs in sorted(byt.items()):
        cs = np.array(cs)
        log.append(f"  {t_:8s}: n={len(cs):3d} mean crush "
                   f"{cs.mean():+.2f}pt med {np.median(cs):+.2f}pt "
                   f"share<0 {np.mean(cs < 0):.0%}")
    allc = np.concatenate([np.array(v) for v in byt.values()])
    log.append(f"  ALL      : n={len(allc)} mean {allc.mean():+.2f}pt "
               f"share<0 {np.mean(allc < 0):.0%}")

    # ---------- D1 cost math ----------
    log.append("")
    log.append("[D1-cost] IV spread trade economics (frozen inputs)")
    days = 2011
    sp_med = -13.7
    reverts = {"z>2": 0.9, "z<-2": 1.9}
    s0 = float(np.median(ctx["cp1"]))
    iv = float(np.median([ctx["dvol"](t) for t in ts1[::240]]))
    ttm = 30 / 365
    prem = bs(s0, s0, ttm, iv, True)          # ATM 30d, per 1 BTC
    g = bs_greeks(s0, s0, ttm, iv, True)
    vega1 = g["vega"]                          # $ per 1 vol pt per 1 BTC
    hc = 0.25
    notion = 0.10
    log.append(f"  inputs: S~{s0:.0f}, IV~{iv:.0f}%, 30d ATM prem "
               f"{prem:.0f}$, vega {vega1:.1f}$/pt per BTC")
    cost_rt = 2 * hc * (prem + prem) * notion  # 2 legs x in/out
    log.append(f"  round-trip haircut cost (2 legs x0.10): "
               f"{cost_rt:.0f}$ = {cost_rt / s0 * 100:.2f}% equity")
    for lab, rev in reverts.items():
        pnl = rev * vega1 * notion * 2        # spread rev on 2 legs
        log.append(f"  {lab}: gross {pnl:.0f}$ vs cost {cost_rt:.0f}$ "
                   f"-> net {pnl - cost_rt:+.0f}$ "
                   f"({(pnl - cost_rt) / s0 * 100:+.2f}% equity)")

    out = ctx["out"].parent.parent / "runs/followup_checks.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
