# -*- coding: utf-8 -*-
"""Step 1 of the OB engineering plan (STATUS, backlog -> activated):
measure WHICH filter of the "4h" live preset kills the block count
on the 4H grid.  Diagnostic only -- no presets are defined here.

Each variant is the frozen "4h" preset with ONE field changed
(ablation); "base_loose" turns the three heavy quality filters off
at once.  Detector logic is untouched.  The committed port_check_4h
reference (BTC '4h'=10, BTC '1h'=131) stays frozen; metrics here are
computed the same way (width vs ATR14 at break bar, delay in 4H
bars).

Run:  uv run python -m experiments.ob.detector.filter_ablation
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import dataclasses

import numpy as np

from engine.passed.avsl_cross_s1 import repo_root
from experiments.ob.detector.port_check_4h import _df_4h
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import (
    OrderBlockConfig,
    get_order_block_config,
)
from ta.src.volatility.atr import atr_ind


VARIANTS: list[tuple[str, dict]] = [
    ("R3c close-entry",
     {"use_market_structure_filter": False,
      "require_complete_window": False,
      "min_extreme_gap": 0,
      "breakout_volume_threshold": 0.0,
      "reversal_atr_multiple": 0.8,
      "multiple_breakouts": True,
      "zone_entry_mode": "close"}),
    ("R3d fixed lookback",
     {"use_market_structure_filter": False,
      "require_complete_window": False,
      "min_extreme_gap": 0,
      "breakout_volume_threshold": 0.0,
      "reversal_atr_multiple": 0.8,
      "multiple_breakouts": True,
      "use_dynamic_lookback": False}),
]

TF_MS = 4 * 3_600_000


def _run(df, cfg: OrderBlockConfig) -> dict:
    blocks = identify_order_blocks(df, cfg=cfg)
    n = blocks.height
    ts = df["date"].dt.epoch(time_unit="ms").to_numpy().astype(np.int64)
    hp = df["high"].to_numpy().astype(np.float64)
    lp = df["low"].to_numpy().astype(np.float64)
    cp = df["close"].to_numpy().astype(np.float64)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    b = ts // TF_MS
    pos = {d: i for i, d in enumerate(df["date"].to_list())}
    widths, delays, ns, nd = [], [], 0, 0
    for row in blocks.iter_rows(named=True):
        i_b, i_r = pos.get(row["break"]), pos.get(row["retest"])
        if i_b is None or i_r is None:
            continue
        ns += row["block_type"] == "supply"
        nd += row["block_type"] == "demand"
        if np.isfinite(atr[i_b]) and atr[i_b] > 0:
            widths.append((row["zone_high"] - row["zone_low"])
                          / atr[i_b])
        delays.append(b[i_r] - b[i_b])
    w = np.array(widths)
    d = np.array(delays)
    return {
        "n": n, "w_med": float(np.median(w)) if w.size else float("nan"),
        "d_med": float(np.median(d)) if d.size else float("nan"),
        "d_p90": (float(np.percentile(d, 90)) if d.size else float("nan")),
        "sd": f"{ns}/{nd}",
    }


def main() -> None:
    base = get_order_block_config("4h")
    live = {f.name: getattr(base, f.name)
            for f in dataclasses.fields(OrderBlockConfig)}
    print("frozen '4h' preset heavy fields:")
    for k in ("zigzag_distance", "min_extreme_gap",
              "reversal_atr_multiple", "use_market_structure_filter",
              "require_complete_window", "strength_age_penalty",
              "use_adx_filter"):
        print(f"  {k} = {live[k]!r}")
    print(flush=True)

    repo = repo_root()
    for sym in ("BTC", "ETH"):
        df = _df_4h(sym, repo)
        print(f"== {sym} 4H ({df.height} bars) ==", flush=True)
        print(f"  {'variant':32s} {'blocks':>6} {'wATR':>6} "
              f"{'dMed':>5} {'dP90':>5}  S/D", flush=True)
        for name, over in VARIANTS:
            cfg = dataclasses.replace(base, **over)
            r = _run(df, cfg)
            print(f"  {name:32s} {r['n']:>6} {r['w_med']:>6.2f} "
                  f"{r['d_med']:>5.0f} {r['d_p90']:>5.0f}  {r['sd']}",
                  flush=True)
    print("\nABLATION DONE", flush=True)


if __name__ == "__main__":
    main()
