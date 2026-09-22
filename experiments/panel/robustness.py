"""Robustness checks (follow-ups 2-4 from STATUS):

1. bootstrap block-length sensitivity 10/20/30/60 days -> does p95/p99
   DD grow with block length (regimes undersampled)?
2. trade-event equity DD (exact realized sequence) vs daily-aggregated
   DD -> is daily aggregation optimistic?
3. capped-out trades: r_pess distribution vs accepted (systematic
   filter or lost signal?), reject rate over time.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl

from experiments import REPO


TR = pl.read_parquet(REPO / "runs" / "d8b" / "wf_trades.parquet").filter(
    pl.col("cell") == "B")
TAGS = sorted(TR["asset"].unique().to_list())
HOUR = 3_600_000
CAP_TOTAL, CAP_CLUSTER, CORR_LIMIT = 4, 2, 0.8
N_SIMS = 1000

tr = TR.with_columns((pl.col("ts_entry") + pl.col("dur_h") * HOUR).alias("ts_exit"))
tr = tr.with_columns((pl.col("ts_entry") // 86_400_000).alias("d_in"))
d0, d1 = int(tr["d_in"].min()), int(tr["d_in"].max())
ndays = d1 - d0 + 1


# price-corr clustering (same as d9)
def dclose(t):
    df = pl.read_parquet(REPO / f"data/okx/raw_{t}_1m.parquet")
    ts = df["ts"].to_numpy() // 86_400_000
    cl = df["close"].to_numpy()
    days = np.unique(ts)
    return days, np.diff(np.log(np.array([cl[ts == d][-1] for d in days])))


parent = {t: t for t in TAGS}


def find(x):
    while parent[x] != x:
        x = parent[x]
    return x


for i, a in enumerate(TAGS):
    for j, b in enumerate(TAGS):
        if j > i:
            da, ra_ = dclose(a)
            db, rb_ = dclose(b)
            common = np.intersect1d(da[1:], db[1:])
            if np.corrcoef(ra_[np.isin(da[1:], common)],
                           rb_[np.isin(db[1:], common)])[0, 1] > CORR_LIMIT:
                parent[find(b)] = find(a)
clusters = {t: find(t) for t in TAGS}

# --- 3. capped-out trades analysis ---
rows = tr.sort("ts_entry").to_dicts()
open_pos, accepted, rejected = [], [], []
for r in rows:
    open_pos = [x for x in open_pos if x[0] > r["ts_entry"]]
    open_cl = [x for x in open_pos if x[1] == clusters[r["asset"]]]
    if len(open_pos) < CAP_TOTAL and len(open_cl) < CAP_CLUSTER:
        accepted.append(r)
        open_pos.append((r["ts_exit"], clusters[r["asset"]]))
    else:
        rejected.append(r)
acc_r = np.array([r["r_pess"] for r in accepted])
rej_r = np.array([r["r_pess"] for r in rejected])
print(f"[capped-out] accepted={len(acc_r)} rejected={len(rej_r)}")
print(f"  r_pess accepted : mean={acc_r.mean():+.3f} "
      f"p25={np.percentile(acc_r, 25):+.2f} p75={np.percentile(acc_r, 75):+.2f}")
if rej_r.size:
    print(f"  r_pess rejected : mean={rej_r.mean():+.3f} "
          f"p25={np.percentile(rej_r, 25):+.2f} p75={np.percentile(rej_r, 75):+.2f}")
    print(f"  -> rejected {'WORSE than accepted (cap acts as a free filter)' if rej_r.mean() < acc_r.mean() else 'same/better (pure capacity loss)'}")
# reject rate over time (thirds)
edges = np.linspace(0, len(rows), 4).astype(int)
rates = [np.mean([r not in accepted for r in rows[edges[i]:edges[i + 1]]])
         for i in range(3)]
print(f"  reject rate by time thirds: {[f'{x:.0%}' for x in rates]}")


# --- 2. trade-event DD vs daily-aggregated DD (capped portfolio) ---
def max_dd(x):
    peak = np.maximum.accumulate(np.concatenate([[0.0], x]))
    return float(np.max(peak[1:] - x))


ev_exit = np.array([r["r_pess"] for r in
                    sorted(accepted, key=lambda r: r["ts_exit"])])
dd_event = max_dd(np.cumsum(ev_exit))
v = np.zeros(ndays)
np.add.at(v, np.array([r["d_in"] - d0 for r in accepted]), acc_r)
dd_daily = max_dd(np.cumsum(v))
print(f"\n[daily vs event] daily-entry DD={dd_daily:.2f}R | "
      f"trade-event DD={dd_event:.2f}R | "
      f"bias={(dd_daily - dd_event) / dd_event:+.0%}")

# --- 1. block-length sensitivity ---
rng = np.random.default_rng(7)
sens = {}
for block in (10, 20, 30, 60):
    nblock = int(np.ceil(ndays / block))
    starts = rng.integers(0, ndays, (N_SIMS, nblock))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(N_SIMS, -1) % ndays
    dds = np.array([max_dd(np.cumsum(v[idx[s]])) for s in range(N_SIMS)])
    q = np.percentile(dds, [50, 95, 99])
    sens[block] = {"p50": float(q[0]), "p95": float(q[1]), "p99": float(q[2])}
    print(f"[block={block:2d}d] maxDD p50={q[0]:.2f} p95={q[1]:.2f} "
          f"p99={q[2]:.2f}R  ({q[1] * 1.0:.1f}% eq @1R=1%)")

trend = sens[60]["p95"] / sens[10]["p95"]
print(f"p95(60d)/p95(10d) = {trend:.2f} -> "
      f"{'10d blocks UNDERSTATE the tail, quote 60d numbers' if trend > 1.3 else '10d blocks adequate (tail stable)'}")

out = {"capped_out": {"n_acc": len(acc_r), "n_rej": int(rej_r.size),
                      "mean_r_acc": float(acc_r.mean()),
                      "mean_r_rej": float(rej_r.mean()) if rej_r.size else None,
                      "reject_rate_thirds": [float(x) for x in rates]},
       "dd": {"daily": dd_daily, "event": dd_event},
       "block_sensitivity": sens}
(REPO / "runs" / "d9b_robustness.json").write_text(json.dumps(out, indent=1))
print("saved runs/d9b_robustness.json")

