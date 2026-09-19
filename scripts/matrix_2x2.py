"""D.8: 2x2 matrix - per-asset vs multi-asset x LightGBM vs Transformer.
(formerly ``scripts/d8_2x2.py``; output artifacts keep the
d-prefixed filenames in ``runs/`` - see STATUS.md for history)

Isolates the two confounded variables of the multi-asset idea:
  A: per-asset LGBM   (current champion protocol, per asset)
  B: multi-asset LGBM (asset_id feature)      -> effect of DATA
  C: per-asset FairTrf (d7 recipe)            -> effect of MODEL
  D: multi-asset FairTrf (asset embedding)    -> test cell
D vs B isolates the model, D vs C isolates the data.  Same label
(pess R), same gate (per-asset rule table), same unified simulator.
No new indicators, no scale-up (pre-registered: EV <= 0 at n=3574).
"""

from __future__ import annotations

import sys

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
import torch
import torch.nn as nn


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.mtf import resample_ohlcv  # noqa: E402
from engine.mtf_model import (  # noqa: E402
    build_features,
    candidate_key,
    fit_rule_table,
    trade_curve_stats,
)
from engine.sim import pess, sim  # noqa: E402
from engine.state_machine import run_state_machine


DEV = "cuda" if torch.cuda.is_available() else "cpu"
WIN = 64
TAGS = (sys.argv[1].split(",") if len(sys.argv) > 1
         else ["BTC-USDT", "ETH-USDT", "SOL-USDT"])
WARM, EPOCHS, PATIENCE = 2, 50, 5


