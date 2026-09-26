# -*- coding: utf-8 -*-
"""B1 Wave-5 events: short strangle T-1 -> T+1 (one-shot).
Prereg: OPTIONS_MAP app.2 B1.  Filter IV pct > 50.  Gates
G-EV1/2/3/4.  Output: runs/wave5_events.log
"""

from __future__ import annotations

__version__ = "1.0.0"

import datetime as dt
import json
import math

import numpy as np

from experiments.options._pricing import bs
from experiments.options._runner import (MSEC_DAY, HAIRCUT, NOTIONAL,
                                         leg_specs, load_ctx,
                                         skew_put, entry_iv,
                                         instrument_name)


def main() -> None:
    ctx = load_ctx()
    cal = json.loads((ctx["out"].parent.parent
                      / "data/events/event_calendar_2021_2026.json"
                      ).read_text())["events"]
    specs = leg_specs(ctx)
    ts1 = ctx["ts1"]

    def dvol(t: float) -> float:
        return ctx["dvol"](t)

    def spot(t: float) -> float:
        return ctx["spot"](t)

    # unique expiries sorted
    exps = sorted({nxt for (_, nxt, _, _) in specs})

    trades = []
    n_skip_iv = n_skip_filter = 0
    for e in cal:
        et, etype, name = e["ts"], e["type"], e["name"]
        t_in = et - MSEC_DAY
        t_out = et + MSEC_DAY
        if t_in < ts1[0] or t_out > ts1[-1]:
            continue
        nxt = min([x for x in exps if x > et], default=None)
        if nxt is None or (nxt - et) < 2 * MSEC_DAY:
            continue  # событие на экспирации -- пропускаем
        if ctx["pct_at"](t_in) <= 0.5:
            n_skip_filter += 1
            continue
        s_in = spot(t_in)
        legs = []
        ok = True
        for otype, tgt in (("put", 0.90), ("call", 1.10)):
            ks = sorted({m["strike"] for m in ctx["subset"].values()
                         if m["option_type"] == otype
                         and m["expiration_timestamp"] == nxt})
            k = min(ks, key=lambda x: abs(x - tgt * s_in)) if ks else None
            iv = entry_iv(ctx, instrument_name(nxt, k, otype == "call"),
                          t_in) if k else None
            if iv is None:
                ok = False
                break
            legs.append((k, otype, iv))
        if not ok:
            n_skip_iv += 1
            continue
        s_out = spot(t_out)
        pnl = 0.0
        for k, otype, iv in legs:
            is_call = otype == "call"
            ttm_in = (nxt - t_in) / (365 * MSEC_DAY)
            ttm_out = max((nxt - t_out) / (365 * MSEC_DAY), 0.0)
            p_in = bs(s_in, k, ttm_in, iv, is_call)
            sk = skew_call_local(ctx, k / s_out, is_call)
            mark_out = bs(s_out, k, ttm_out, dvol(t_out) + sk, is_call)
            cash_in = p_in * (1 - HAIRCUT)
            liab_out = mark_out * (1 + HAIRCUT)
            pnl += (cash_in - liab_out) / s_in * NOTIONAL * 100.0
        crush = dvol(t_out) - dvol(t_in)
        trades.append(dict(ts=t_in, etype=etype, pnl=pnl, crush=crush))

    log = [f"wave5_events v{__version__} -- one-shot",
           f"events considered {len(cal)}, traded {len(trades)}, "
           f"skip IV-filter {n_skip_filter}, skip no-prints {n_skip_iv}"]
    pnls = np.array([t["pnl"] for t in trades])
    if len(trades) < 5:
        log.append("INSUFFICIENT")
    else:
        mu, sd = float(pnls.mean()), float(pnls.std())
        sharpe = mu / sd * math.sqrt(12) if sd > 0 else 0.0
        tstat = mu / sd * math.sqrt(len(pnls)) if sd > 0 else 0.0
        eq = np.cumprod(1 + pnls / 100)
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
        log.append(f"per-event pnl: mean {mu:+.2f}% median "
                   f"{np.median(pnls):+.2f}% t={tstat:+.2f} "
                   f"Sharpe(ann x12) {sharpe:+.2f} DD {dd:.1%}")
        crush = np.array([t["crush"] for t in trades])
        log.append(f"IV crush: mean {crush.mean():+.1f}pt "
                   f"share<0 {np.mean(crush < 0):.0%}")
        for etype in sorted({t["etype"] for t in trades}):
            sel = np.array([t["etype"] == etype for t in trades])
            log.append(f"  {etype:8s}: n={sel.sum():3d} "
                       f"mean {pnls[sel].mean():+.2f}% "
                       f"share>0 {np.mean(pnls[sel] > 0):.0%}")
        g1 = sharpe >= 1.0
        g2 = dd <= 0.20
        g3 = len(trades) >= 30
        pos = {et_: float(pnls[np.array([t["etype"] == et_
                                          for t in trades])].mean())
               for et_ in {t["etype"] for t in trades}}
        g4 = sum(1 for v in pos.values() if v > 0) >= 2
        log += [f"G-EV1 Sharpe>=1.0: {'PASS' if g1 else 'FAIL'}",
                f"G-EV2 DD<=20%: {'PASS' if g2 else 'FAIL'}",
                f"G-EV3 n>=30: {'PASS' if g3 else 'FAIL'}",
                f"G-EV4 EV>0 on 2/3 types: {'PASS' if g4 else 'FAIL'} "
                f"{pos}",
                f"VERDICT: {'PASS' if all([g1, g2, g3, g4]) else 'FAIL'}"]

    out = ctx["out"].parent.parent / "runs/wave5_events.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


def skew_call_local(ctx: dict, m: float, is_call: bool) -> float:
    from experiments.options._runner import skew_call
    if not is_call:
        return skew_put(m)
    return skew_call(m, {})


if __name__ == "__main__":
    main()
