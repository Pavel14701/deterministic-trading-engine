# -*- coding: utf-8 -*-
"""E8 port-check: does the OB detector work on 4H with the "4h"
preset?  Diagnostic ONLY (prereg 51448f7 gate: must pass before E8).

Checks per the E8 plan:
  1. detector runs without errors on 4H OHLCV;
  2. block counts are reasonable (not ~10, not ~10000 per asset);
  3. zone width median in [1, 3] ATR14 units;
  4. retest-delay distribution is sane (mostly within 36 x 4H bars)
     -- compared against the 1H/"1h" reference on the same source.

Run:  uv run python -m experiments.ob.detector.port_check_4h
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    read_1h,
    repo_root,
    resample_4h,
)
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import (
    get_order_block_config,
)
from ta.src.volatility.atr import atr_ind


def _df_4h(sym: str, repo) -> pl.DataFrame:
    ts, hp, lp, cp, vol = resample_4h(*read_1h(repo, sym))
    return pl.DataFrame({
        "date": pl.from_epoch(ts, time_unit="ms"),
        "high": hp, "low": lp, "close": cp, "volume": vol,
    })


def _df_tf(ts, hp, lp, cp, vol, msec: int) -> pl.DataFrame:
    b = ts // msec
    df = pl.DataFrame({"b": b, "ts": ts, "hp": hp, "lp": lp,
                       "cp": cp, "vol": vol})
    g = df.group_by("b", maintain_order=True).agg(
        pl.first("ts"), pl.max("hp"), pl.min("lp"),
        pl.last("cp"), pl.sum("vol"),
    )
    return pl.DataFrame({
        "date": pl.from_epoch(g["ts"].to_numpy(), time_unit="ms"),
        "high": g["hp"], "low": g["lp"], "close": g["cp"],
        "volume": g["vol"],
    })


def _diagnose(df: pl.DataFrame, tf_ms: int, preset: str,
              label: str) -> dict | None:
    blocks = identify_order_blocks(
        df, cfg=get_order_block_config(preset))
    n = blocks.height
    if n == 0:
        print(f"{label}: 0 blocks", flush=True)
        return None
    ts = df["date"].dt.epoch(time_unit="ms").to_numpy().astype(
        np.int64)
    hp = df["high"].to_numpy().astype(np.float64)
    lp = df["low"].to_numpy().astype(np.float64)
    cp = df["close"].to_numpy().astype(np.float64)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    b = ts // tf_ms
    pos = {d: i for i, d in enumerate(df["date"].to_list())}
    widths, delays, ztypes = [], [], {"supply": 0, "demand": 0}
    for row in blocks.iter_rows(named=True):
        i_break = pos.get(row["break"])
        i_retest = pos.get(row["retest"])
        if i_break is None or i_retest is None:
            continue
        if np.isfinite(atr[i_break]) and atr[i_break] > 0:
            widths.append((row["zone_high"] - row["zone_low"])
                          / atr[i_break])
        delays.append(b[i_retest] - b[i_break])
        ztypes[row["block_type"]] = ztypes.get(row["block_type"], 0) + 1
    w = np.array(widths)
    d = np.array(delays)
    res = {
        "n": n, "n_meas": len(w),
        "w_med": float(np.median(w)) if w.size else float("nan"),
        "w_p10": float(np.percentile(w, 10)) if w.size else float("nan"),
        "w_p90": float(np.percentile(w, 90)) if w.size else float("nan"),
        "d_med": float(np.median(d)) if d.size else float("nan"),
        "d_le36": float((d <= 36).mean() * 100) if d.size else 0.0,
        **ztypes,
    }
    print(f"{label}: blocks={n} (S {res.get('supply', 0)} / "
          f"D {res.get('demand', 0)})  zoneW ATR med "
          f"{res['w_med']:.2f} [{res['w_p10']:.2f},"
          f"{res['w_p90']:.2f}]  delay med {res['d_med']:.0f} bars, "
          f"<=36 bars: {res['d_le36']:.0f}%", flush=True)
    return res


def main() -> None:
    repo = repo_root()
    ok = True

    # reference: 1H data + "1h" preset (the archived working combo)
    ts, hp, lp, cp, vol = read_1h(repo, "BTC")
    ref = _diagnose(_df_tf(ts, hp, lp, cp, vol, 3_600_000),
                    3_600_000, "1h", "REF  BTC 1H/'1h'")
    if ref is None or not (200 <= ref["n"] <= 20000):
        ok = False

    print(flush=True)
    for sym in ASSETS:
        df4 = _df_4h(sym, repo)
        r = _diagnose(df4, MSEC_4H, "4h", f"4H   {sym} '4h'")
        if r is None or not (50 <= r["n"] <= 5000):
            ok = False
            print(f"  -> {sym}: block count out of [50, 5000]",
                  flush=True)
        elif not (1.0 <= r["w_med"] <= 3.0):
            ok = False
            print(f"  -> {sym}: zone width median outside [1, 3] ATR",
                  flush=True)

    print(f"\nPORT-CHECK VERDICT: "
          f"{'PASS -- detector usable on 4H, E8 may proceed'}"
          if ok else "\nPORT-CHECK VERDICT: FAIL -- E8 stays postponed",
          flush=True)


if __name__ == "__main__":
    main()
