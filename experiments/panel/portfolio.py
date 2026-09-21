"""Portfolio layer on WF-B trade series (BTC+ETH+SOL).

Inputs: runs/d8b/wf_trades.parquet (cell B, walk-forward, pess R).
Layers:
  1. correlation cluster check on daily per-asset R series (flag > 0.8);
  2. concurrency caps: max open positions total (4) and per cluster (2)
     simulated on real history with entry/exit times;
  3. stationary block bootstrap (1000 sims, 10-day blocks) of the daily
     portfolio return series -> max-DD distribution (1R = 1% risk);
     pre-registered flag: p95 DD > 30%.
  4. kill-switch: DD-triggered pause (K=4R drawdown -> 14 days no new
     entries) simulated path-wise inside each bootstrap draw.
"""

from __future__ import annotations

import json

from datetime import datetime, timezone

import numpy as np
import polars as pl

from experiments import REPO


TR = pl.read_parquet(REPO / "runs" / "d8b" / "wf_trades.parquet").filter(
    pl.col("cell") == "B")
TAGS = sorted(TR["asset"].unique().to_list())
HOUR = 3_600_000
RISK_PCT = 1.0          # 1R = 1% of equity
CAP_TOTAL, CAP_CLUSTER, CORR_LIMIT = 4, 2, 0.8
KILL_DD_R, KILL_PAUSE_D = 4.0, 14
N_SIMS, BLOCK_D = 1000, 10

tr = TR.with_columns(
    (pl.col("ts_entry") + pl.col("dur_h") * HOUR).alias("ts_exit"))
tr = tr.with_columns(
    (pl.col("ts_entry") // 86_400_000).alias("d_in"))
d0 = int(tr["d_in"].min())
d1 = int(tr["d_in"].max())
ndays = d1 - d0 + 1
print(f"trades(B)={tr.height} span={ndays}d "
      f"({datetime.fromtimestamp(d0 * 86400, tz=timezone.utc):%Y-%m-%d} .. "
      f"{datetime.fromtimestamp(d1 * 86400, tz=timezone.utc):%Y-%m-%d})")

# --- 1. per-asset daily series and correlations ---
daily = {}
for t in TAGS:
    sub = tr.filter(pl.col("asset") == t)
    v = np.zeros(ndays)
    np.add.at(v, sub["d_in"].to_numpy() - d0, sub["r_pess"].to_numpy())
    daily[t] = v
corr = np.eye(len(TAGS))
for i, a in enumerate(TAGS):
    for j, b in enumerate(TAGS):
        if j > i:
            c = np.corrcoef(daily[a], daily[b])[0, 1]
            corr[i, j] = corr[j, i] = c
            print(f"corr({a.split('-')[0]}, {b.split('-')[0]}) = {c:+.2f}"
                  f" {'CLUSTER' if c > CORR_LIMIT else ''}")
parent = {t: t for t in TAGS}


def find(x):
    while parent[x] != x:
        x = parent[x]
    return x


for i, a in enumerate(TAGS):
    for j, b in enumerate(TAGS):
        if j > i and corr[i, j] > CORR_LIMIT:
            parent[find(b)] = find(a)
clusters = {t: find(t) for t in TAGS}
print("pnl clusters:", {t.split("-")[0]: c.split("-")[0] for t, c in clusters.items()})

# price-level correlation drives concurrent adverse moves; the ~0.8
# cluster threshold is about EXPOSURE, not strategy P&L (geometry
# dominates outcomes -> daily-P&L corr is low).
pcorr = {}
for i, a in enumerate(TAGS):
    for j, b in enumerate(TAGS):
        if j <= i:
            continue
        def dclose(t):
            df = pl.read_parquet(REPO / f"data/okx/raw_{t}_1m.parquet")
            ts = df["ts"].to_numpy() // 86_400_000
            cl = df["close"].to_numpy()
            days = np.unique(ts)
            last = np.array([cl[ts == d][-1] for d in days])
            return days, np.diff(np.log(last))
        da, ra_ = dclose(a)
        db, rb_ = dclose(b)
        common = np.intersect1d(da[1:], db[1:])
        c = np.corrcoef(ra_[np.isin(da[1:], common)],
                        rb_[np.isin(db[1:], common)])[0, 1]
        pcorr[f"{a}|{b}"] = float(c)
        print(f"price corr({a.split('-')[0]}, {b.split('-')[0]}) = {c:+.2f}"
              f" {'CLUSTER' if c > CORR_LIMIT else ''}")
        if c > CORR_LIMIT:
            parent[find(b)] = find(a)
clusters = {t: find(t) for t in TAGS}
print("clusters (price):",
      {t.split("-")[0]: c.split("-")[0] for t, c in clusters.items()})

# --- 2. concurrency caps on real history ---
rows = tr.sort("ts_entry").to_dicts()
acc_rows = None
for cap_t, cap_c, label in ((10**9, 10**9, "uncapped"),
                            (CAP_TOTAL, CAP_CLUSTER, "capped")):
    open_pos, accepted = [], []
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in rows:
        open_pos = [x for x in open_pos if x[0] > r["ts_entry"]]
        open_cl = [x for x in open_pos if x[1] == clusters[r["asset"]]]
        if len(open_pos) < cap_t and len(open_cl) < cap_c:
            accepted.append(r)
            open_pos.append((r["ts_exit"], clusters[r["asset"]]))
            eq += r["r_pess"]
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
    print(f"[{label}] accepted={len(accepted)} "
          f"rejected={len(rows) - len(accepted)} EV={eq:+.1f}R maxDD={dd:.1f}R")
    if label == "capped":
        acc_rows = accepted

v = np.zeros(ndays)
np.add.at(v, np.array([r["d_in"] - d0 for r in acc_rows]),
          np.array([r["r_pess"] for r in acc_rows]))

# --- 3+4. block bootstrap of daily returns; kill-switch path-sim ---
rng = np.random.default_rng(7)
nblock = int(np.ceil(ndays / BLOCK_D))
starts = rng.integers(0, ndays, (N_SIMS, nblock))
idx = (starts[:, :, None] + np.arange(BLOCK_D)[None, None, :]).reshape(N_SIMS, -1) % ndays


def max_dd(equity):
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))
    return float(np.max(peak[1:] - equity))


