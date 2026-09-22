# -*- coding: utf-8 -*-
"""Acceptance run for the RESEARCH presets (OB engineering plan,
step 3-4).  Frozen criteria (STATUS, 2026-09-22):

  A1  blocks/asset in [200, 2000] for R1/R2/R3 on ALL 10 assets
      (R4_diagnostic exempt -- it documents the structure-filter
      cost and must fail this floor);
  A2  zone width median in [1, 3] ATR14;
  A3  retest delay median <= 10 bars and p90 <= 36 bars;
  A4  each side (supply/demand) 30-70%;
  A5  determinism: byte-identical output on rerun;
  A6  regression: live "1h" preset -> 131 blocks (BTC 1H) and
      live "4h" preset -> 10 blocks (BTC 4H), unchanged.

Run:  uv run python -m experiments.ob.research_preset_check
"""

from __future__ import annotations

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.ob.research_presets import RESEARCH_PRESETS
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import (
    get_order_block_config,
)
from ta.src.volatility.atr import atr_ind


TF_MS = MSEC_4H


def _metrics(df: pl.DataFrame, cfg) -> dict:
    blocks = identify_order_blocks(df, cfg=cfg)
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
        "n": blocks.height,
        "w_med": float(np.median(w)) if w.size else float("nan"),
        "d_med": float(np.median(d)) if d.size else float("nan"),
        "d_p90": (float(np.percentile(d, 90)) if d.size else float("nan")),
        "s_frac": ns / max(ns + nd, 1),
        "raw": blocks,
    }


def _check(name: str, sym: str, r: dict, enforce: bool,
           fails: list[str]) -> None:
    loc: list[str] = []
    if enforce and not 200 <= r["n"] <= 2000:
        loc.append(f"A1 blocks={r['n']}")
    if not 1.0 <= r["w_med"] <= 3.0:
        loc.append(f"A2 width={r['w_med']:.2f}")
    if not (r["d_med"] <= 10 and r["d_p90"] <= 36):
        loc.append(f"A3 delay={r['d_med']:.0f}/{r['d_p90']:.0f}")
    if not 0.30 <= r["s_frac"] <= 0.70:
        loc.append(f"A4 S={r['s_frac']:.0%}")
    tag = " ".join(loc) if loc else "OK"
    if loc and enforce:
        fails.extend(f"{name}/{sym}: {x}" for x in loc)
    print(f"  {name:14s} {sym:5s} n={r['n']:>5}  w={r['w_med']:.2f}  "
          f"d={r['d_med']:.0f}/{r['d_p90']:.0f}  "
          f"S={r['s_frac']:.0%}  {tag}", flush=True)


def main() -> None:
    repo = repo_root()
    fails: list[str] = []

    # --- A6 regression on the live presets (frozen references) ---
    ts, hp, lp, cp, vol = read_1h(repo, "BTC")
    df1h = pl.DataFrame({
        "date": pl.from_epoch(ts, time_unit="ms"),
        "high": hp, "low": lp, "close": cp, "volume": vol,
    })
    n1h = identify_order_blocks(
        df1h, cfg=get_order_block_config("1h")).height
    df4h = pl.DataFrame({
        "date": pl.from_epoch(
            (ts // MSEC_4H) * MSEC_4H, time_unit="ms"),
        "high": hp, "low": lp, "close": cp, "volume": vol,
    }).group_by("date", maintain_order=True).agg(
        pl.max("high"), pl.min("low"), pl.last("close"),
        pl.sum("volume"))
    n4h = identify_order_blocks(
        df4h, cfg=get_order_block_config("4h")).height
    ok6 = n1h == 131 and n4h == 10
    print(f"A6 regression: '1h' BTC={n1h} (want 131), "
          f"'4h' BTC={n4h} (want 10) -> "
          f"{'OK' if ok6 else 'FAIL'}", flush=True)
    if not ok6:
        fails.append("A6 regression")

    # --- A1-A5 per asset x preset ---
    for sym in ASSETS:
        t4, h4, l4, c4, v4 = resample_4h(*read_1h(repo, sym))
        df = pl.DataFrame({
            "date": pl.from_epoch(t4, time_unit="ms"),
            "high": h4, "low": l4, "close": c4, "volume": v4,
        })
        print(f"== {sym} ==", flush=True)
        for name, cfg in RESEARCH_PRESETS.items():
            r = _metrics(df, cfg)
            _check(name, sym, r, enforce=not name.startswith("R4"),
                   fails=fails)
            # A5 determinism (same-process rerun, full compare)
            r2 = _metrics(df, cfg)
            same = r["raw"].equals(r2["raw"])
            if not same:
                fails.append(f"A5 determinism {name}/{sym}")
                print(f"    A5 FAIL {name}", flush=True)

    print(flush=True)
    if fails:
        print("ACCEPTANCE FAIL:")
        for f in fails:
            print(f"  - {f}")
    else:
        print("ACCEPTANCE PASS: R1/R2/R3 usable for E8; "
              "R4_diagnostic is reference-only.")
    print("\nNOTE: repaint-free/determinism are also covered by "
          "ta/tests/tests_custom/{test_online_zigzag,"
          "test_market_structure}.py -- run pytest separately.",
          flush=True)


if __name__ == "__main__":
    main()
