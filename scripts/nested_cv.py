"""D.10: nested CV on the multi-asset LGBM head (B).
(formerly ``scripts/d10_nested_cv.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Closes the hyperparameter selection bias before external quoting.
Outer loop: the 8 walk-forward folds (expanding train, 7d embargo).
Inner loop: last 25% of fold-train rows by time (3d gap) = inner-val;
grid of 6 LGBM configs selected by inner-val NDCG (candidate groups).
Final fit on the full fold-train with the selected config -> replay on
fold-test (gate + unified sim + state machine), identical protocol to
D.8b.  Discount vs fixed-params B (+0.450R) estimates selection bias.
"""

from __future__ import annotations

import json
import sys

from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.mtf import resample_ohlcv  # noqa: E402
from ai.mtf_model import (  # noqa: E402
    build_features,
    candidate_key,
    fit_rule_table,
)
from ai.state_machine import run_state_machine  # noqa: E402
from scripts.sim_engine import pess, sim  # noqa: E402


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
N_FOLDS, FOLD_DAYS, EMBARGO_DAYS = 8, 56, 7
DAY_MS = 86_400_000
INNER_VAL_FRAC, INNER_GAP_D = 0.25, 3
GRID = [{"n_estimators": ne, "num_leaves": lv, "learning_rate": 0.05}
        for ne in (150, 400) for lv in (7, 15, 31)]
FIXED = {"n_estimators": 300, "num_leaves": 15, "learning_rate": 0.05}


