"""D.11: portfolio admission policies - fix FCFS slot-mechanics alpha loss.
(formerly ``scripts/d11_admission.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Finding (D.2b): first-come-first-served capping rejects BETTER trades
(rejected mean r_pess +0.484 vs accepted +0.441) - pure capacity loss,
and reject rate drifts 16%->24% as candidate density grows.

Policies on the same 1040-trade WF-B stream (cap = 2 concurrent, one
crypto cluster):
  FCFS         - current: slots full -> reject.
  REPLACE-low  - slots full -> if new score > worst open score, close
                 worst and take new; replaced trade contributes 0
                 (conservative: mid-flight close assumed to give back).
  REPLACE-high - same, but replaced trade keeps its full isolated
                 r_pess (optimistic bound).
Realized equity is event-based (R credited at exit) -> DD not flattered
by daily aggregation.  Also: 4h-resolution outcome correlations
(cluster-limit check at finer granularity than daily).
"""

from __future__ import annotations

import json

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
HOUR = 3_600_000
CAP = 2

tr = (pl.read_parquet(REPO / "runs" / "d8b" / "wf_trades.parquet")
      .filter(pl.col("cell") == "B")
      .with_columns((pl.col("ts_entry") + pl.col("dur_h") * HOUR).alias("ts_exit"))
      .sort("ts_entry").to_dicts())


def run_policy(policy):
    open_pos, entered, replaced = [], [], []
    for r in tr:
        open_pos = [x for x in open_pos if x["ts_exit"] > r["ts_entry"]]
        if len(open_pos) < CAP:
            open_pos.append(r)
            entered.append(r)
        elif policy.startswith("REPLACE"):
            worst = min(open_pos, key=lambda x: x["s"])
            if r["s"] > worst["s"]:
                open_pos.remove(worst)
                open_pos.append(r)
                entered.append(r)
                replaced.append(worst)
    # event equity: contributions at exits; replaced contribute 0 (low) / full (high)
    ev = []
    for r in entered:
        if any(r is x for x in replaced):
            ev.append((r["ts_exit"], 0.0 if policy == "REPLACE-low" else r["r_pess"]))
        else:
            ev.append((r["ts_exit"], r["r_pess"]))
    ev.sort(key=lambda x: x[0])
    eq = np.cumsum([x[1] for x in ev])
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))
    dd = float(np.max(peak[1:] - eq))
    return {"n": len(entered), "ev": float(eq[-1]), "dd": dd,
            "replaced": len(replaced)}


out = {}
for pol in ("FCFS", "REPLACE-low", "REPLACE-high"):
    res = run_policy(pol)
    res["mean_r"] = res["ev"] / res["n"]
    out[pol] = res
    print(f"[{pol:12s}] n={res['n']} EV={res['ev']:+.1f}R "
          f"mean={res['mean_r']:+.3f}R maxDD(event)={res['dd']:.2f}R "
          f"replaced={res['replaced']}")

gain_lo = out["REPLACE-low"]["ev"] - out["FCFS"]["ev"]
gain_hi = out["REPLACE-high"]["ev"] - out["FCFS"]["ev"]
print(f"REPLACE vs FCFS EV gain: [{gain_lo:+.1f}R, {gain_hi:+.1f}R] "
      f"({gain_lo / max(abs(out['FCFS']['ev']), 1e-9):+.0%} .. "
      f"{gain_hi / max(abs(out['FCFS']['ev']), 1e-9):+.0%})")

# --- 4h-resolution outcome correlations (cluster check) ---
B4 = 4 * HOUR
t4 = (pl.read_parquet(REPO / "runs" / "d8b" / "wf_trades.parquet")
      .filter(pl.col("cell") == "B")
      .with_columns(((pl.col("ts_entry") + pl.col("dur_h") * HOUR) // B4).alias("b")))
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
        print(f"4h corr({keys[i].split('-')[0]}, {keys[j].split('-')[0]}) = {c:+.2f}"
              f" {'STILL CLUSTER' if c > 0.8 else 'below 0.8 at 4h'}")

out["corr_4h"] = corr4
(REPO / "runs" / "d11_admission.json").write_text(json.dumps(out, indent=1))
print("saved runs/d11_admission.json")
