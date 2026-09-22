"""Funding carry feasibility check (delta-neutral).

Delta-neutral carry: short the perp when funding is positive (shorts
receive), long when negative; the opposite spot leg removes price
risk.  PnL per position per day = |funding| collected - nothing else
(basis/margin costs ignored, documented).

Design:
  - daily funding per asset = sum of 3 settlements per UTC day
  - signal  = trailing 3-day mean daily funding (decided on d-1 data)
  - each day: short top-k by signal, long bottom-k (equal weight)
  - costs   = ROUND_TRIP per new position (perp taker 2x + spot leg)

Outputs runs/funding_carry.json: per-asset funding stats,
persistence (lag-1 autocorr of daily funding), and the net carry
stream (annualized %, daily Sharpe, hit rate, avg positions).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import polars as pl

from experiments import REPO


sys.path.insert(0, str(REPO))

from engine.infra.marketdata.okx_fetch import (
    fetch_funding_history,
)


UNIVERSE = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
    "BNB-USDT", "ADA-USDT", "AVAX-USDT", "LINK-USDT", "TON-USDT",
    "TRX-USDT", "DOT-USDT", "LTC-USDT", "BCH-USDT", "NEAR-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "SUI-USDT", "PEPE-USDT",
    "TIA-USDT", "INJ-USDT", "FIL-USDT", "ATOM-USDT", "ETC-USDT",
    "XLM-USDT", "HBAR-USDT", "AAVE-USDT", "WIF-USDT", "SEI-USDT",
]
K = 3               # long k / short k per day
SIGNAL_DAYS = 3     # trailing mean window
MIN_ABS_SIGNAL = 0.0002  # 2 bp/day: skip the dead zone
ROUND_TRIP_COST = 0.003  # 0.3% of notional per position open+close
CACHE = REPO / "data" / "funding"


def daily_funding(inst: str) -> pl.DataFrame | None:
    try:
        f = fetch_funding_history(
            f"{inst}-SWAP", max_records=1800, cache_dir=CACHE
        )
    except RuntimeError as exc:
        print(f"  [skip] {inst}: {exc}", flush=True)
        return None
    d = (
        f.with_columns(
            pl.from_epoch("ts", time_unit="ms").dt.date().alias("date")
        )
        .group_by("date")
        .agg(pl.col("rate").sum().alias("f"))
        .sort("date")
    )
    return d.select(pl.lit(inst).alias("inst"), "date", "f")


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    frames = []
    for inst in UNIVERSE:
        print(f"fetching {inst} ...", flush=True)
        d = daily_funding(inst)
        if d is not None and d.height > 60:
            frames.append(d)
    wide = (
        pl.concat(frames)
        .pivot(index="date", on="inst", values="f")
        .sort("date")
    )
    print(f"\npanel: {wide.shape[0]} days x {wide.shape[1] - 1} assets",
          flush=True)

    mat = wide.drop("date").to_numpy()
    dates = wide["date"].to_list()
    sig = np.full_like(mat, np.nan)
    for j in range(mat.shape[1]):
        col = mat[:, j]
        roll = (
            pl.DataFrame({"f": col})
            .with_columns(pl.col("f").rolling_mean(SIGNAL_DAYS).alias("s"))
            ["s"].to_numpy()
        )
        sig[1:, j] = roll[:-1]  # decision on d uses data through d-1

    gross, costs, npos, shorts, news = [], [], [], [], []
    prev: set[str] = set()
    for i in range(len(dates)):
        s = sig[i]
        ok = np.isfinite(s)
        if ok.sum() < 2 * K:
            gross.append(np.nan)
            costs.append(0.0)
            news.append(0)
            npos.append(0)
            shorts.append(frozenset())
            prev = set()
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(s[idx])]
        longs = order[:K]    # negative funding: long perp receives
        shrt = order[-K:]    # positive funding: short perp receives
        sel = list(longs) + list(shrt)
        actual = mat[i]
        g = float(np.mean(np.where(np.isin(sel, longs), -1.0, 1.0)
                          * actual[sel]))
        cur = {str(j) for j in sel}  # asset-keyed: held positions are
        # NOT re-charged next day just because the calendar rolled
        new = len(cur - prev)
        prev = cur
        gross.append(g)
        news.append(new)
        costs.append(ROUND_TRIP_COST * new / (2 * K))
        npos.append(len(sel))
        shorts.append(frozenset(str(j) for j in shrt))

    gross_a = np.array(gross)
    valid = np.isfinite(gross_a)
    thr_mask = np.array(
        [np.nanmax(np.abs(s)) >= MIN_ABS_SIGNAL for s in sig], dtype=bool
    )
    take = valid & thr_mask
    net = np.where(take, gross_a - np.array(costs), 0.0)
    days = int(take.sum())
    ann = net[take].mean() * 365
    shp = (net[take].mean() / net[take].std() * np.sqrt(365)
           if net[take].std() > 0 else float("nan"))
    hit = float((net[take] > 0).mean())

    gross_v = gross_a[take]
    cost_v = np.array(costs)[take]
    new_v = np.array(news)[take]
    res = {
        "universe_ok": int(mat.shape[1]),
        "days_total": len(dates),
        "days_traded": days,
        "k": K,
        "signal_days": SIGNAL_DAYS,
        "round_trip_cost": ROUND_TRIP_COST,
        "gross_daily_mean_bp": round(float(gross_v.mean()) * 1e4, 2),
        "gross_annualized": round(float(gross_v.mean()) * 365, 4),
        "gross_daily_sharpe": round(
            float(gross_v.mean() / gross_v.std() * np.sqrt(365))
            if gross_v.std() > 0 else float("nan"), 2),
        "gross_hit_rate": round(float((gross_v > 0).mean()), 3),
        "avg_daily_cost_bp": round(float(cost_v.mean()) * 1e4, 2),
        "avg_new_positions_per_day": round(float(new_v.mean()), 2),
        "net_annualized": round(float(ann), 4),
        "net_daily_sharpe": round(float(shp), 2),
        "hit_rate": round(hit, 3),
        "avg_positions": round(float(np.mean([n for n in npos if n])), 1),
    }
    print("\n=== funding carry (delta-neutral) ===")
    for key, val in res.items():
        print(f"  {key:22s} {val}")

    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "funding_carry.json").write_text(
        json.dumps(res, indent=1))
    print("saved runs/funding_carry.json", flush=True)


if __name__ == "__main__":
    main()
