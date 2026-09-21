"""MFE/MAE head -> adaptive take-profit, regime TP rule, RR gates.

1. LGBM regression predicts the favorable excursion (in R and ATR
   units) from ENTRY-TIME features only - "how far does this move
   usually run", not "will it hit +2R".
2. Adaptive TP: tp_r = clip(k * mfe_r_pred, rr_min, rr_max) with
   configurable RR gates (user spec: 1/5..1/3 scalp style up to 1..3).
3. Regime-conditioned TP rule (trend 3R / flat 1R) as the cheap
   non-ML baseline.
Trades = ranker + table gate picks.  Re-simulated on raw 1H bars
with the pessimistic cost model (SL-first, slip x2, gap 0.25 ATR).
"""

from __future__ import annotations

import sys

import lightgbm as lgb
import numpy as np
import polars as pl

from experiments import REPO


sys.path.insert(0, str(REPO))

from engine.model.ranker import (
    build_features,
    candidate_key,
    fit_rule_table,
)
from engine.sim.state_machine import run_state_machine


GEN_SLIP, COMM = 0.0005, 0.001
GAP, E_MULT, X_MULT = 0.25, 2.0, 2.0


def sim_trade(
    o, h, l, c, fill_idx, side, sl, tp, hold, gap_mult, atr=1.0
) -> tuple[float, float, int]:
    """Returns (r_opt, r_pess) with SL-first pessimism, generator costs."""
    sign = 1.0 if side == "long" else -1.0
    risk = abs(o[fill_idx] - sl)
    if risk <= 0:
        return np.nan, np.nan, -1
    fill = o[fill_idx]
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / risk
    pess_extra = E_MULT * GEN_SLIP * fill / risk
    last = min(len(c) - 1, fill_idx + max(hold - 1, 0))
    for held, j in enumerate(range(fill_idx, last + 1)):
        hit_sl = l[j] <= sl if sign > 0 else h[j] >= sl
        hit_tp = h[j] >= tp if sign > 0 else l[j] <= tp
        if hit_sl:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            return (r, r - pess_extra - (X_MULT - 1) * GEN_SLIP * abs(sl) / risk
                   - gap_mult * atr / risk, j)
        if hit_tp:
            r = sign * (tp - fill) / risk - cost_r
            return r, r - pess_extra, j
        if hold > 0 and held >= hold:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            return (r, r - pess_extra - (X_MULT - 1) * GEN_SLIP * abs(px) / risk, j)
    return np.nan, np.nan, -1  # unreachable (loop always ends with time exit)


from engine.features.mtf import resample_ohlcv
from engine.metrics.trade import trade_curve_stats


raw = resample_ohlcv(
    pl.read_parquet(REPO / "data/okx/raw_BTC-USDT_1m.parquet"), "1h"
)
print("raw 1h bars from 15m:", raw.height)
o, h, l, c = (raw[k].to_numpy() for k in ("open", "high", "low", "close"))

stop = candidate_key(
    pl.read_parquet(REPO / "data/mtf_dataset/BTCUSDT_1h.parquet").filter(
        (pl.col("execution") == "market")
        & (pl.col("target") == 2.0)
        & pl.col("r_net").is_not_nan()
        & (pl.col("exit_idx") >= 0)
        & pl.col("mfe_r").is_not_nan()
    )
).sort("_cand")

feats = build_features(stop, ("rule",))
tr = (stop["split"] == "train").to_numpy()
reg = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=15,
                        min_child_samples=40, random_state=7, verbosity=-1)
reg.fit(feats[tr], stop["mfe_r"].to_numpy()[tr])
stop = stop.with_columns(pl.Series("mfe_pred", reg.predict(feats)))
_v = stop.filter(pl.col("split") == "val")
print("mfe head: val rmse=", float(np.sqrt(np.mean(
    (_v["mfe_pred"].to_numpy() - _v["mfe_r"].to_numpy()) ** 2))))

table = fit_rule_table(stop.filter(pl.col("split") == "train"))
fmt = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))


# --- ranker for trade selection (same recipe, pess labels) ---
def _pess(row: dict) -> float:
    risk, fill = row["risk_unit"], row["fill_price"]
    d = E_MULT * GEN_SLIP * fill / risk
    if row["exit_reason"] == "sl":
        d += (X_MULT - 1) * GEN_SLIP * abs(row["sl_price"]) / risk
        d += GAP * row["atr_i"] / risk
    elif row["exit_reason"] == "time":
        d += (X_MULT - 1) * GEN_SLIP * abs(row["exit_price"]) / risk
    return row["r_net"] - d


stop = (
    stop.with_columns(pl.struct(pl.exclude("_cand")).map_elements(
        _pess, return_dtype=pl.Float64).alias("r_pess"))
    .with_columns(
        (pl.col("risk_unit") / pl.col("fill_price")).alias("risk_pct"),
        (0.0025 * pl.col("fill_price") / pl.col("risk_unit")).alias("cost_R"),
    )
)
feats["risk_pct"] = stop["risk_pct"].to_numpy()
feats["cost_R"] = stop["cost_R"].to_numpy()
split_row = stop["split"].to_numpy()
trm = split_row == "train"
sizes = stop.group_by("_cand").len().sort("_cand")["len"].to_numpy()
csp = (stop.group_by("_cand").agg(pl.col("split").first()).sort("_cand")
       ["split"].to_numpy())