dds = np.array([max_dd(np.cumsum(v[idx[s]])) for s in range(N_SIMS)])
ev_plain = np.array([v[idx[s]].sum() for s in range(N_SIMS)])


def kill_sim(K, pause_days):
    dd_ = np.zeros(N_SIMS)
    ev_ = np.zeros(N_SIMS)
    skp = np.zeros(N_SIMS)
    for s in range(N_SIMS):
        path = v[idx[s]]
        eqk, peak, dd, pause_until, skipped = 0.0, 0.0, 0.0, -1, 0.0
        for k in range(ndays):
            day = idx[s][k]
            if day <= pause_until:
                skipped += path[k]
                continue
            eqk += path[k]
            peak = max(peak, eqk)
            dd = max(dd, peak - eqk)
            if peak - eqk >= K:
                pause_until = day + pause_days
        dd_[s] = dd
        ev_[s] = eqk
        skp[s] = 100 * abs(skipped) / max(abs(eqk) + abs(skipped), 1e-9)
    return dd_, ev_, skp


results = {"plain": (dds, ev_plain, np.zeros(N_SIMS))}
for K, P in ((KILL_DD_R, KILL_PAUSE_D), (2.0, 14), (2.0, 7)):
    tag = f"kill K={K}R/P={P}d"
    results[tag] = kill_sim(K, P)
for name, (dd_, ev_, skp) in results.items():
    q = np.percentile(dd_, [50, 95, 99])
    print(f"[{name}] maxDD p50={q[0]:.1f}R p95={q[1]:.1f}R p99={q[2]:.1f}R "
          f"(p95={q[1] * RISK_PCT:.0f}% eq @1R=1%) "
          f"flag={'p95>30% !!!' if q[1] > 30 else 'ok'} | "
          f"EV p50={np.percentile(ev_, 50):+.1f}R | "
          f"skipped {np.mean(skp):.1f}%")

out = {
    "pnl_corr": {f"{a}|{b}": float(corr[i, j])
             for i, a in enumerate(TAGS) for j, b in enumerate(TAGS) if j > i},
    "price_corr": pcorr,
    "clusters": clusters,
    "concurrency": {"cap_total": CAP_TOTAL, "cap_cluster": CAP_CLUSTER,
                    "n_accepted": len(acc_rows),
                    "n_rejected": len(rows) - len(acc_rows)},
    "bootstrap": {
        "plain": {"dd_p50": float(np.percentile(dds, 50)),
                  "dd_p95": float(np.percentile(dds, 95)),
                  "dd_p99": float(np.percentile(dds, 99)),
                  "ev_p50": float(np.percentile(ev_plain, 50))},
        "kill_variants": {name: {"dd_p50": float(np.percentile(dd_, 50)),
                                 "dd_p95": float(np.percentile(dd_, 95)),
                                 "dd_p99": float(np.percentile(dd_, 99)),
                                 "ev_p50": float(np.percentile(ev_, 50)),
                                 "skipped_ev_pct": float(np.mean(skp_))}
                          for name, (dd_, ev_, skp_) in results.items()
                          if name != "plain"}},
    "flag_p95_dd_gt_30": bool(np.percentile(dds, 95) * RISK_PCT > 30),
}
(REPO / "runs" / "portfolio.json").write_text(json.dumps(out, indent=1))
print("saved runs/portfolio.json")
