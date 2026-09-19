"""D.8b: walk-forward A vs B - confirm multi-asset LGBM (B) as baseline.
(formerly ``scripts/d8b_wf_ab.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

8 folds x 56 days, expanding train, 7-day embargo. Per fold:
  A: per-asset LGBM   B: multi-asset LGBM (asset_id feature)
Gate: fit_rule_table on the fold's train. Same unified sim + state
machine. Decision rule (pre-registered): B > A pooled in 6+/8 folds ->
upgrade accepted; 4/8 ambiguous; <=3/8 -> B-A is a one-regime artifact.
Note: state machine slots reset at fold boundaries (path-dependence
approximation).
"""

from __future__ import annotations

import sys

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf import resample_ohlcv  # noqa: E402
from engine.mtf_model import (  # noqa: E402
    build_features,
    candidate_key,
    fit_rule_table,
    trade_curve_stats,
)
from engine.state_machine import run_state_machine  # noqa: E402
from engine.sim import pess, sim  # noqa: E402


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
N_FOLDS, FOLD_DAYS, EMBARGO_DAYS = 8, 56, 7
DAY_MS = 86_400_000


def load_asset(tag: str) -> dict:
    raw = resample_ohlcv(
        pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet"), "1h"
    )
    o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(raw)
    panel = candidate_key(
        pl.read_parquet(REPO / f"data/mtf_dataset/{tag.replace('-', '')}_1h.parquet").filter(
            (pl.col("execution") == "market")
            & (pl.col("target") == 2.0)
            & pl.col("r_net").is_not_nan()
            & (pl.col("exit_idx") >= 0)
            & pl.col("risk_unit").is_not_nan()
        )
    ).sort("_cand")
    panel = panel.with_columns(
        pl.struct(pl.exclude("_cand"))
        .map_elements(pess, return_dtype=pl.Float64)
        .alias("r_pess")
    )
    feats = build_features(panel, ("rule",))
    feats["risk_pct"] = (panel["risk_unit"] / panel["fill_price"]).to_numpy()
    feats["cost_R"] = (0.0025 * panel["fill_price"] / panel["risk_unit"]).to_numpy()
    return {"tag": tag, "panel": panel, "feats": feats,
            "n": n, "o": o, "h": h, "l": l, "c": c}


print("loading assets...", flush=True)
DATA = {t: load_asset(t) for t in TAGS}
for t, d in DATA.items():
    print(t, "rows:", d["panel"].height,
          "range:", d["panel"]["ts"].min(), "->", d["panel"]["ts"].max())

# multi-asset frame
feats_all = []
asset_row_all, ys_all, ts_all = [], [], []
for ai, t in enumerate(TAGS):
    d = DATA[t]
    f = d["feats"].copy()
    f["asset"] = pd.Categorical([t] * len(f))
    feats_all.append(f)
    asset_row_all.append(np.full(len(f), ai))
    ys_all.append(d["panel"]["r_pess"].to_numpy())
    ts_all.append(d["panel"]["ts"].to_numpy())
FEATS_ALL = pd.concat(feats_all, ignore_index=True)
for col in FEATS_ALL.columns:
    if str(FEATS_ALL[col].dtype) == "category":
        FEATS_ALL[col] = FEATS_ALL[col].cat.codes.astype(np.float32)
    elif FEATS_ALL[col].dtype == object:
        FEATS_ALL[col] = pd.Categorical(FEATS_ALL[col]).codes.astype(np.float32)
TAB_ALL = np.nan_to_num(FEATS_ALL.to_numpy().astype(np.float32),
                        nan=0.0, posinf=0.0, neginf=0.0)
ASSET_ROW = np.concatenate(asset_row_all)
Y_ALL = np.concatenate(ys_all).astype(np.float32)
TS_ALL = np.concatenate(ts_all)
row_parts, off = [], 0
for t in TAGS:
    cands = DATA[t]["panel"]["_cand"].unique(maintain_order=True).to_list()
    row_parts.append(DATA[t]["panel"]["_cand"]
                     .replace_strict(cands, list(range(len(cands))))
                     .to_numpy() + off)
    off += len(cands)
ROW_ALL = np.concatenate(row_parts)
print("multi rows:", len(FEATS_ALL))


