# -*- coding: utf-8 -*-
"""Honest (repaint-free) raw EV of order-block retest entries.

Uses the **ta** market-structure pipeline (online ZigZag, confirm-guarded
pivots, causal filters) on cached OKX candles - the first OB test that is
not contaminated by look-ahead.

For every confirmed block:

- entry at the retest bar's close, fading the zone
  (demand -> long, supply -> short);
- risk unit R = entry - stop, stop just beyond the protected zone edge
  (``zone_low - stop_atr_buffer * ATR`` for demand, mirrored for supply);
- take-profit at ``tp_r * R``; stop at -1R; if neither is hit within
  ``horizon`` bars the position is marked to market at the horizon close;
- taker fees charged on both legs (converted to R via the risk unit);
- within-bar ambiguity resolved conservatively (stop wins).

Reported per timeframe / ``reversal_atr_multiple`` grid: block counts,
EV in R (gross and net), win-rate, plus calibration distributions
(retest delay in bars -> ``confirmation_window``, zone width in ATR)
used to tune the presets.

Usage:  uv run python -m engine.experiments.ob_raw_ev
"""

from __future__ import annotations

import sys

from dataclasses import replace
from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.configs import TIMEFRAME_CONFIGS
from ta.src.volatility.atr import atr_ind


#: cached raw candle files, relative to the repo root
FILES: dict[str, str] = {
    "5m": "data/okx/raw_BTC-USDT_5m.parquet",
    "15m": "data/okx/raw_BTC-USDT_15m.parquet",
}
REVERSAL_GRID = (2.5,)
TP_R_GRID = (1.0, 3.0, 6.0)
STOP_ATR_BUFFER = 0.25
HORIZON = 48  # bars
TAKER_FEE = 0.0005  # per leg, fraction of notional


def _simulate_block(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    retest_idx: int,
    is_supply: bool,
    zone_low: float,
    zone_high: float,
    atr_retest: float,
    tp_r: float,
) -> tuple[float, bool, int] | None:
    """Walk a block forward; return (pnl_R, hit_tp, bars_held) or None."""
    entry = close[retest_idx]
    if is_supply:
        stop = zone_high + STOP_ATR_BUFFER * atr_retest
        risk = stop - entry
    else:
        stop = zone_low - STOP_ATR_BUFFER * atr_retest
        risk = entry - stop
    if not np.isfinite(risk) or risk <= 0:
        return None
    tp_price = entry - tp_r * risk if is_supply else entry + tp_r * risk
    sign = -1.0 if is_supply else 1.0
    n = len(close)
    for k in range(retest_idx + 1, min(retest_idx + 1 + HORIZON, n)):
        if is_supply:
            hit_sl = high[k] >= stop
            hit_tp = low[k] <= tp_price
        else:
            hit_sl = low[k] <= stop
            hit_tp = high[k] >= tp_price
        if hit_sl:
            return (-1.0, False, k - retest_idx)
        if hit_tp:
            return (tp_r, True, k - retest_idx)
    last = min(retest_idx + HORIZON, n - 1)
    pnl = sign * (close[last] - entry) / risk
    return (float(pnl), False, last - retest_idx)


def run_tf(tf: str) -> list[dict]:
    df = pl.read_parquet(REPO / FILES[tf]).rename({"ts": "date"})
    dates = df["date"].to_list()
    pos = {d: i for i, d in enumerate(dates)}
    high = df["high"].to_numpy().astype(np.float64)
    low = df["low"].to_numpy().astype(np.float64)
    close = df["close"].to_numpy().astype(np.float64)
    atr = atr_ind(high, low, close, length=14, use_talib=True)
    rows: list[dict] = []
    for k in REVERSAL_GRID:
        cfg = replace(
            TIMEFRAME_CONFIGS[tf],
            reversal_atr_multiple=k,
            online_reversal=None,
            online_reversal_pct=None,
        )
        out = identify_order_blocks(df, cfg=cfg)
        for tp_r in TP_R_GRID:
            pnl_list: list[float] = []
            gross_list: list[float] = []
            delay_list: list[float] = []
            age_list: list[float] = []
            zwidth_list: list[float] = []
            wins = 0
            for row in out.iter_rows(named=True):
                j = pos[row["retest"]]
                p = pos[row["start"]]
                is_supply = row["block_type"] == "supply"
                if not np.isfinite(atr[j]):
                    continue
                buffer = STOP_ATR_BUFFER * atr[j]
                stop = (
                    row["zone_high"] + buffer
                    if is_supply
                    else row["zone_low"] - buffer
                )
                sim = _simulate_block(
                    high,
                    low,
                    close,
                    j,
                    is_supply,
                    row["zone_low"],
                    row["zone_high"],
                    atr[j],
                    tp_r,
                )
                if sim is None:
                    continue
                pnl, hit_tp, _held = sim
                risk = abs(close[j] - stop)
                fee_r = TAKER_FEE * 2 * close[j] / risk
                gross_list.append(pnl)
                pnl_list.append(pnl - fee_r)
                delay_list.append(float(j - p))
                age_list.append(float(pos[row["break"]] - p))
                zwidth_list.append(
                    (row["zone_high"] - row["zone_low"]) / atr[p]
                    if np.isfinite(atr[p])
                    else np.nan
                )
                wins += int(hit_tp)
            n = len(pnl_list)
            net = float(np.mean(pnl_list)) if n else np.nan
            gross = float(np.mean(gross_list)) if n else np.nan
            rec = {
                "tf": tf,
                "rev_atr": k,
                "tp_r": tp_r,
                "blocks": out.height,
                "traded": n,
                "ev_r_gross": gross,
                "ev_r_net": net,
                "win_rate": wins / n if n else np.nan,
                "retest_delay_med": (
                    float(np.median(delay_list)) if n else np.nan
                ),
                "retest_delay_p90": (
                    float(np.percentile(delay_list, 90)) if n else np.nan
                ),
                "pivot_age_med": (
                    float(np.median(age_list)) if n else np.nan
                ),
                "pivot_age_p90": (
                    float(np.percentile(age_list, 90)) if n else np.nan
                ),
                "zone_width_atr_med": (
                    float(np.nanmedian(zwidth_list)) if n else np.nan
                ),
            }
            rows.append(rec)
            print(
                f"{tf:>4} revATR={k:.1f} TP={tp_r:.0f}R "
                f"blocks={rec['blocks']:>4} traded={n:>4} "
                f"EV={gross:+.3f}R net={net:+.3f}R win={rec['win_rate']:.1%} "
                f"delay_med={rec['retest_delay_med']:.0f} "
                f"delay_p90={rec['retest_delay_p90']:.0f} "
                f"age_med={rec['pivot_age_med']:.0f} "
                f"age_p90={rec['pivot_age_p90']:.0f} "
                f"zwATR={rec['zone_width_atr_med']:.2f}",
                flush=True,
            )
    return rows


def main() -> None:
    all_rows: list[dict] = []
    for tf in FILES:
        print(f"\n=== {tf} ===", flush=True)
        all_rows.extend(run_tf(tf))
    out_dir = REPO / "runs"
    out_dir.mkdir(exist_ok=True)
    pl.DataFrame(all_rows).write_parquet(out_dir / "ob_raw_ev.parquet")
    print("\nsaved -> runs/ob_raw_ev.parquet", flush=True)


if __name__ == "__main__":
    main()