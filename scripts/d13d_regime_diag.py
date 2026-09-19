"""D.13d: what regime signal separates weak folds (f2, f5) from f1?

D.13c located the A-vs-D gap in two folds: 2025-10-27..12-22 and
2026-04-13..06-08.  A regime-aware stop-floor needs a CAUSAL trigger
that fires early inside those folds and stays quiet in f1 (where the
narrow-stop stack is fine).  This script:

  1. recomputes the production regime vector (z50, slope50 from the
     SMA50; vol_pct = ATR% percentile, bbw_pct = BB-width percentile,
     both in a trailing 500-bar window - all causal) on the 1h bars;
  2. prints per-fold x per-asset feature means -> which feature
     separates f2/f5 from f1;
  3. checks detector latency: feature values on fold day 0/3/7 vs the
     fold mean - how early the separation is visible;
  4. scores candidate triggers (vol_pct >= .7, |z50| <= .5,
     bbw_pct >= .7) by per-fold coverage and lead time.

Saves runs/d13d_regime_diag.json.
"""

from __future__ import annotations

import json
import sys

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.features import compute_atr  # noqa: E402
from engine.mtf import resample_ohlcv  # noqa: E402
from engine.mtf_dataset import rolling_percentile, trend_state  # noqa: E402

TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
N_FOLDS, FOLD_DAYS, DAY_MS = 8, 56, 86_400_000
TRIGGERS = {
    "vol_pct>=0.7": lambda f: f["vol_pct"] >= 0.7,
    "abs_z50<=0.5": lambda f: np.abs(f["z50"]) <= 0.5,
    "bbw_pct>=0.7": lambda f: f["bbw_pct"] >= 0.7,
    "vol&chop": lambda f: (f["vol_pct"] >= 0.7) & (np.abs(f["z50"]) <= 0.5),
}

def hourly(tag: str) -> pl.DataFrame:
    """1h bars + the production causal regime vector."""
    base = resample_ohlcv(
        pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet"), "1h"
    )
    atr = compute_atr(base, period=14).astype(np.float64)
    close = base["close"].to_numpy().astype(np.float64)
    z50, slope50, _ = trend_state(close, atr)
    atr_pct = np.where(close > 0, atr / close, np.nan)
    vol_pct = rolling_percentile(atr_pct, window=500)
    cs = base["close"]
    mean20 = cs.rolling_mean(20)
    std20 = cs.rolling_std(20, ddof=0)
    bbw = (4 * std20 / mean20).to_numpy()
    bbw_pct = rolling_percentile(bbw, window=500)
    return base.select(["ts"]).with_columns(
        pl.Series("z50", z50), pl.Series("slope50", slope50),
        pl.Series("atr_pct", atr_pct), pl.Series("vol_pct", vol_pct),
        pl.Series("bbw_pct", bbw_pct),
    )


