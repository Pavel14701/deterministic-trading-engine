"""Funding carry v2 (delta-neutral) -- pre-registered variant battery.

Implements the v2 prereg in STATUS.md (commit 58849ca, BEFORE run):

  - OKX funding panel is API-hard-limited to ~94 days (verified live:
    0 records beyond cache via the after-cursor), so persistence
    beyond that is cross-checked on Binance funding history (different
    venue; context only, NOT OKX tradability evidence).
  - Variants: {daily, weekly} rebalance x {taker 0.30%, maker 0.20%}
    round-trip costs.  PRIMARY = weekly-maker.
  - Per-asset dead zone: only hold a position if its own trailing 3d
    mean |funding| >= 2bp/day (v1's global OR-mask never filtered).
  - Per-asset slow carry: hold short while trailing mean > +2bp/day,
    long while < -2bp/day, exit on sign flip; half round trip at
    entry and exit (maker).
  - Gates: W-G1 weekly-maker ann >= 3% AND Sharpe >= 1.0;
    W-G2 per-asset Sharpe >= 1.0 on >= 3 assets; W-G3 turnover
    <= 0.3 new positions/day.
"""
from __future__ import annotations

import json
import sys
import time

from pathlib import Path

import niquests
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from engine.experiments.funding_carry import UNIVERSE, daily_funding

BINANCE_BASE = "https://fapi.binance.com"
BINANCE_YEARS = 3
K = 3
SIGNAL_DAYS = 3
DEAD_ZONE = 0.0002          # 2 bp/day, per-asset
TAKER_RT = 0.003            # 2x (spot 0.10% + perp 0.05%)
MAKER_RT = 0.002            # 2x (spot 0.08% + perp 0.02%)
BNB_CACHE = REPO / "data" / "funding_binance"


def _get(url: str, params: dict, retries: int = 4) -> list[dict]:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = niquests.get(url, params=params, timeout=30.0)
            r.raise_for_status()
            return r.json()
        except niquests.RequestException as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def binance_daily_funding(inst: str) -> pl.DataFrame | None:
    """~BINANCE_YEARS of raw funding rows from Binance USDT-M futures."""
    sym = inst.replace("-USDT", "USDT")  # LINK-USDT -> LINKUSDT
    cache = BNB_CACHE / f"fbnb_{sym}.parquet"
    if cache.exists():
        return pl.read_parquet(cache)
    ms_per_day = 86_400_000
    start = int(time.time() * 1000) - BINANCE_YEARS * 365 * ms_per_day
    rows: list[tuple[int, float]] = []
    while True:
        page = _get(
            f"{BINANCE_BASE}/fapi/v1/fundingRate",
            {"symbol": sym, "startTime": str(start), "limit": "1000"},
        )
        if not isinstance(page, list) or not page:
            break
        rows += [(int(r["fundingTime"]), float(r["fundingRate"]))
                 for r in page]
        nxt = int(page[-1]["fundingTime"]) + 1
        if len(page) < 1000 or nxt <= start:
            break
        start = nxt
        time.sleep(0.15)
    if not rows:
        return None
    f = pl.DataFrame(
        rows, schema={"ts": pl.Int64, "rate": pl.Float64}, orient="row"
    ).unique(subset="ts").sort("ts")
    BNB_CACHE.mkdir(parents=True, exist_ok=True)
    f.write_parquet(cache)
    return f


def to_daily(f: pl.DataFrame) -> pl.DataFrame:
    if "ts" not in f.columns:      # v1 daily_funding: inst,date,f
        return f.select("inst", "date", "f").sort("date")
    return (
        f.with_columns(
            pl.from_epoch("ts", time_unit="ms").dt.date().alias("date")
        )
        .group_by("date")
        .agg(pl.col("rate").sum().alias("f"))
        .sort("date")
    )


def build_panel(fetch) -> tuple[np.ndarray, list]:
    frames = []
    for inst in UNIVERSE:
        print(f"  {inst} ...", flush=True)
        try:
            raw = fetch(inst)
        except RuntimeError as exc:
            print(f"    [skip] {exc}", flush=True)
            continue
        if raw is None:
            continue
        d = to_daily(raw)
        if d.height > 60:
            frames.append(d.select(pl.lit(inst).alias("inst"), "date", "f"))
    wide = (
        pl.concat(frames)
        .pivot(index="date", on="inst", values="f")
        .sort("date")
    )
    print(
        f"panel: {wide.shape[0]} days x {wide.shape[1] - 1} assets",
        flush=True,
    )
    return wide.drop("date").to_numpy(), wide["date"].to_list()


