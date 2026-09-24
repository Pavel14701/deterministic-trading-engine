"""P4 low-cap carry -- gates per the frozen prereg (STATUS
2026-09-21).  Universe: the snapshot JSON produced by
p4_universe.py (rule frozen at pull date).  Params: v3 rules
AS-IS (trailing 3d mean daily funding decided on d-1, entry
|sig| >= 2bp/day DEAD_ZONE, exit on sign flip, MAKER_RT/2 at
entry and exit).  Evaluation: PRIMARY = full available history
pooled; CONFIRMATION = trailing 12 months.  Gates:
  G1: portfolio Sharpe_NW >= 1.0 on PRIMARY
  G2: portfolio Sharpe_NW >= 0.7 on trailing 12m
  G3: portfolio maxDD <= 15%
  G4: >= 60% of universe assets with Sharpe_NW >= 0 and
      active >= 60d (on PRIMARY)
  G5: block-bootstrap CI (P2 procedure: 30d blocks, B=10k,
      seed=7) on ann% excludes 0 on PRIMARY and on 12m.
Kill: PRIMARY gate fails -> track closed, no re-universe,
no re-params.
"""
from __future__ import annotations

import datetime as _dt
import json

import numpy as np
import polars as pl

from experiments import REPO
from experiments.carry.carry_v3_ci import ann_ci
from experiments.carry.funding_carry_v2 import (
    SIGNAL_DAYS,
    binance_daily_funding,
)
from experiments.carry.funding_carry_v3 import (
    ACTIVITY_FLOOR_DAYS,
    max_dd,
    per_asset_stream,
    sharpe_nw,
)


SNAP = sorted((REPO / "data").glob("p4_universe_*.json"))[-1]
CONF_DAYS = 365
BLOCK = 30
B = 10_000
SEED = 7


def build_panel(syms: list[str]) -> tuple[np.ndarray, list[_dt.date], list[str]]:
    frames = []
    keep: list[str] = []
    for sym in syms:
        inst = f"{sym[:-4]}-{sym[-4:]}"
        print(f"  {inst} ...", flush=True)
        try:
            raw = binance_daily_funding(inst)
        except RuntimeError as exc:
            print(f"    [skip] {exc}", flush=True)
            continue
        if raw is None:
            continue
        d = raw.with_columns(
            pl.from_epoch("ts", time_unit="ms").dt.date().alias("date")
        ).group_by("date").agg(pl.col("rate").sum().alias("f")).sort("date")
        if d.height > 60:
            frames.append(d.select(pl.lit(sym).alias("inst"), "date", "f"))
            keep.append(sym)
    wide = (
        pl.concat(frames).pivot(index="date", on="inst", values="f")
        .sort("date")
    )
    dates = [d for d in wide["date"].to_list()]
    mat = wide.drop("date").to_numpy().astype(float)
    return mat, dates, keep


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


def main() -> None:
    snap = json.loads(SNAP.read_text())
    syms = [u["symbol"] for u in snap["universe"]]
    print(f"=== P4 gates (universe snapshot {snap['pull_date']}, "
          f"n={len(syms)}) ===", flush=True)
    mat, dates, keep = build_panel(syms)
    print(f"panel: {mat.shape[0]} days x {mat.shape[1]} assets "
          f"({dates[0]} .. {dates[-1]})", flush=True)
    sig = trailing_signal(mat)
    streams = np.zeros_like(mat)
    for j in range(mat.shape[1]):
        streams[:, j] = per_asset_stream(mat[:, j], sig[:, j])

    n = mat.shape[0]
    a_conf = next((i for i, d in enumerate(dates)
                   if d >= dates[-1] - _dt.timedelta(days=CONF_DAYS)), 0)
    port = streams.mean(axis=1)  # v3 convention: mean over all slots
    segs = {"PRIMARY": (0, n), "CONF-12m": (a_conf, n)}
    res = {}
    for name, (a, b) in segs.items():
        sh, shnw, fac = sharpe_nw(port[a:b])
        res[name] = {"ann_pct": round(float(port[a:b].mean() * 365) * 100, 2),
                     "sharpe": round(sh, 2), "sharpe_nw": round(shnw, 2),
                     "nw_factor": round(fac, 2),
                     "max_dd_pct": round(max_dd(port[a:b]) * 100, 2)}
        print(f"{name}: ann={res[name]['ann_pct']:+.2f}%  "
              f"sharpe_nw={shnw:+.2f} (x{fac:.2f})  "
              f"maxDD={res[name]['max_dd_pct']:.2f}%", flush=True)

    rng = np.random.default_rng(SEED)
    for name, (a, b) in segs.items():
        _p, lo, hi = ann_ci(port[a:b], rng)
        res[name]["ci95"] = [round(lo, 2), round(hi, 2)]
        res[name]["ci_excl_0"] = bool(lo > 0.0)
        print(f"{name}: ann CI95=[{lo:+.2f}, {hi:+.2f}]", flush=True)

    a0, b0 = segs["PRIMARY"]
    ok = 0
    for j, sym in enumerate(keep):
        mask = np.isfinite(mat[a0:b0, j])
        active = int(np.sum(mask & (streams[a0:b0, j] != 0.0)))
        _, shnw, _ = sharpe_nw(streams[mask, j])
        if active >= ACTIVITY_FLOOR_DAYS and np.isfinite(shnw) and shnw >= 0:
            ok += 1
    frac = ok / max(len(keep), 1)
    print(f"G4 assets (Sharpe_NW>=0, active>={ACTIVITY_FLOOR_DAYS}d): "
          f"{ok}/{len(keep)} = {frac:.0%}", flush=True)

    g1 = res["PRIMARY"]["sharpe_nw"] >= 1.0
    g2 = res["CONF-12m"]["sharpe_nw"] >= 0.7
    g3 = res["PRIMARY"]["max_dd_pct"] <= 15.0
    g4 = frac >= 0.60
    g5 = res["PRIMARY"]["ci_excl_0"] and res["CONF-12m"]["ci_excl_0"]
    for name, okk in (("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4),
                      ("G5", g5)):
        print(f"  {name}: {'PASS' if okk else 'FAIL'}")
    verdict = "PASS" if (g1 and g2 and g3 and g4 and g5) else \
        "CLOSED (PRIMARY gate failed; no re-universe, no re-params)"
    print(f"P4: {verdict}", flush=True)
    out = {"snapshot": snap["pull_date"], "universe": keep,
           "results": res, "g4_frac": round(frac, 3),
           "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5},
           "verdict": verdict}
    (REPO / "runs" / "p4_carry.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
