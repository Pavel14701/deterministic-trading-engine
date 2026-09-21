"""Admission-policy comparison: FCFS vs REPLACE slots.

Same 1040-trade WF-B stream under each policy; also 4h-resolution
outcome correlations (cluster-limit check at finer granularity than
daily).  Saves runs/admission_policies.json.
"""
from __future__ import annotations

import json

from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from engine.sim.admission import run_policy


REPO = Path(__file__).resolve().parent.parent
HOUR = 3_600_000


def load_b_trades() -> list[dict[str, Any]]:
    """WF-B trades from the validated walk-forward run (cell B)."""
    hour = pl.col("dur_h") * HOUR
    return (pl.read_parquet(
                REPO / "runs" / "d8b" / "wf_trades.parquet")
            .filter(pl.col("cell") == "B")
            .with_columns((pl.col("ts_entry") + hour).alias("ts_exit"))
            .sort("ts_entry").to_dicts())


def main() -> None:
    """Admission-policy comparison (saves runs/admission_policies.json)."""
    tr = load_b_trades()
    out: dict[str, Any] = {}
    for pol in ("FCFS", "REPLACE-low", "REPLACE-high"):
        res = run_policy(pol, tr)
        res["mean_r"] = res["ev"] / res["n"]
        out[pol] = res
        print(f"[{pol:12s}] n={res['n']} EV={res['ev']:+.1f}R "
              f"mean={res['mean_r']:+.3f}R "
              f"maxDD(event)={res['dd']:.2f}R "
              f"replaced={res['replaced']}")

    gain_lo = out["REPLACE-low"]["ev"] - out["FCFS"]["ev"]
    gain_hi = out["REPLACE-high"]["ev"] - out["FCFS"]["ev"]
    fcfs_abs = max(abs(out["FCFS"]["ev"]), 1e-9)
    print(f"REPLACE vs FCFS EV gain: [{gain_lo:+.1f}R, {gain_hi:+.1f}R] "
          f"({gain_lo / fcfs_abs:+.0%} .. {gain_hi / fcfs_abs:+.0%})")

    # --- 4h-resolution outcome correlations (cluster check) ---
    b4 = 4 * HOUR
    t4 = (pl.read_parquet(
              REPO / "runs" / "d8b" / "wf_trades.parquet")
          .filter(pl.col("cell") == "B")
          .with_columns(((pl.col("ts_entry") + pl.col("dur_h") * HOUR)
                         // b4).alias("b")))
    buckets = {}
    for t in sorted(t4["asset"].unique().to_list()):
        sub = t4.filter(pl.col("asset") == t)
        b = sub["b"].to_numpy()
        lo, hi = b.min(), b.max()
        v = np.zeros(int(hi - lo + 1))
        np.add.at(v, b - lo, sub["r_pess"].to_numpy())
        buckets[t] = v
    n = min(len(v) for v in buckets.values())
    corr4 = {}
    keys = list(buckets)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = buckets[keys[i]][-n:]
            b = buckets[keys[j]][-n:]
            c = float(np.corrcoef(a, b)[0, 1])
            corr4[f"{keys[i]}|{keys[j]}"] = c
            print(f"4h corr({keys[i].split('-')[0]}, "
                  f"{keys[j].split('-')[0]}) = {c:+.2f}"
                  f" {'STILL CLUSTER' if c > 0.8 else 'below 0.8 at 4h'}")

    out["corr_4h"] = corr4
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "admission_policies.json").write_text(
        json.dumps(out, indent=1))
    print("saved runs/admission_policies.json")


if __name__ == "__main__":
    main()