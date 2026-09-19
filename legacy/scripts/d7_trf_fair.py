"""D.7: FAIR transformer fight - same info, label, protocol, costs.

Equalizers vs the champion LGBM ranker (D.4):
- input: 64-bar window (9 raw channels, builder normalization) PLUS the
  exact LGBM feature row (33 + rule + risk_pct + cost_R) broadcast over
  every bar -> the model sees everything LGBM sees, plus sequence;
- label: same pess R (D.3 gap model), pairwise RankNet loss over
  candidate groups (LambdaRank protocol);
- selection: same table gate, same unified d6 simulator for replay;
- metrics: pairwise AUROC on val (crit > 0.55), pess EV bootstrap diff
  CI vs LGBM (crit: excludes 0), attention entropy (crit < 0.917 of
  max, i.e. 5.5/6.0 bits equivalent).
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.src.mtf import resample_ohlcv  # noqa: E402
from ai.src.mtf_model import (  # noqa: E402
    apply_rule_table,
    build_features,
    candidate_key,
    fit_rule_table,
    trade_curve_stats,
)
from ai.src.state_machine import run_state_machine
from scripts.d6_joint_rank import sim, pess  # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
WIN = 64

# ---------------------------------------------------------------- data
raw = resample_ohlcv(
    pl.read_parquet(REPO / "data/okx/raw_BTC-USDT_1m.parquet"), "1h"
)
o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))
n = len(raw)

stop = candidate_key(
    pl.read_parquet(REPO / "data/mtf_dataset/BTCUSDT_1h.parquet").filter(
        (pl.col("execution") == "market")
        & (pl.col("target") == 2.0)
        & pl.col("r_net").is_not_nan()
        & (pl.col("exit_idx") >= 0)
        & pl.col("risk_unit").is_not_nan()
    )
).sort("_cand")
stop = stop.with_columns(
    pl.struct(pl.exclude("_cand"))
    .map_elements(pess, return_dtype=pl.Float64)
    .alias("r_pess")
)
feats = build_features(stop, ("rule",))
feats["risk_pct"] = (stop["risk_unit"] / stop["fill_price"]).to_numpy().astype(np.float32)
feats["cost_R"] = (0.0025 * stop["fill_price"] / stop["risk_unit"]).to_numpy().astype(np.float32)
TAB = feats.shape[1]
feats_num = feats.copy()
for col in feats_num.columns:
    if str(feats_num[col].dtype) == "category":
        feats_num[col] = feats_num[col].cat.codes.astype(np.float32)
feats_num = feats_num.astype(np.float32)

cands = stop["_cand"].unique(maintain_order=True).to_list()
row_cand = stop["_cand"].replace_strict(cands, list(range(len(cands)))).to_numpy()
sizes = stop.group_by("_cand").len().sort("_cand")["len"].to_numpy()
split_row = stop["split"].to_numpy()
y = stop["r_pess"].to_numpy().astype(np.float32)

# raw windows per candidate (builder normalization)
vol1h = np.log1p(raw["volume"].to_numpy())
vmed = np.full(n, 1.0)
for i in range(n):
    seg = vol1h[max(0, i - 500): i + 1]
    m = np.median(seg[np.isfinite(seg)])
    if m and m > 0:
        vmed[i] = m
W = np.zeros((len(cands), WIN, 9), dtype=np.float32)
ei = stop.group_by("_cand").agg(pl.col("entry_idx").first()).sort("_cand")["entry_idx"].to_numpy()
sd = stop.group_by("_cand").agg(pl.col("side").first()).sort("_cand")["side"].to_numpy()
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

tW = torch.from_numpy(W).to(DEV)                     # (C, WIN, 9)
tTab = torch.from_numpy(np.nan_to_num(feats_num.to_numpy(), nan=0.0, posinf=0.0, neginf=0.0)).to(DEV)               # (R, TAB)
tRowCand = torch.from_numpy(row_cand).to(DEV)        # (R,)


# --------------------------------------------------------------- model
class FairTrf(nn.Module):
    def __init__(self, d=64, layers=2, heads=4):
        super().__init__()
        self.proj = nn.Linear(9 + TAB, d)
        self.pos = nn.Parameter(torch.zeros(1, WIN, d))
        layer = nn.TransformerEncoderLayer(
            d, heads, d * 4, dropout=0.1, activation="gelu", batch_first=True
        )
        self.enc = nn.TransformerEncoder(layer, layers)
        self.head = nn.Linear(2 * d, 1)  # mean + last pooling

    def forward(self, xw, xtab, rows):
        tab = tTab[rows].unsqueeze(1).expand(-1, WIN, -1)
        z = self.proj(torch.cat([xw, tab], -1)) + self.pos
        z = self.enc(z)
        pooled = torch.cat([z.mean(1), z[:, -1]], -1)
        return self.head(pooled).squeeze(-1)


def ranknet_loss(scores, rows, ys):
    loss, n_pair = 0.0, 0
    for g in rows.unique():
        m = rows == g
        si, yi = scores[m], ys[m]
        if si.numel() < 2:
            continue
        diff = si.unsqueeze(1) - si.unsqueeze(0)
        yd = torch.sign(yi.unsqueeze(1) - yi.unsqueeze(0))
        mask = yd != 0
        loss = loss + nn.functional.softplus(-diff[mask] * yd[mask]).sum()
        n_pair += int(mask.sum())
    return loss / max(n_pair, 1)


te = torch.from_numpy(split_row == "test").to(DEV)
va = torch.from_numpy(split_row == "val").to(DEV)
tY = torch.from_numpy(y).to(DEV)

model = FairTrf().to(DEV)
opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
WARM, EPOCHS, PATIENCE = 2, 50, 5
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda ep: min(
    (ep + 1) / WARM,
    0.5 * (1 + np.cos(np.pi * max(0, ep - WARM) / max(EPOCHS - WARM, 1))),
))
rng0 = np.random.default_rng(7)
tr_ix = np.where(split_row == "train")[0]
va_ix = np.where(split_row == "val")[0]
te_ix = np.where(split_row == "test")[0]

def group_loss(ix):
    tot, nb = 0.0, 0
    with torch.no_grad():
        for b in range(0, len(ix), 1024):
            bix = torch.from_numpy(ix[b:b + 1024]).to(DEV)
            tot += float(ranknet_loss(
                model(tW[tRowCand[bix]], tTab, bix), tRowCand[bix], tY[bix]))
            nb += 1
    return tot / max(nb, 1)

print(f"device={DEV} rows={len(tr_ix)} tab={TAB}", flush=True)
curve, best, waited, best_state = [], np.inf, 0, None
for ep in range(EPOCHS):
    model.train()
    perm = tr_ix[rng0.permutation(len(tr_ix))]
    tot = 0.0
    for b in range(0, len(perm), 256):
        bix = torch.from_numpy(perm[b:b + 256]).to(DEV)
        loss = ranknet_loss(
            model(tW[tRowCand[bix]], tTab, bix), tRowCand[bix], tY[bix]
        )
        opt.zero_grad(); loss.backward(); opt.step()
        tot += float(loss)
    sched.step()
    model.eval()
    vloss = group_loss(va_ix)
    curve.append({"epoch": ep, "train_loss": tot, "val_loss": vloss})
    print(f"epoch {ep}: train={tot:.1f} val={vloss:.4f}", flush=True)
    if vloss < best - 1e-4:
        best, waited, best_state = vloss, 0, {
            k: v.clone() for k, v in model.state_dict().items()}
    else:
        waited += 1
        if waited >= PATIENCE:
            print(f"early stop at epoch {ep} (best val {best:.4f})", flush=True)
            break
if best_state is not None:
    model.load_state_dict(best_state)
import json
runs = REPO / "runs/d7"; runs.mkdir(parents=True, exist_ok=True)
(runs / "loss_curve.json").write_text(json.dumps(curve, indent=2),
                                      encoding="utf-8")
model.eval()
trf_scores = np.empty(len(stop), dtype=np.float32)
with torch.no_grad():
    for b in range(0, len(stop), 4096):
        bix = torch.arange(b, min(b + 4096, len(stop)), device=DEV)
        trf_scores[b:b + 4096] = model(tW[tRowCand[bix]], tTab, bix).cpu().numpy()


# ------------------------------------------------------- diagnostics
def pw_auroc(mask):
    ix = np.where(mask)[0]
    rng = np.random.default_rng(3)
    a = rng.choice(ix, 20000)
    b = rng.choice(ix, 20000)
    m = y[a] > y[b]
    return float((trf_scores[a][m] > trf_scores[b][m]).mean())


print(f"val pairwise AUROC = {pw_auroc(va.cpu().numpy()):.3f} (crit > 0.55)")

# attention entropy: patch last layer self-attn to return weights,
# normalized by max entropy log(WIN) (1.0 = perfectly flat attention)
attn_stats = []
layer_last = model.enc.layers[-1]
orig_attn = layer_last.self_attn.forward
def attn_forward(*a, **kw):
    kw["need_weights"] = True
    out, w = orig_attn(*a, **kw)
    p = w / w.sum(-1, keepdims=True)
    ent = -(p * (p + 1e-9).log()).sum(-1)
    attn_stats.append(float(ent.mean()) / np.log(WIN))
    return out, None
layer_last.self_attn.forward = attn_forward
with torch.no_grad():
    model(tW[tRowCand[te_ix[:512]]], tTab, te_ix[:512])
print(f"attention entropy (norm, 1.0=flat) = {np.mean(attn_stats):.3f} "
      f"(crit < 0.917 ~ 5.5/6.0 bits)")


# --------------------------------------- LGBM baseline + replay + CI
table = fit_rule_table(stop.filter(pl.col("split") == "train"))
fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
trm = split_row == "train"
csp = (
    stop.group_by("_cand").agg(pl.col("split").first()).sort("_cand")
    ["split"].to_numpy()
)
lgbm = lgb.LGBMRanker(objective="lambdarank", n_estimators=300,
                      learning_rate=0.05, num_leaves=15, min_child_samples=30,
                      label_gain=list(range(13)), random_state=7, verbosity=-1)
lgbm.fit(feats[trm], np.clip(np.round((y[trm] + 2) * 2), 0, 12).astype(int),
         group=sizes[csp == "train"], callbacks=[])
stop = stop.with_columns(
    pl.Series("trf_s", trf_scores), pl.Series("lgb_s", lgbm.predict(feats))
)


def replay(score):
    picks = (stop.sort(["_cand", score]).group_by("_cand").last()
             .with_columns(fmt.replace_strict([f"{r}|{s}" for (r, s) in table],
                 list(table.values()), default="x").alias("tr"))
             .filter(pl.col("rule") == pl.col("tr")).sort("entry_idx"))
    res = {}
    for s in ("val", "test"):
        sig = []
        for r in picks.filter(pl.col("split") == s).iter_rows(named=True):
            i0 = int(r["entry_idx"]) + 1
            if i0 >= n:
                continue
            ro, rp, jx = sim(o, h, l, c, i0, r["side"], r["sl_price"],
                             r["tp_price"], 48, r["atr_i"])
            if not np.isfinite(ro):
                continue
            sig.append({"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
                        "side": r["side"], "priority": 0.0,
                        "r_net": float(rp), "r_opt": float(ro), "exit_idx": jx})
        taken, _ = run_state_machine(sig)
        rp = np.array([t["r_net"] for t in taken])
        ro = np.array([t["r_opt"] for t in taken])
        res[s] = (ro, rp)
        dd = trade_curve_stats(rp)["max_dd_r"]
        print(f"{score:6s} {s:5s} opt={ro.mean():+.3f} pess={rp.mean():+.3f} "
              f"ratio={rp.mean()/ro.mean():.2f} n={rp.size} dd={dd:.1f}R")
    return res


r_l = replay("lgb_s")
r_t = replay("trf_s")
rng = np.random.default_rng(7)
a, b = r_l["test"][1], r_t["test"][1]
d = [a[rng.integers(0, a.size, a.size)].mean()
     - b[rng.integers(0, b.size, b.size)].mean() for _ in range(1000)]
lo, hi = np.percentile(d, [2.5, 97.5])
print(f"bootstrap LGBM - TRF diff CI: [{lo:+.3f}, {hi:+.3f}] "
      f"(TRF alive iff excludes 0 with TRF better)")


