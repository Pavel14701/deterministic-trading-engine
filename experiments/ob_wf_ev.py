# -*- coding: utf-8 -*-
"""Walk-forward gross EV of honest order-block retest entries.

Same fold calendar as the D.13/D.14 protocol (``protocol::wf_folds``,
8 x 56d, embargo 7d).  Per fold:

- run the OB pipeline on the causal prefix ``ts < fold_end`` (the ATR
  median used for ``reversal_atr_multiple`` is computed on the prefix
  too - no future information);
- evaluate blocks whose retest falls inside the fold window
  (``fold_masks`` test mask, embargo respected trivially since nothing
  is fitted - parameters are fixed a priori);
- simulate gross R: entry at retest close, stop beyond the protected
  zone edge, TP at {1, 3, 6}R, horizon-capped mark-to-market.

Reported per fold: block count, gross EV per TP, win-rate.  Pooled
across folds: EV vs pivot age (``break_idx - idx``, tests the
"OB works on reversals after consolidation, not impulses" hypothesis)
and retest-delay distribution.  Net with taker fees is reported for
reference only; the go/no-go criterion is gross fold stability.

Usage:  uv run python -m experiments.ob_wf_ev
"""

from __future__ import annotations

import sys

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import EMBARGO_DAYS, FOLD_DAYS, N_FOLDS, wf_folds
from experiments.ob_raw_ev import _simulate_block
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


FILE = "data/okx/raw_BTC-USDT_15m.parquet"
TP_R_GRID = (1.0, 3.0, 6.0)
AGE_BUCKETS = ((0, 10), (11, 20), (21, 10**9))


def run() -> None:
    df = pl.read_parquet(REPO / FILE).rename({"ts": "date"})
    ts = df["date"].to_numpy().astype(np.int64)
    cfg = TIMEFRAME_CONFIGS["15m"]
    folds = wf_folds(int(ts[0]), int(ts[-1]), N_FOLDS, FOLD_DAYS)
    print(
        f"{len(folds)} folds x {FOLD_DAYS}d, embargo {EMBARGO_DAYS}d, "
        f"cfg: revATR={cfg.reversal_atr_multiple} cw={cfg.confirmation_window} "
        f"lb={cfg.lookback_max} multiple_breakouts={cfg.multiple_breakouts}",
        flush=True,
    )
    high = df["high"].to_numpy().astype(np.float64)
    low = df["low"].to_numpy().astype(np.float64)
    close = df["close"].to_numpy().astype(np.float64)
    pool: list[dict] = []
    print(
        f"{'fold':>4} {'blocks':>6} "
        + " ".join(f"{'EV' + format(int(t)) + 'R':>8}" for t in TP_R_GRID)
        + f" {'win3R':>7}",
        flush=True,
    )
    pos_counts = dict.fromkeys(TP_R_GRID, 0)
    for fi, (fs, fe) in enumerate(folds):
        prefix = int(np.searchsorted(ts, fe))
        dfp = df[:prefix]
        pos = {d: i for i, d in enumerate(dfp["date"].to_list())}
        hp = high[:prefix]
        lp = low[:prefix]
        cp = close[:prefix]
        atr = atr_ind(hp, lp, cp, length=14, use_talib=True)
        out = identify_order_blocks(dfp, cfg=cfg)
        trades = [
            r
            for r in out.iter_rows(named=True)
            if fs <= ts[pos[r["retest"]]] < fe
        ]
        evs: dict[float, list[float]] = {t: [] for t in TP_R_GRID}
        for row in trades:
            j = pos[row["retest"]]
            p = pos[row["start"]]
            b = pos[row["break"]]
            is_supply = row["block_type"] == "supply"
            if not np.isfinite(atr[j]):
                continue
            buffer = 0.25 * atr[j]
            stop = (
                row["zone_high"] + buffer
                if is_supply
                else row["zone_low"] - buffer
            )
            risk = abs(cp[j] - stop)
            if risk <= 0:
                continue
            pnl3 = np.nan
            for tp_r in TP_R_GRID:
                sim = _simulate_block(
                    hp, lp, cp, j, is_supply,
                    row["zone_low"], row["zone_high"], atr[j], tp_r,
                )
                if sim is None:
                    continue
                evs[tp_r].append(sim[0])
                if tp_r == 3.0:
                    pnl3 = sim[0]
            pool.append(
                {
                    "fold": fi,
                    "pnl_gross": pnl3,
                    "age": b - p,
                    "rdelay": j - b,
                }
            )
        cells = []
        for tp_r in TP_R_GRID:
            v = float(np.mean(evs[tp_r])) if evs[tp_r] else np.nan
            if evs[tp_r] and v > 0:
                pos_counts[tp_r] += 1
            cells.append(f"{v:+8.3f}")
        win3 = (
            float(np.mean([x > 0 for x in evs[3.0]]))
            if evs[3.0]
            else float("nan")
        )
        print(
            f"{fi:>4} {len(trades):>6} " + " ".join(cells) + f" {win3:>7.1%}",
            flush=True,
        )
    print("\npositive folds per TP (of", len(folds), "):", flush=True)
    for tp_r in TP_R_GRID:
        print(f"  TP={tp_r:.0f}R: {pos_counts[tp_r]}", flush=True)
    print("\nEV vs pivot age (pooled, gross, 3R):", flush=True)
    ages = np.array([r["age"] for r in pool], dtype=float)
    pnls = np.array([r["pnl_gross"] for r in pool], dtype=float)
    for lo, hi in AGE_BUCKETS:
        m = (ages >= lo) & (ages < hi)
        if m.sum():
            print(
                f"  age [{lo:>2},{hi if hi < 100 else '':>2}): "
                f"n={int(m.sum()):>4} EV={float(np.mean(pnls[m])):+.3f}R",
                flush=True,
            )
    rd = np.array([r["rdelay"] for r in pool], dtype=float)
    print(
        f"\nretest delay (break->retest): med={np.median(rd):.0f} "
        f"p90={np.percentile(rd, 90):.0f}",
        flush=True,
    )


if __name__ == "__main__":
    run()