def lgb_ranker(tr_ix):
    rel = np.clip(np.round((Y_ALL + 2) * 2), 0, 12).astype(int)
    order = np.lexsort((np.arange(len(Y_ALL)), ROW_ALL))
    inv = np.empty(len(Y_ALL), np.int64)
    inv[order] = np.arange(len(Y_ALL))
    fs = FEATS_ALL.iloc[order].reset_index(drop=True)
    rows_o = ROW_ALL[order]
    in_tr = np.isin(np.arange(len(rows_o)), inv[tr_ix])
    gs, i = [], 0
    while i < len(rows_o):
        j = i
        while j < len(rows_o) and rows_o[j] == rows_o[i]:
            j += 1
        if in_tr[i]:
            gs.append(j - i)
        i = j
    m = lgb.LGBMRanker(objective="lambdarank", n_estimators=300,
                       learning_rate=0.05, num_leaves=15, min_child_samples=30,
                       label_gain=list(range(13)), random_state=7, verbosity=-1)
    m.fit(fs[in_tr], rel[order][in_tr], group=gs, callbacks=[])
    return m.predict(fs)


picks_out = []


def replay_panel(panel, d, fold=None, asset=None):
    """panel: one asset's panel rows with 's' and 'is_test' columns."""
    table = fit_rule_table(panel.filter(~pl.col("is_test")))
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    picks = (panel.sort(["_cand", "s"]).group_by("_cand").last()
             .with_columns(fmt.replace_strict([f"{r}|{s}" for (r, s) in table],
                 list(table.values()), default="x").alias("tr"))
             .filter(pl.col("rule") == pl.col("tr"))
             .sort("entry_idx").filter(pl.col("is_test")))
    if fold is not None:
        for r_ in picks.iter_rows(named=True):
            picks_out.append({
                "asset": asset, "fold": fold, "cand": r_["_cand"],
                "ts": int(r_["ts"]), "entry_idx": int(r_["entry_idx"]),
                "side": r_["side"], "fill_price": float(r_["fill_price"]),
                "sl_price": float(r_["sl_price"]), "tp_price": float(r_["tp_price"]),
                "risk_unit": float(r_["risk_unit"]), "atr_i": float(r_["atr_i"]),
                "s": float(r_["s"]), "r_pess": float(r_["r_pess"])})
    sig = []
    for r in picks.iter_rows(named=True):
        i0 = int(r["entry_idx"]) + 1
        if i0 >= d["n"]:
            continue
        ro, rp, jx = sim(d["o"], d["h"], d["l"], d["c"], i0, r["side"],
                         r["sl_price"], r["tp_price"], 48, r["atr_i"])
        if not np.isfinite(ro):
            continue
        sig.append({"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
                    "side": r["side"], "priority": 0.0,
                    "r_net": float(rp), "r_opt": float(ro), "exit_idx": jx})
    taken, _ = run_state_machine(sig)
    r = np.array([x["r_net"] for x in taken])
    # map taken trades back to decision ts + holding for portfolio layer
    meta = {r_["_cand"]: (int(r_["ts"]), int(r_["entry_idx"]), float(r_["s"]))
            for r_ in picks.iter_rows(named=True)}
    ts_a = np.array([meta[x["cand"]][0] for x in taken], dtype=np.int64)
    dur_h = np.array([int(x["exit_idx"]) - meta[x["cand"]][1]
                      for x in taken], dtype=np.int64)
    sc = np.array([meta[x["cand"]][2] for x in taken], dtype=np.float32)
    return r, ts_a, dur_h, sc


ROW_SCORES = {}


def run_cell(cell, tr_mask, te_mask):
    """cell: 'A' per-asset models; 'B' one multi model.
    -> {tag: (r_test, ts_entry, dur_h)}.
    """
    if cell == "A":
        sc = np.empty(len(Y_ALL), np.float32)
        for ai, t in enumerate(TAGS):
            m = tr_mask & (ASSET_ROW == ai)
            sc[ASSET_ROW == ai] = lgb_ranker(np.where(m)[0])[ASSET_ROW == ai]
    else:
        sc = lgb_ranker(np.where(tr_mask)[0])
    out = {}
    for ai, t in enumerate(TAGS):
        m = ASSET_ROW == ai
        ROW_SCORES[cell, t] = sc[m]
        pm = DATA[t]["panel"].with_columns(
            pl.Series("s", sc[m]),
            pl.Series("is_test", te_mask[m]))
        out[t] = replay_panel(pm, DATA[t])
    return out