def trailing_signal(mat: np.ndarray) -> np.ndarray:
    sig = np.full_like(mat, np.nan)
    for j in range(mat.shape[1]):
        roll = (
            pl.DataFrame({"f": mat[:, j]})
            .with_columns(pl.col("f").rolling_mean(SIGNAL_DAYS).alias("s"))
            ["s"].to_numpy()
        )
        sig[1:, j] = roll[:-1]  # decide on d-1 data
    return sig


def portfolio(mat: np.ndarray, sig: np.ndarray, rebal_every: int,
              rt_cost: float) -> dict:
    """Cross-sectional carry book; rebalance every `rebal_every` days."""
    n = mat.shape[0]
    gross = np.full(n, np.nan)
    cost = np.zeros(n)
    new_cnt = np.zeros(n)
    pos = np.full(mat.shape[1], 0.0)  # per-asset sign, 0 = flat
    prev_side: dict[int, float] = {}
    for i in range(n):
        if i % rebal_every == 0:
            s = sig[i]
            ok = np.isfinite(s) & (np.abs(s) >= DEAD_ZONE)
            idx = np.where(ok)[0]
            if idx.size >= 2 * K:
                order = idx[np.argsort(s[idx])]
                picks: dict[int, float] = {}
                for j in order[:K]:
                    picks[int(j)] = -1.0     # negative funding: long perp
                for j in order[-K:]:
                    picks[int(j)] = 1.0      # positive funding: short perp
                new_names = {
                    j for j, sgn in picks.items()
                    if prev_side.get(j) != sgn
                }
                closed = [j for j in prev_side if j not in picks]
                for j in closed:
                    pos[j] = 0.0
                for j, sgn in picks.items():
                    pos[j] = sgn
                cost[i] = rt_cost * (len(new_names) + len(closed)) / (2 * K)
                new_cnt[i] = len(new_names) + len(closed)
                prev_side = picks
        held = np.where(pos != 0.0)[0]
        if held.size:
            f = mat[i, held]
            f = np.where(np.isfinite(f), f, 0.0)
            # pos=+1 is SHORT perp -> receives +f; pos=-1 LONG -> -f
            gross[i] = float(np.mean(pos[held] * f))
        else:
            gross[i] = 0.0
    valid = ~np.isnan(gross)
    net = gross - cost
    v = net[valid]
    return {
        "ann": float(v.mean() * 365),
        "sharpe": float(v.mean() / v.std() * np.sqrt(365))
        if v.std() > 0 else float("nan"),
        "gross_bp_day": float(gross[valid].mean() * 1e4),
        "hit": float((v > 0).mean()),
        "new_per_day": float(new_cnt.sum() / max(valid.sum(), 1)),
        "days": int(valid.sum()),
    }


def per_asset_slow_carry(mat: np.ndarray, sig: np.ndarray,
                         rt_cost: float) -> list[tuple[str, float, int]]:
    out = []
    for j in range(mat.shape[1]):
        f = mat[:, j]
        s = sig[:, j]
        pos = 0.0
        stream = np.zeros(len(f))
        for i in range(len(f)):
            if not np.isfinite(f[i]):
                continue
            cost_i = 0.0
            if pos == 0.0:
                if np.isfinite(s[i]) and s[i] >= DEAD_ZONE:
                    pos = -1.0  # positive funding -> short perp
                    cost_i = rt_cost / 2
                elif np.isfinite(s[i]) and s[i] <= -DEAD_ZONE:
                    pos = 1.0
                    cost_i = rt_cost / 2
            elif pos < 0 and s[i] <= 0.0:
                pos = 0.0
                cost_i = rt_cost / 2
            elif pos > 0 and s[i] >= 0.0:
                pos = 0.0
                cost_i = rt_cost / 2
            stream[i] = -pos * f[i] - cost_i
        v = stream[np.isfinite(f)]
        if v.size < 30:
            continue
        shp = (
            v.mean() / v.std() * np.sqrt(365) if v.std() > 0 else float("nan")
        )
        out.append((UNIVERSE[j], float(shp), int(v.size)))
    return out