rel = np.clip(np.round((stop["r_pess"].to_numpy() + 2.0) * 2.0), 0, 12).astype(int)
ranker = lgb.LGBMRanker(objective="lambdarank", n_estimators=300,
                        learning_rate=0.05, num_leaves=15, min_child_samples=30,
                        label_gain=list(range(13)), random_state=7, verbosity=-1)
ranker.fit(feats[trm], rel[trm], group=sizes[csp == "train"], callbacks=[])
stop = stop.with_columns(pl.Series("rank_score", ranker.predict(feats)))
picks = (
    stop.sort(["_cand", "rank_score"]).group_by("_cand").last()
    .with_columns(fmt.replace_strict(
        [f"{r}|{s}" for (r, s) in table], list(table.values()), default="x"
    ).alias("tbl_rule"))
    .filter(pl.col("rule") == pl.col("tbl_rule"))
    .sort("entry_idx")
)
print("picks:", picks.height, " trend vals:", stop["h1_trend"].unique().to_list())
_s = picks.filter(pl.col("split") == "val").head(50)
_d = []
for r in _s.iter_rows(named=True):
    i0 = int(r["entry_idx"]) + 1
    if i0 >= raw.height or r["sl_price"] == r["fill_price"]:
        continue
    ro, _, _ = sim_trade(o, h, l, c, i0, r["side"], r["sl_price"],
                         r["fill_price"] + (1 if r["side"] == "long" else -1)
                         * 2.0 * r["risk_unit"], 48, 0.0)
    _d.append(ro - r["r_net"])
print("sanity vs stored r_net: n=", len(_d), " mean abs diff=",
      float(np.nanmean(np.abs(_d))))

META = ["entry_idx", "side", "risk_unit", "fill_price", "sl_price", "split",
        "h1_trend", "mfe_pred"]


def eval_tp(name: str, tp_rule, k: float = 0.0) -> None:
    for s in ("val", "test"):
        sub = picks.filter(pl.col("split") == s)
        signals = []
        for r in sub.iter_rows(named=True):
            i0 = int(r["entry_idx"]) + 1
            if i0 >= len(c):
                continue
            sign = 1.0 if r["side"] == "long" else -1.0
            fill, risk = r["fill_price"], r["risk_unit"]
            tp_r = tp_rule(r) * k if k else tp_rule(r)
            tp_r = float(np.clip(tp_r, RR[0], RR[1]))
            tp = fill + sign * tp_r * risk
            ro, rp, jx = sim_trade(o, h, l, c, i0, r["side"], r["sl_price"], tp,
                                   48, GAP, r["atr_i"])
            if not np.isfinite(ro):
                continue
            signals.append({"cand": r["_cand"], "decision_idx": int(r["entry_idx"]),
                            "side": r["side"], "priority": 0.0,
                            "r_net": float(rp), "r_opt": float(ro), "exit_idx": jx})
        taken, _ = run_state_machine(signals)
        ro = np.array([t.get("r_opt", t["r_net"]) for t in taken])
        rp = np.array([t["r_net"] for t in taken])
        if s == "test" and (name.startswith("fixed")
                            or ("rr=0.33-1.00" in name and k == 0.8)):
            BOOT[name] = rp
        dd = trade_curve_stats(rp)["max_dd_r"]
        print(f"{name:22s} {s:5s} opt={ro.mean():+.3f} pess={rp.mean():+.3f} "
              f"ratio={rp.mean() / ro.mean() if ro.mean() else 0:.2f} "
              f"n={rp.size} dd={dd:.1f}R")


BOOT: dict[str, np.ndarray] = {}
for RR in [(0.05, 10.0)]:
    eval_tp("fixed 2R (baseline)", lambda r: 2.0)
    eval_tp("regime 3R/1R", lambda r: 3.0 if r["h1_trend"] * (1 if r["side"] == "long" else -1) == 1 else 1.0)
    for RR in [(0.2, 1 / 3), (1 / 3, 1.0), (1.0, 3.0)]:
        for k in (0.4, 0.6, 0.8):
            eval_tp(f"adaptive k={k} rr={RR[0]:.2f}-{RR[1]:.2f}",
                    lambda r: r["mfe_pred"], k)


print("bootstrap 95% CI on pess EV (1000 resamples, test):")
rng = np.random.default_rng(7)
keys = [k for k in BOOT if True]
for name, r in BOOT.items():
    m = [r[rng.integers(0, r.size, r.size)].mean() for _ in range(1000)]
    lo, hi = np.percentile(m, [2.5, 97.5])
    print(f"{name:22s} EV={r.mean():+.3f} CI=[{lo:+.3f},{hi:+.3f}] n={r.size}")
fa, fb = BOOT.get("fixed 2R (baseline)"), None
for k2, v2 in BOOT.items():
    if k2 != "fixed 2R (baseline)":
        fb = v2
if fa is not None and fb is not None:
    d = [fa[rng.integers(0, fa.size, fa.size)].mean()
         - fb[rng.integers(0, fb.size, fb.size)].mean() for _ in range(1000)]
    print("fixed - adaptive diff CI:", np.percentile(d, [2.5, 97.5]).round(3))
