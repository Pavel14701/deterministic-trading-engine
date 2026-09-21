"""Maker-entry grid: maker-or-skip vs always-market execution.

Limit at fill-delta*ATR into the zone, wait W bars, skip if unfilled;
baseline = market entry on the same gated WF-B signals.  Metric: mean
pess R per signal.  Saves runs/maker_entry.json.
"""
from __future__ import annotations

import json

from typing import Any

import numpy as np
import polars as pl

from engine.features.mtf import resample_ohlcv
from engine.sim.maker import MAKER_FRAC, maker_sim, market_sim
from experiments import REPO


GRID_DELTA = (0.0, 0.1, 0.25, 0.5)     # x ATR into the zone
GRID_WAIT = (1, 4, 12)                 # bars to wait for a fill


def main() -> None:
    """Maker-entry grid experiment (saves runs/maker_entry.json)."""
    pk = pl.read_parquet(REPO / "runs" / "d8b" / "wf_picks.parquet")
    print("signals:", pk.height)
    data: dict[str, dict[str, Any]] = {}
    for t in sorted(pk["asset"].unique().to_list()):
        raw = resample_ohlcv(
            pl.read_parquet(REPO / f"data/okx/raw_{t}_1m.parquet"), "1h"
        )
        data[t] = {k: raw[k].to_numpy()
                   for k in ("open", "high", "low", "close")}
        data[t]["n"] = len(raw)

    rows = pk.to_dicts()
    base = np.array([market_sim(data[r["asset"]]["open"],
                                data[r["asset"]]["high"],
                                data[r["asset"]]["low"],
                                data[r["asset"]]["close"],
                                int(r["entry_idx"]) + 1, r["side"],
                                r["sl_price"], r["tp_price"], r["atr_i"])
                     for r in rows])
    base = base[np.isfinite(base)]
    print(f"baseline market-always: mean pess R per signal = "
          f"{base.mean():+.3f} (n={base.size})")

    results: dict[str, dict[str, float]] = {}
    for delta in GRID_DELTA:
        for wait in GRID_WAIT:
            contrib, filled_n = [], 0
            for r in rows:
                d = data[r["asset"]]
                sign = 1.0 if r["side"] == "long" else -1.0
                i0 = int(r["entry_idx"]) + 1
                limit = r["fill_price"] - sign * delta * r["atr_i"]
                if sign * (limit - r["sl_price"]) <= 0.05 * r["atr_i"]:
                    contrib.append(np.nan)
                    continue
                fill_bar = None
                for i in range(i0, min(i0 + wait, d["n"])):
                    hit = (d["low"][i] <= limit if sign > 0
                           else d["high"][i] >= limit)
                    if hit:
                        fill_bar = i
                        break
                if fill_bar is not None:
                    filled_n += 1
                    contrib.append(maker_sim(
                        d["open"], d["high"], d["low"], d["close"], fill_bar,
                        r["side"], r["sl_price"], r["tp_price"], limit,
                        r["atr_i"], MAKER_FRAC))
                else:
                    contrib.append(np.nan)  # maker-or-skip: missed signal = 0
            c_ = np.array([x for x in contrib if np.isfinite(x)])
            ev_skip = float(c_.mean() * len(contrib) / len(rows))
            results[f"delta{delta}_wait{wait}"] = {
                "fill_rate": filled_n / len(rows),
                "mean_given_fill": float(c_.mean()),
                "ev_per_signal_skip": ev_skip}
            print(f"delta={delta:.2f} wait={wait:2d}: "
                  f"fill={filled_n / len(rows):.0%} "
                  f"r|fill={c_.mean():+.3f} "
                  f"EV/signal(skip)={ev_skip:+.3f} "
                  f"vs market {base.mean():+.3f}", flush=True)

    best = max(results.items(), key=lambda kv: kv[1]["ev_per_signal_skip"])
    lift = best[1]["ev_per_signal_skip"] - base.mean()
    print(f"\nbest maker config: {best[0]} "
          f"EV/signal={best[1]['ev_per_signal_skip']:+.3f} "
          f"(market {base.mean():+.3f}, lift {lift:+.3f})")
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "maker_entry.json").write_text(json.dumps(
        {"baseline_market": float(base.mean()), "n_signals": int(base.size),
         "grid": results, "best": best[0], "lift": float(lift)}, indent=1))
    print("saved runs/maker_entry.json")


if __name__ == "__main__":
    main()