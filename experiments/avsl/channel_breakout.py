# -*- coding: utf-8 -*-
"""AVS-CHANNEL breakout track (prereg frozen in STATUS
2026-09-24, BEFORE this run; AVS family attempt #3 of 3).

Signal: AVSL+AVSR volatility channel.  Enter on the TRANSITION
from inside [AVSL, AVSR] to outside: close > AVSR => long,
close < AVSL => short (state trigger, no re-entry while
outside).  Stop risk = max(distance to the opposite line,
2*ATR14); TP 5R, HORIZON 500, fee 10bp RT, stop-first
within-bar -- identical bookkeeping to the frozen cross
tracks.  Sizing battery S1..S4 and gates G1'..G5' byte-
equivalent to the frozen overlay; 0/4 pass closes the AVS
family finally.

Run:  python -m experiments.avsl.channel_breakout
"""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    K_STOP,
    MSEC_4H,
    TAKER_FEE,
    TP_PRIMARY,
    _sim_5r,
    fast_line,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsl.risk_overlay_mirror import (
    CONFIGS,
    PICK_ORDER,
    _apply_config,
    _gates,
    _sizing_inputs,
    avsr_line,
)
from ta.src.volatility.atr import atr_ind


def collect_channel_trades(sym: str) -> dict:
    """TP=5R channel-breakout trade table for one asset."""
    repo = repo_root()
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    avsl = fast_line(lp, cp, vol)
    avsr = avsr_line(hp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    ok = np.isfinite(avsl) & np.isfinite(avsr)
    inside = ok & (cp >= avsl) & (cp <= avsr)
    b = ts // MSEC_4H
    g0 = int(b[0])
    trades = []
    for t in range(1, len(cp)):
        if not (ok[t] and ok[t - 1] and inside[t - 1]) or inside[t]:
            continue
        is_long = bool(cp[t] > avsr[t])
        if is_long:
            risk = max(cp[t] - avsl[t], K_STOP * atr[t])
        else:
            risk = max(avsr[t] - cp[t], K_STOP * atr[t])
        if not np.isfinite(risk) or risk <= 0:
            continue
        stop = cp[t] - risk if is_long else cp[t] + risk
        fee_r = 2 * TAKER_FEE * cp[t] / risk
        pnl = _sim_5r(hp, lp, cp, int(t), is_long, float(stop))
        if pnl is None:
            continue
        n = len(cp)
        k_exit = min(int(t) + 500, n - 1)
        tp_px = cp[t] + TP_PRIMARY * risk if is_long \
            else cp[t] - TP_PRIMARY * risk
        for k in range(int(t) + 1, min(int(t) + 1 + 500, n)):
            if is_long:
                hit = lp[k] <= stop or hp[k] >= tp_px
            else:
                hit = hp[k] >= stop or lp[k] <= tp_px
            if hit:
                k_exit = k
                break
        trades.append({
            "net": pnl - fee_r,
            "gross": pnl,
            "fee": fee_r,
            "e0": int(b[t]) - g0,
            "e1": int(b[k_exit]) - g0,
            "long": is_long,
        })
    return {"trades": trades, "g0": g0, "n_bars": int(b[-1]) - g0 + 1}


def main() -> None:
    from engine.passed.avsl_cross_s1 import ASSETS

    data = {s: collect_channel_trades(s) for s in ASSETS}
    g0 = min(d["g0"] for d in data.values())
    n_g = max(d["n_bars"] + d["g0"] for d in data.values()) - g0
    split = int(n_g * 2 / 3)
    trs = []
    for s, d in data.items():
        for t in d["trades"]:
            trs.append({**t, "sym": s})
    trs.sort(key=lambda t: (t["e0"], t["sym"]))
    n_long = sum(1 for t in trs if t["long"])
    print(f"AVS-CHANNEL one-shot (attempt 3/3); grid n={n_g}, "
          f"PRIMARY<{split}<=F3, trades {len(trs)} "
          f"(long {n_long} / short {len(trs) - n_long})", flush=True)
    aux = {s: _sizing_inputs(s) for s in ASSETS}

    summary: dict = {}
    for name in CONFIGS:
        sized = _apply_config(name, trs, aux)
        kept = [t for t in sized if not t["skipped"]]
        print(f"\n=== {name}: skipped {len(sized) - len(kept)} "
              f"entries, kept {len(kept)} ===", flush=True)
        fails: list = []
        _gates(name, kept, len(sized), n_g, split, fails)
        summary[name] = (not fails, len(sized) - len(kept), len(kept))

    print("\n==== AVS-CHANNEL VERDICT (risk-first) ====", flush=True)
    passers = [c for c in CONFIGS if summary[c][0]]
    for c in CONFIGS:
        print(f"  {c}: {'PASS' if summary[c][0] else 'FAIL'} "
              f"(skipped {summary[c][1]}, kept {summary[c][2]})",
              flush=True)
    if not passers:
        print("0/4 configs pass -> AVS-CHANNEL CLOSED; AVS family "
              "budget exhausted (3/3), family CLOSED FINALLY",
              flush=True)
    else:
        pick = min(passers, key=lambda c: PICK_ORDER[c])
        print(f"passers: {passers} -> selected (most conservative): "
              f"{pick}", flush=True)


if __name__ == "__main__":
    main()
