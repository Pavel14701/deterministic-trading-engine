# -*- coding: utf-8 -*-
"""C2 options taker flow -- read-out (one-shot, no gates yet).
Prereg-sketch in OPTIONS_MAP app.2 C2: extreme flow -> direction.
Data: strangle_subset trades (direction, iv, amount, price).
Output: runs/opt_flow_readout.log
"""

from __future__ import annotations

__version__ = "1.0.0"

import json

import numpy as np

from experiments.options._runner import load_ctx

H = 86_400_000


def main() -> None:
    ctx = load_ctx()
    log = [f"opt_flow_readout v{__version__} -- one-shot read-out"]

    # signed taker flow: buy +1 / sell -1, in BTC notional (amount)
    hourly: dict[int, float] = {}
    n_tr = 0
    for name, meta in sorted(ctx["subset"].items()):
        p = ctx["out"] / "strangle_trades" / f"{name}.json"
        try:
            tr = json.loads(p.read_text())["result"]["trades"]
        except Exception:
            continue
        is_call = meta["option_type"] == "call"
        for x in tr:
            d = x.get("direction")
            if d not in ("buy", "sell"):
                continue
            amt = float(x.get("amount") or 0)
            if amt <= 0:
                continue
            sgn = (1 if d == "buy" else -1) * (1 if is_call else -1)
            # call-buys positive, put-buys negative => net "risk appetite"
            hourly[x["timestamp"] // H] = \
                hourly.get(x["timestamp"] // H, 0.0) + sgn * amt
            n_tr += 1

    hs = np.array(sorted(hourly))
    fl = np.array([hourly[h] for h in hs])
    log.append(f"trades {n_tr}, hours with flow {len(hs)}")

    # daily aggregation
    day = hs // (H // H)
    dflow: dict[int, float] = {}
    for h, f in zip(hs, fl):
        dflow[h * H] = dflow.get(h * H, 0.0) + f  # keep hourly buckets

    # forward 24h return after each hour
    ts1, cp1 = ctx["ts1"], ctx["cp1"]
    px: dict[int, float] = {}
    for t, c in zip(ts1, cp1):
        px[int(t // H)] = float(c)
    fwd: dict[int, float] = {}
    hours = sorted({int(t // H) for t in ts1})
    for i in range(len(hours) - 24):
        fwd[hours[i]] = (px[hours[i + 24]] / px[hours[i]] - 1) * 100

    pairs = [(fl[i], fwd.get(int(hs[i]))) for i in range(len(hs))
             if int(hs[i]) in fwd]
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    from scipy.stats import spearmanr
    rho = float(spearmanr(x, y).statistic)
    log.append(f"IC(net flow, fwd 24h ret) = {rho:+.3f} (n={len(x)})")

    for q, lab in ((0.9, "top10 buy-flow"), (0.1, "bottom10 sell-flow")):
        thr = np.quantile(x, q)
        sel = (x >= thr) if q > 0.5 else (x <= thr)
        log.append(f"  {lab:18s}: n={sel.sum():5d} fwd24h mean "
                   f"{y[sel].mean():+.2f}% median {np.median(y[sel]):+.2f}%")

    # regime split: high vs low DVOL
    dv = np.array([ctx["dvol"](h * H) for h in hs])
    med = np.median(dv)
    for lab, m in (("DVOL<med", dv <= med), ("DVOL>med", dv > med)):
        idx = np.where(m & np.isin(hs, hs[[p[1] is not None
                                           for p in pairs]]))[0]
        ys = np.array([fwd.get(int(h)) for h in hs[idx]
                       if fwd.get(int(h)) is not None])
        xs2 = np.array([f for f, h in zip(fl[idx], hs[idx])
                        if fwd.get(int(h)) is not None])
        r = float(spearmanr(xs2, ys).statistic) if len(xs2) > 10 else float("nan")
        log.append(f"  {lab:9s}: IC {r:+.3f} (n={len(xs2)})")

    out = ctx["out"].parent.parent / "runs/opt_flow_readout.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