def load_asset(tag: str) -> dict:
    raw = resample_ohlcv(
        pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet"), "1h")
    o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(raw)
    panel = candidate_key(
        pl.read_parquet(REPO / f"data/mtf_dataset/{tag.replace('-', '')}_1h.parquet").filter(
            (pl.col("execution") == "market")
            & (pl.col("target") == 2.0)
            & pl.col("r_net").is_not_nan()
            & (pl.col("exit_idx") >= 0)
            & pl.col("risk_unit").is_not_nan())
    ).sort("_cand")
    panel = panel.with_columns(
        pl.struct(pl.exclude("_cand"))
        .map_elements(pess, return_dtype=pl.Float64).alias("r_pess"))
    feats = build_features(panel, ("rule",))
    feats["risk_pct"] = (panel["risk_unit"] / panel["fill_price"]).to_numpy()
    feats["cost_R"] = (0.0025 * panel["fill_price"] / panel["risk_unit"]).to_numpy()
    return {"panel": panel, "feats": feats, "n": n,
            "o": o, "h": h, "l": l, "c": c}


print("loading assets...", flush=True)
DATA = {t: load_asset(t) for t in TAGS}
feats_all, asset_row_all, ys_all, ts_all, row_parts = [], [], [], [], []
off = 0
for ai, t in enumerate(TAGS):
    d = DATA[t]
    f = d["feats"].copy()
    f["asset"] = pd.Categorical([t] * len(f))
    feats_all.append(f)
    asset_row_all.append(np.full(len(f), ai))
    ys_all.append(d["panel"]["r_pess"].to_numpy())
    ts_all.append(d["panel"]["ts"].to_numpy())
    cands = d["panel"]["_cand"].unique(maintain_order=True).to_list()
    row_parts.append(d["panel"]["_cand"]
                     .replace_strict(cands, list(range(len(cands))))
                     .to_numpy() + off)
    off += len(cands)
FEATS = pd.concat(feats_all, ignore_index=True)
for col in FEATS.columns:
    if str(FEATS[col].dtype) == "category":
        FEATS[col] = FEATS[col].cat.codes.astype(np.float32)
    elif FEATS[col].dtype == object:
        FEATS[col] = pd.Categorical(FEATS[col]).codes.astype(np.float32)
FEATS = np.nan_to_num(FEATS.to_numpy().astype(np.float32),
                      nan=0.0, posinf=0.0, neginf=0.0)
Y = np.concatenate(ys_all).astype(np.float32)
TS = np.concatenate(ts_all)
ROW = np.concatenate(row_parts)
print("rows:", len(Y))


def fit_ranker(params, tr_ix, va_ix=None, ret_model=False):
    rel = np.clip(np.round((Y + 2) * 2), 0, 12).astype(int)
    order = np.lexsort((np.arange(len(Y)), ROW))
    inv = np.empty(len(Y), np.int64)
    inv[order] = np.arange(len(Y))
    fs = FEATS[order]
    rows_o = ROW[order]
    in_tr = np.isin(np.arange(len(rows_o)), inv[tr_ix])
    in_va = np.isin(np.arange(len(rows_o)), inv[va_ix]) if va_ix is not None else None
    gs, i = [], 0
    while i < len(rows_o):
        j = i
        while j < len(rows_o) and rows_o[j] == rows_o[i]:
            j += 1
        if in_tr[i]:
            gs.append(j - i)
        i = j
    m = lgb.LGBMRanker(objective="lambdarank", min_child_samples=30,
                       label_gain=list(range(13)), random_state=7,
                       verbosity=-1, **params)
    if va_ix is None:
        m.fit(fs[in_tr], rel[order][in_tr], group=gs, callbacks=[])
    else:
        gs_va, i = [], 0
        while i < len(rows_o):
            j = i
            while j < len(rows_o) and rows_o[j] == rows_o[i]:
                j += 1
            if in_va[i]:
                gs_va.append(j - i)
            i = j
        m.fit(fs[in_tr], rel[order][in_tr], group=gs,
              eval_set=[(fs[in_va], rel[order][in_va])],
              eval_group=[gs_va], eval_at=[50], callbacks=[],
              eval_metric="ndcg")
    return m if ret_model else m.predict(fs)


def ndcg_score(scores, va_ix):
    """Mean NDCG over candidate groups in inner-val."""
    rel = np.clip(np.round((Y + 2) * 2), 0, 12).astype(float)
    tot, cnt = 0.0, 0
    for g in np.unique(ROW[va_ix]):
        m = va_ix[ROW[va_ix] == g]
        s, r = scores[m], rel[m]
        order = np.argsort(-s)
        dcg = np.sum((2 ** r[order] - 1) / np.log2(np.arange(len(r)) + 2))
        ideal = np.sum((2 ** np.sort(r)[::-1] - 1) / np.log2(np.arange(len(r)) + 2))
        if ideal > 0:
            tot += dcg / ideal
            cnt += 1
    return tot / max(cnt, 1)


def replay_panel(panel, d):
    table = fit_rule_table(panel.filter(~pl.col("is_test")))
    fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    picks = (panel.sort(["_cand", "s"]).group_by("_cand").last()
             .with_columns(fmt.replace_strict([f"{r}|{s}" for (r, s) in table],
                 list(table.values()), default="x").alias("tr"))
             .filter(pl.col("rule") == pl.col("tr"))
             .sort("entry_idx").filter(pl.col("is_test")))
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
    return np.array([x["r_net"] for x in taken])


t0 = int(min(DATA[t]["panel"]["ts"].min() for t in TAGS))
t1 = int(max(DATA[t]["panel"]["ts"].max() for t in TAGS))
fold_len = FOLD_DAYS * DAY_MS
folds = [(t0 + W * fold_len, t0 + (W + 1) * fold_len) for W in
         range(max(0, (t1 - t0) // fold_len - N_FOLDS + 1),
               (t1 - t0) // fold_len + 1)][-N_FOLDS:]

ASSET_ROW = np.concatenate(asset_row_all)
print(f"[nested CV] {len(folds)} folds, grid={len(GRID)}", flush=True)
ev_nested, ev_fixed, chosen = [], [], []
for fi, (fs, fe) in enumerate(folds):
    tr_mask = TS < fs - EMBARGO_DAYS * DAY_MS
    te_mask = (TS >= fs) & (TS < fe)
    tr_ix = np.where(tr_mask)[0]
    tr_sorted = tr_ix[np.argsort(TS[tr_ix])]
    cut = tr_sorted[int(len(tr_sorted) * (1 - INNER_VAL_FRAC))]
    gap = INNER_GAP_D * DAY_MS
    inner_va = tr_sorted[TS[tr_sorted] >= TS[cut] + gap]
    inner_tr = tr_sorted[TS[tr_sorted] < TS[cut]]
    best_cfg, best_ndcg = None, -1.0
    for cfg in GRID:
        n = ndcg_score(fit_ranker(cfg, inner_tr), inner_va)
        if n > best_ndcg:
            best_ndcg, best_cfg = n, cfg
    chosen.append(best_cfg)
    scores = {"nested": fit_ranker(best_cfg, tr_ix),
              "fixed": fit_ranker(FIXED, tr_ix)}
    en, ef = [], []
    for ai, t in enumerate(TAGS):
        m = ASSET_ROW == ai
        pm = DATA[t]["panel"].with_columns(
            pl.Series("s", scores["nested"][m]),
            pl.Series("is_test", te_mask[m]))
        en.append(replay_panel(pm, DATA[t]))
        pm = DATA[t]["panel"].with_columns(
            pl.Series("s", scores["fixed"][m]),
            pl.Series("is_test", te_mask[m]))
        ef.append(replay_panel(pm, DATA[t]))
    en = np.concatenate(en)
    ef = np.concatenate(ef)
    ev_nested.append(en)
    ev_fixed.append(ef)
    d0s = datetime.fromtimestamp(fs / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"f{fi} {d0s} nested={en.mean():+.3f}(n{en.size}) "
          f"fixed={ef.mean():+.3f}(n{ef.size}) "
          f"cfg=ne{best_cfg['n_estimators']}/lv{best_cfg['num_leaves']}", flush=True)

an = np.concatenate(ev_nested)
af = np.concatenate(ev_fixed)
print(f"NESTED total: pess={an.mean():+.3f} (n={an.size}) | "
      f"FIXED total: pess={af.mean():+.3f} (n={af.size})")
print(f"selection-bias discount: {(af.mean() - an.mean()) / max(abs(af.mean()), 1e-9):+.1%}")
print(f"D.8b WF-B reference +0.450R -> external quote: {an.mean():+.3f}R")
from collections import Counter  # noqa: E402


print("chosen configs:", Counter((c["n_estimators"], c["num_leaves"]) for c in chosen))

out = {"folds": [{"fold": i, "nested": float(x.mean()),
                  "fixed": float(y.mean()), "cfg": c}
                 for i, (x, y, c) in enumerate(zip(ev_nested, ev_fixed, chosen))],
       "nested_total": float(an.mean()), "fixed_total": float(af.mean())}
(REPO / "runs").mkdir(exist_ok=True)
(REPO / "runs" / "d10_nested.json").write_text(json.dumps(out, indent=1))
print("saved runs/d10_nested.json")