def load_asset(tag: str) -> dict:
    raw = resample_ohlcv(
        pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet"), "1h"
    )
    o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(raw)
    panel = candidate_key(
        pl.read_parquet(REPO / f"data/mtf_dataset/{tag.replace("-", "")}_1h.parquet").filter(
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
    cands = panel["_cand"].unique(maintain_order=True).to_list()
    row_cand = panel["_cand"].replace_strict(cands, list(range(len(cands)))).to_numpy()

    vol1h = np.log1p(raw["volume"].to_numpy())
    vmed = np.full(n, 1.0)
    for i in range(n):
        seg = vol1h[max(0, i - 500): i + 1]
        m = np.median(seg[np.isfinite(seg)])
        if m and m > 0:
            vmed[i] = m
    W = np.zeros((len(cands), WIN, 9), dtype=np.float32)
    ei = panel.group_by("_cand").agg(pl.col("entry_idx").first()).sort("_cand")["entry_idx"].to_numpy()
    sd = panel.group_by("_cand").agg(pl.col("side").first()).sort("_cand")["side"].to_numpy()
    vv = raw["volume"].to_numpy()
    for k, i in enumerate(ei):
        i = int(i)
        if i < WIN - 1 or i >= n:
            continue
        w = slice(i - WIN + 1, i + 1)
        ref = c[i]
        W[k, :, 0] = o[w] / ref - 1
        W[k, :, 1] = h[w] / ref - 1
        W[k, :, 2] = l[w] / ref - 1
        W[k, :, 3] = c[w] / ref - 1
        W[k, :, 4] = np.log1p(vv[w] / max(vmed[i], 1e-12))
        W[k, :, 5] = np.where(np.isfinite(vv[w]) & (c[w] > 0), h[w] / c[w] - l[w] / c[w], 0.0)
        W[k, :, 6] = 1.0 if sd[k] == "long" else -1.0
    W[np.isnan(W)] = 0.0
    return {
        "tag": tag, "raw": raw, "panel": panel, "feats": feats, "W": W,
        "row_cand": row_cand, "cands": cands, "n": n, "o": o, "h": h,
        "l": l, "c": c,
    }


print("loading assets...", flush=True)
DATA = {t: load_asset(t) for t in TAGS}
for t, d in DATA.items():
    print(t, "rows:", d["panel"].height, "cands:", len(d["cands"]))

# multi-asset concat
feats_all = []
row_cand_all, asset_row_all, ys_all, split_all = [], [], [], []
off = 0
for ai, t in enumerate(TAGS):
    d = DATA[t]
    f = d["feats"].copy()
    f["asset"] = pd.Categorical([t] * len(f))
    feats_all.append(f)
    row_cand_all.append(d["row_cand"] + off)
    asset_row_all.append(np.full(d["panel"].height, ai))
    ys_all.append(d["panel"]["r_pess"].to_numpy())
    split_all.append(d["panel"]["split"].to_numpy())
    d["cand_off"] = off
    off += len(d["cands"])
FEATS_ALL = pd.concat(feats_all, ignore_index=True)
ROW_ALL = np.concatenate(row_cand_all)
ASSET_ROW = np.concatenate(asset_row_all)
Y_ALL = np.concatenate(ys_all).astype(np.float32)
SPLIT_ALL = np.concatenate(split_all)
W_ALL = np.concatenate([DATA[t]["W"] for t in TAGS])
for col in FEATS_ALL.columns:
    if str(FEATS_ALL[col].dtype) == "category":
        FEATS_ALL[col] = FEATS_ALL[col].cat.codes.astype(np.float32)
    elif FEATS_ALL[col].dtype == object:
        FEATS_ALL[col] = pd.Categorical(FEATS_ALL[col]).codes.astype(np.float32)
TAB_ALL = np.nan_to_num(FEATS_ALL.to_numpy().astype(np.float32),
                        nan=0.0, posinf=0.0, neginf=0.0)
TAB_ALL = np.column_stack([TAB_ALL, ASSET_ROW.astype(np.float32)])
print("multi rows:", len(FEATS_ALL), "tab(+asset):", TAB_ALL.shape[1])

tW = torch.from_numpy(W_ALL).to(DEV)
tTab = torch.from_numpy(TAB_ALL).to(DEV)
tRows = torch.from_numpy(ROW_ALL).to(DEV)
tY = torch.from_numpy(Y_ALL).to(DEV)
NTAB = TAB_ALL.shape[1]


class FairTrf(nn.Module):
    def __init__(self, d=64, layers=2, heads=4):
        super().__init__()
        self.proj = nn.Linear(9 + NTAB, d)
        self.pos = nn.Parameter(torch.zeros(1, WIN, d))
        layer = nn.TransformerEncoderLayer(
            d, heads, d * 4, dropout=0.1, activation="gelu", batch_first=True
        )
        self.enc = nn.TransformerEncoder(layer, layers)
        self.head = nn.Linear(2 * d, 1)

    def forward(self, rows):
        tab = tTab[rows].unsqueeze(1).expand(-1, WIN, -1)
        z = self.proj(torch.cat([tW[tRows[rows]], tab], -1)) + self.pos
        z = self.enc(z)
        pooled = torch.cat([z.mean(1), z[:, -1]], -1)
        return self.head(pooled).squeeze(-1)


def ranknet_loss(scores, rows, ys):
    loss, n_pair = scores.new_zeros(()), 0
    for g in rows.unique():
        m = rows == g
        si, yi = scores[m], ys[m]
        if si.numel() < 2:
            continue
        diff = si.unsqueeze(1) - si.unsqueeze(0)
        yd = torch.sign(yi.unsqueeze(1) - yi.unsqueeze(0))
        mask = yd != 0
        if mask.any():
            loss = loss + nn.functional.softplus(-diff[mask] * yd[mask]).sum()
            n_pair += int(mask.sum())
    return loss / max(n_pair, 1)


def train_trf(tr_ix, va_ix, name):
    model = FairTrf().to(DEV)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda ep: min(
        (ep + 1) / WARM,
        0.5 * (1 + np.cos(np.pi * max(0, ep - WARM) / max(EPOCHS - WARM, 1)))))
    rng = np.random.default_rng(7)
    best, waited, state, curve, empty_batches = np.inf, 0, None, [], 0
    for ep in range(EPOCHS):
        model.train()
        perm = tr_ix[rng.permutation(len(tr_ix))]
        for b in range(0, len(perm), 256):
            bix = torch.from_numpy(perm[b:b + 256]).to(DEV)
            loss = ranknet_loss(model(bix), tRows[bix], tY[bix])
            if not loss.requires_grad:
                continue
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()
        model.eval()
        v = 0.0
        with torch.no_grad():
            for b in range(0, len(va_ix), 1024):
                bix = torch.from_numpy(va_ix[b:b + 1024]).to(DEV)
                v += float(ranknet_loss(model(bix), tRows[bix], tY[bix]))
        v /= max(len(va_ix) // 1024, 1)
        curve.append(v)
        if v < best - 1e-4:
            best, waited = v, 0
            state = {k: x.clone() for k, x in model.state_dict().items()}
        else:
            waited += 1
            if waited >= PATIENCE:
                break
    if state:
        model.load_state_dict(state)
    scores = np.empty(len(tRows), dtype=np.float32)
    model.eval()
    with torch.no_grad():
        for b in range(0, len(tRows), 8192):
            bix = torch.arange(b, min(b + 8192, len(tRows)), device=DEV)
            scores[b:b + 8192] = model(bix).cpu().numpy()
    print(f"trf[{name}]: best val {best:.4f} @ep{int(np.argmin(curve))} "
          f"empty_batches={empty_batches}", flush=True)
    return scores


def lgb_ranker(tr_ix):
    """Train on the given global row indices; score ALL rows."""
    f = FEATS_ALL
    rel = np.clip(np.round((Y_ALL + 2) * 2), 0, 12).astype(int)
    order = np.lexsort((np.arange(len(Y_ALL)), ROW_ALL))
    inv = np.empty(len(Y_ALL), np.int64)
    inv[order] = np.arange(len(Y_ALL))
    fs = f.iloc[order].reset_index(drop=True)
    rows_o, gs = ROW_ALL[order], []
    in_tr = np.isin(np.arange(len(rows_o)), inv[tr_ix])
    i = 0
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


def replay(cell, score_by_tag):
    out = {}
    for ai, t in enumerate(TAGS):
        d = DATA[t]
        panel = d["panel"].with_columns(pl.Series("s", score_by_tag[t]))
        table = fit_rule_table(panel.filter(pl.col("split") == "train"))
        fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
        picks = (panel.sort(["_cand", "s"]).group_by("_cand").last()
                 .with_columns(fmt.replace_strict([f"{r}|{s}" for (r, s) in table],
                     list(table.values()), default="x").alias("tr"))
                 .filter(pl.col("rule") == pl.col("tr")).sort("entry_idx"))
        sig = []
        for r in picks.filter(pl.col("split") == "test").iter_rows(named=True):
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
        out[t] = np.array([x["r_net"] for x in taken])
    return out


cells = {}
for ai, t in enumerate(TAGS):
    sub = np.where((SPLIT_ALL == "train") & (ASSET_ROW == ai))[0]
    cells["A", t] = lgb_ranker(sub)[ASSET_ROW == ai]
sc_b = lgb_ranker(np.where(SPLIT_ALL == "train")[0])
for ai, t in enumerate(TAGS):
    cells["B", t] = sc_b[ASSET_ROW == ai]

for ai, t in enumerate(TAGS):
    d = DATA[t]
    lo, hi = d["cand_off"], d["cand_off"] + len(d["cands"])
    in_asset = (ROW_ALL >= lo) & (ROW_ALL < hi)
    gW, gTab, gRows = tW, tTab, tRows
    tW, tTab, tRows = tW[lo:hi], tTab[in_asset], tRows[in_asset] - lo
    tr_ix = np.where(in_asset & (SPLIT_ALL == "train"))[0] - np.where(in_asset)[0][0]
    va_ix = np.where(in_asset & (SPLIT_ALL == "val"))[0] - np.where(in_asset)[0][0]
    sc = train_trf(tr_ix, va_ix, f"C:{t}")
    tW, tTab, tRows = gW, gTab, gRows
    full = np.zeros(len(Y_ALL), np.float32)
    full[in_asset] = sc
    cells["C", t] = full[ASSET_ROW == ai]

sc_d = train_trf(np.where(SPLIT_ALL == "train")[0],
                 np.where(SPLIT_ALL == "val")[0], "D:all")
for ai, t in enumerate(TAGS):
    cells["D", t] = sc_d[ASSET_ROW == ai]

print("\n=== 2x2 results (test pess, state machine) ===", flush=True)
pooled = {}
for cell in ["A", "B", "C", "D"]:
    allr = []
    for t in TAGS:
        r = replay(cell, {x: cells[cell, x] for x in TAGS})[t]
        allr.append(r)
        dd = trade_curve_stats(r)["max_dd_r"] if r.size else float("nan")
        ev = r.mean() if r.size else float("nan")
        print(f"{cell} {t:8s} pess={ev:+.3f} n={r.size} dd={dd:.1f}R")
    pooled[cell] = np.concatenate(allr)
    dd = trade_curve_stats(pooled[cell])["max_dd_r"]
    print(f"{cell} POOLED   pess={pooled[cell].mean():+.3f} "
          f"n={pooled[cell].size} dd={dd:.1f}R")

rng = np.random.default_rng(7)
for x, y in (("D", "B"), ("D", "C"), ("B", "A")):
    a, b = pooled[x], pooled[y]
    d = [a[rng.integers(0, a.size, a.size)].mean()
         - b[rng.integers(0, b.size, b.size)].mean() for _ in range(1000)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"{x} - {y} diff CI: [{lo:+.3f}, {hi:+.3f}]")