t0 = int(min(DATA[t]["panel"]["ts"].min() for t in TAGS))
t1 = int(max(DATA[t]["panel"]["ts"].max() for t in TAGS))
fold_len = FOLD_DAYS * DAY_MS
folds = [(t0 + W * fold_len, t0 + (W + 1) * fold_len) for W in
         range(max(0, (t1 - t0) // fold_len - N_FOLDS + 1),
               (t1 - t0) // fold_len + 1)][-N_FOLDS:]

print(f"\n=== walk-forward A vs B: {len(folds)} folds x {FOLD_DAYS}d, "
      f"embargo {EMBARGO_DAYS}d ===", flush=True)
from datetime import datetime, timezone  # noqa: E402


rows_out = []
agg = {"A": [], "B": []}
trades_out = []
per_wins = {t: 0 for t in TAGS}
per_valid = {t: 0 for t in TAGS}
wins = 0
for fi, (fs, fe) in enumerate(folds):
    tr_mask = TS_ALL < fs - EMBARGO_DAYS * DAY_MS
    te_mask = (TS_ALL >= fs) & (TS_ALL < fe)
    ra, rb = run_cell("A", tr_mask, te_mask), run_cell("B", tr_mask, te_mask)
    ea = np.concatenate([ra[t][0] for t in TAGS])
    eb = np.concatenate([rb[t][0] for t in TAGS])
    agg["A"].append(ea)
    agg["B"].append(eb)
    for ai_, t in enumerate(TAGS):
        replay_panel(DATA[t]["panel"].with_columns(
            pl.Series("s", ROW_SCORES["B", t]), pl.Series("is_test", te_mask[ASSET_ROW == ai_])),
            DATA[t], fold=fi, asset=t)
        r_, ts_, du_, sc_ = rb[t]
        for k in range(r_.size):
            trades_out.append({"asset": t, "fold": fi, "ts_entry": int(ts_[k]),
                               "dur_h": int(du_[k]), "r_pess": float(r_[k]),
                               "s": float(sc_[k]), "cell": "B"})
        r_, ts_, du_, _ = ra[t]
        for k in range(r_.size):
            trades_out.append({"asset": t, "fold": fi, "ts_entry": int(ts_[k]),
                               "dur_h": int(du_[k]), "r_pess": float(r_[k]),
                               "s": float("nan"), "cell": "A"})
    win = bool(ea.size and eb.size and eb.mean() > ea.mean())
    wins += win
    d0 = datetime.fromtimestamp(fs / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    per = " ".join(
        f"{t.split('-')[0]}:{ra[t][0].mean():+.2f}/{rb[t][0].mean():+.2f}"
        f"(n{ra[t][0].size}/{rb[t][0].size})" if ra[t][0].size and rb[t][0].size
        else f"{t.split('-')[0]}:--" for t in TAGS)
    for t in TAGS:
        if ra[t][0].size and rb[t][0].size:
            per_valid[t] += 1
            per_wins[t] += int(rb[t][0].mean() > ra[t][0].mean())
    print(f"f{fi} {d0} train={int(tr_mask.sum())} A={ea.mean():+.3f}(n{ea.size}) "
          f"B={eb.mean():+.3f}(n{eb.size}) {'B>A' if win else 'A>=B'} | {per}",
          flush=True)
    rows_out.append({"fold": fi, "start": d0, "A": float(ea.mean()),
                     "B": float(eb.mean()), "nA": int(ea.size),
                     "nB": int(eb.size), "B_win": win})

fa, fb = np.concatenate(agg["A"]), np.concatenate(agg["B"])
dda = trade_curve_stats(fa)["max_dd_r"]
ddb = trade_curve_stats(fb)["max_dd_r"]
print(f"\nWF total: A pess={fa.mean():+.3f} (n={fa.size}, dd={dda:.1f}R) | "
      f"B pess={fb.mean():+.3f} (n={fb.size}, dd={ddb:.1f}R)")
print(f"B wins pooled: {wins}/{len(folds)}  "
      f"(pre-registered: 6+ accept, 4-5 ambiguous, <=3 artifact)")
for t in TAGS:
    print(f"B wins {t.split('-')[0]}: {per_wins[t]}/{per_valid[t]}")

import json  # noqa: E402


(REPO / "runs" / "d8b").mkdir(parents=True, exist_ok=True)
pl.DataFrame(trades_out).write_parquet(REPO / "runs" / "d8b" / "wf_trades.parquet")
pl.DataFrame(picks_out).write_parquet(REPO / "runs" / "d8b" / "wf_picks.parquet")
print("picks exported:", len(picks_out))
(REPO / "runs" / "d8b" / "wf_folds.json").write_text(json.dumps({
    "folds": rows_out, "total": {"A": float(fa.mean()), "B": float(fb.mean()),
                                 "ddA": float(dda), "ddB": float(ddb),
                                 "wins_pooled": wins, "n_folds": len(folds)},
    "wins_per_asset": per_wins}, indent=1))
print("saved runs/d8b/wf_folds.json")