def persistence_stats(mat: np.ndarray) -> dict:
    acs = []
    for j in range(mat.shape[1]):
        x = mat[:, j]
        x = x[~np.isnan(x)]
        if x.size > 50:
            acs.append(float(np.corrcoef(x[:-1], x[1:])[0, 1]))
    # weekly top-quartile membership persistence (trailing 4w mean)
    memb = []
    for i in range(28, len(mat) - 7, 7):
        trail = np.nanmean(mat[i - 28:i], axis=0)
        nxt = np.nanmean(mat[i:i + 7], axis=0)
        if np.isnan(trail).all() or np.isnan(nxt).all():
            continue
        a = set(np.where(trail >= np.nanquantile(trail, 0.75))[0])
        b = set(np.where(nxt >= np.nanquantile(nxt, 0.75))[0])
        if a | b:
            memb.append(len(a & b) / len(a | b))
    return {
        "lag1_autocorr_daily_mean": round(float(np.mean(acs)), 3),
        "top_quartile_weekly_jaccard_mean": (
            round(float(np.mean(memb)), 3) if memb else float("nan")
        ),
        "weekly_windows": len(memb),
    }


def main() -> None:
    print("=== funding carry v2 (pre-registered 58849ca) ===", flush=True)
    print("-- OKX panel (~94d API limit)", flush=True)
    okx, _ = build_panel(daily_funding)
    okx_sig = trailing_signal(okx)

    variants = {
        "daily_taker": portfolio(okx, okx_sig, 1, TAKER_RT),
        "weekly_taker": portfolio(okx, okx_sig, 7, TAKER_RT),
        "weekly_maker": portfolio(okx, okx_sig, 7, MAKER_RT),
    }
    per_asset = per_asset_slow_carry(okx, okx_sig, MAKER_RT)
    good = sorted([x for x in per_asset if x[1] >= 1.0],
                  key=lambda x: -x[1])

    print("\n-- portfolio variants (OKX ~94d)", flush=True)
    for name, r in variants.items():
        print(
            f"  {name:13s} ann={r['ann'] * 100:+6.2f}%  "
            f"sharpe={r['sharpe']:5.2f}  gross={r['gross_bp_day']:5.2f}"
            f"bp/d  hit={r['hit']:.2f}  new_pos/day={r['new_per_day']:.2f}"
        )
    print("\n-- per-asset slow carry (maker): Sharpe >= 1:",
          len(good), "assets", flush=True)
    for name, shp, n in good:
        print(f"    {name:11s} {shp:5.2f}  (n={n})")

    print("\n-- Binance persistence cross-check (3y, other venue)",
          flush=True)
    bnb, _ = build_panel(binance_daily_funding)
    bnb_stats = persistence_stats(bnb)
    for k_, v_ in bnb_stats.items():
        print(f"  {k_:34s} {v_}")

    g1 = (variants["weekly_maker"]["ann"] >= 0.03
          and variants["weekly_maker"]["sharpe"] >= 1.0)
    g2 = len(good) >= 3
    g3 = variants["weekly_maker"]["new_per_day"] <= 0.3
    print("\n=== gates ===")
    print(f"  W-G1 weekly-maker ann>=3% & sharpe>=1: "
          f"{variants['weekly_maker']['ann'] * 100:.2f}% / "
          f"{variants['weekly_maker']['sharpe']:.2f} -> "
          f"{'PASS' if g1 else 'FAIL'}")
    print(f"  W-G2 per-asset sharpe>=1 on >=3 assets: {len(good)} "
          f"-> {'PASS' if g2 else 'FAIL'}")
    print(f"  W-G3 turnover <= 0.3/day: "
          f"{variants['weekly_maker']['new_per_day']:.2f} "
          f"-> {'PASS' if g3 else 'FAIL'}")
    verdict = "PASS" if (g1 and g2 and g3) else "FAIL"
    print(f"OVERALL: {verdict}")

    out = REPO / "runs" / "funding_carry_v2.json"
    out.write_text(json.dumps({
        "variants": variants,
        "per_asset_pass": good,
        "binance": bnb_stats,
        "gates": {"W-G1": g1, "W-G2": g2, "W-G3": g3},
        "verdict": verdict,
    }, indent=1))
    print("saved runs/funding_carry_v2.json", flush=True)


if __name__ == "__main__":
    main()