def folds() -> list[tuple[int, int]]:
    """Same fold grid as d13c (t0/t1 from the ablation-A panels)."""
    tss = []
    for t in TAGS:
        p = pl.read_parquet(
            REPO / "data" / "ablation" / "A"
            / f"{t.replace('-', '')}_1h.parquet"
        ).filter(
            (pl.col("execution") == "market") & (pl.col("target") == 2.0)
        )
        tss.append((int(p["ts"].min()), int(p["ts"].max())))
    t0, t1 = min(a for a, _ in tss), max(b for _, b in tss)
    fl = FOLD_DAYS * DAY_MS
    return [(t0 + w * fl, t0 + (w + 1) * fl) for w in
            range(max(0, (t1 - t0) // fl - N_FOLDS + 1),
                  (t1 - t0) // fl + 1)][-N_FOLDS:]

def main() -> None:
    frames = {t: hourly(t) for t in TAGS}
    fds = folds()

    # --- 1. per-fold feature means (pooled over assets) ---
    print("\n=== per-fold regime features (mean over 3 assets, 1h bars) ===",
          flush=True)
    print(f"{'fold':14s} {'|z50|':>6s} {'slp50':>6s} {'atr%':>6s} "
          f"{'vol_p':>6s} {'bbw_p':>6s} {'range%':>6s} {'nbars':>6s}",
          flush=True)
    fold_stats = {}
    for fi, (fs_, fe) in enumerate(fds):
        parts = [frames[t].filter((pl.col("ts") >= fs_)
                                  & (pl.col("ts") < fe)).drop_nulls()
                 for t in TAGS]
        cat = pl.concat([p for p in parts if p.height])
        row = {"|z50|": float(cat["z50"].abs().mean()),
               "slope50": float(cat["slope50"].mean()),
               "atr_pct": float(cat["atr_pct"].mean()) * 100,
               "vol_pct": float(cat["vol_pct"].mean()),
               "bbw_pct": float(cat["bbw_pct"].mean()),
               "range": float((cat["z50"].abs() <= 0.5).mean()) * 100,
               "n": cat.height}
        fold_stats[fi] = row
        d0 = datetime.fromtimestamp(fs_ / 1000, tz=timezone.utc)
        print(f"f{fi} {d0:%Y-%m-%d}   {row['|z50|']:6.2f} "
              f"{row['slope50']:+6.2f} {row['atr_pct']:6.3f} "
              f"{row['vol_pct']:6.2f} {row['bbw_pct']:6.2f} "
              f"{row['range']:6.1f} {row['n']:6d}", flush=True)

    # --- 2. latency: feature level on fold day 0/3/7 vs fold mean ---
    print("\n=== detector latency (vol_pct, |z50|) day 0/3/7 vs fold mean ===",
          flush=True)
    lat = {}
    for fi in (1, 2, 5):
        fs_ = fds[fi][0]
        rows = {}
        for t in TAGS:
            f = frames[t].filter(pl.col("ts") >= fs_).head(56 * 24).drop_nulls()
            for dd in (0, 3, 7):
                seg = f.head(dd * 24 + 24).tail(24)
                rows.setdefault(f"d{dd}", {})[t] = (
                    float(seg["vol_pct"].mean()),
                    float(seg["z50"].abs().mean()))
            rows.setdefault("fold_mean", {})[t] = (
                float(f["vol_pct"].mean()), float(f["z50"].abs().mean()))
        lat[fi] = rows
        print(f"  f{fi}:", flush=True)
        for k in ("d0", "d3", "d7", "fold_mean"):
            print(f"    {k:9s} " + "  ".join(
                f"{t.split('-')[0]}: vol={a:.2f} |z|={b:.2f}"
                for t, (a, b) in rows[k].items()), flush=True)

    # --- 3. trigger coverage per fold + lead time in f2/f5 ---
    print("\n=== trigger coverage, % bars flagged (lead = hours to 1st flag "
          "in f2/f5) ===", flush=True)
    trig_stats = {}
    for name, fn in TRIGGERS.items():
        cov, leads = {}, []
        for fi, (fs_, fe) in enumerate(fds):
            flags = []
            for t in TAGS:
                w = frames[t].filter((pl.col("ts") >= fs_)
                                     & (pl.col("ts") < fe)).drop_nulls()
                m = fn({c: w[c].to_numpy() for c in w.columns})
                flags.append(float(m.mean()))
                idx = np.flatnonzero(m)
                if fi in (2, 5) and idx.size:
                    leads.append(int(idx[0]))
            cov[fi] = float(np.mean(flags)) * 100
        trig_stats[name] = {"coverage": cov, "min_lead_h_f2f5": min(leads)}
        print(f"  {name:14s} "
              + " ".join(f"f{fi}={cov[fi]:4.0f}%" for fi in sorted(cov))
              + f"  lead={min(leads)}h", flush=True)

    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "d13d_regime_diag.json").write_text(json.dumps(
        {"folds": fold_stats, "latency": lat, "triggers": trig_stats},
        indent=1, default=str))
    print("\nsaved runs/d13d_regime_diag.json", flush=True)


if __name__ == "__main__":
    main()
