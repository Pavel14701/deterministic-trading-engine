"""ProSP v2: tail-event probabilities with flow features.

Prereg STATUS 2026-09-21 (+ run declaration 4c8b390): 29-asset
Binance 1H panel; labels label_up/dn = close(t+24)/close(t)-1
beyond +-2% (future bars only); 8 frozen features; LGBM
(n=400, lr=0.05, leaves=15, mcs=40, seed=7), two tasks (up,
dn), pooled across assets; isotonic calibration on the 56d
window before the 7d embargo; WF 8x56d expanding (repo
protocol); predictions only on TEST bars.  Portfolio: daily,
long top-3 / short bottom-3 by calibrated P(up)-P(dn), 0.15%
per leg membership change.  Gates on pooled TEST: P-G1 kill
(calibrated Brier < TEST class-rate baseline, per-fold
improvement > 0 on >= 5/8), P-G2 tercile net EV > 0, P-G3
portfolio net Sharpe_NW >= 1.0.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.isotonic import IsotonicRegression

from engine.backtest.protocol import wf_folds
from engine.passed.avsl_cross_s1 import atr_ind, repo_root
from experiments.carry.funding_carry import UNIVERSE
from experiments.loaders.load_binance import SYMBOL_ALIASES

REPO = repo_root()
CACHE = REPO / "data" / "binance"
MS_H = 3_600_000
MS_D = 86_400_000
Z_W = 336
DELTA = 24
RET_1, RET_2 = 24, 168
FUND_W = 3
FUND_Z_W = 90
HORIZON = 24
TH = 0.02
DAY = MS_D
CAL_DAYS = 56
EMBARGO_D = 7
COST = 0.0015
N_LEG = 3
LGB = dict(n_estimators=400, learning_rate=0.05, num_leaves=15,
           min_child_samples=40, random_state=7, verbosity=-1)


def _rollz(x: pl.Expr, w: int) -> pl.Expr:
    return (x - x.rolling_mean(w)) / x.rolling_std(w, ddof=1)


def load_asset(sym: str, funding: pl.DataFrame) -> dict | None:
    df = pl.read_parquet(CACHE / f"kl_{sym}_1h.parquet")
    ts = df["ts"].to_numpy().astype(np.int64)
    hp = df["high"].to_numpy()
    lp = df["low"].to_numpy()
    cp = df["close"].to_numpy()
    vol = df["volume"].to_numpy()
    tbv = df["taker_buy_volume"].to_numpy()
    share = np.where(vol > 0, tbv / np.where(vol > 0, vol, 1.0), np.nan)
    atr = np.asarray(atr_ind(hp, lp, cp, 24, use_talib=False), float)

    f = pl.DataFrame({
        "ts": ts, "share": share, "cp": cp, "vol": vol,
        "rng": (hp - lp) / cp, "atr": atr,
        "day": ts // MS_D,
    })
    # daily funding (next-day mapping, no lookahead)
    fd = funding.select(
        (pl.col("ts") // MS_D).alias("day"),
        pl.col("rate"),
    ).group_by("day").agg(pl.col("rate").sum().alias("f"))
    fd = fd.sort("day").with_columns([
        pl.col("f").rolling_mean(FUND_W).alias("f3"),
    ]).with_columns(
        ((pl.col("f3") - pl.col("f3").rolling_mean(FUND_Z_W))
         / pl.col("f3").rolling_std(FUND_Z_W, ddof=1)).alias("fz")
    ).select(
        (pl.col("day") + 1).alias("day"),  # next-day mapping
        "fz",
    )
    f = f.join(fd, on="day", how="left")
    f = f.with_columns([
        _rollz(pl.col("share"), Z_W).alias("f_share_z"),
        (pl.col("share") - pl.col("share").shift(DELTA)).alias("f_share_d"),
        _rollz(pl.col("atr"), Z_W).alias("f_atr_z"),
        _rollz(pl.col("vol"), Z_W).alias("f_vol_z"),
        _rollz(pl.col("rng"), Z_W).alias("f_rng_z"),
        (pl.col("cp") / pl.col("cp").shift(RET_1) - 1).alias("f_ret24"),
        (pl.col("cp") / pl.col("cp").shift(RET_2) - 1).alias("f_ret168"),
    ])
    feats = f.select(
        "f_share_z", "f_share_d", "fz", "f_ret24", "f_ret168",
        "f_atr_z", "f_vol_z", "f_rng_z",
    ).to_numpy()
    fut = np.full(len(cp), np.nan)
    fut[:-HORIZON] = cp[HORIZON:] / cp[:-HORIZON] - 1.0
    lab_up = np.where(np.isfinite(fut), (fut > TH).astype(float), np.nan)
    lab_dn = np.where(np.isfinite(fut), (fut < -TH).astype(float), np.nan)
    return {"ts": ts, "cp": cp, "feats": feats, "up": lab_up, "dn": lab_dn}


def load_funding() -> pl.DataFrame:
    frames = []
    for u in UNIVERSE:
        sym = SYMBOL_ALIASES.get(u, u.replace("-", ""))
        p = REPO / "data" / "funding_binance" / f"fbnb_{sym}.parquet"
        if p.exists():
            frames.append(pl.read_parquet(p))
    return pl.concat(frames)


FEATS = ["f_share_z", "f_share_d", "fz", "f_ret24", "f_ret168",
         "f_atr_z", "f_vol_z", "f_rng_z"]


def main() -> None:
    import lightgbm as lgb

    funding = load_funding()
    data = {}
    for u in UNIVERSE:
        sym = SYMBOL_ALIASES.get(u, u.replace("-", ""))
        if (CACHE / f"kl_{sym}_1h.parquet").exists():
            data[sym] = load_asset(sym, funding)
    data = {k: v for k, v in data.items() if v is not None}
    print(f"universe: {len(data)} assets", flush=True)

    t0 = min(int(d["ts"][0]) for d in data.values())
    t1 = max(int(d["ts"][-1]) for d in data.values())
    folds = wf_folds(t0, t1, 8, 56)
    day_last: dict[tuple[str, int], int] = {}
    for sym, d in data.items():
        last: dict[int, int] = {}
        for i, dd in enumerate(d["ts"] // MS_D):
            last[int(dd)] = i
        for k2, v in last.items():
            day_last[(sym, k2)] = v
    all_days = sorted({k for _s, k in day_last})
    day_idx = {dd: k for k, dd in enumerate(all_days)}

    brier_mod = {"up": [], "dn": []}
    brier_base = {"up": [], "dn": []}
    fold_ok = {"up": 0, "dn": 0}
    pred: dict[tuple[int, str], float] = {}

    for k, (fs, fe) in enumerate(folds):
        cal_hi = fs - EMBARGO_D * DAY
        cal_lo = cal_hi - CAL_DAYS * DAY
        for task in ("up", "dn"):
            labkey = task
            Xtr, ytr, Xcal, ycal, Xte, yte, meta = (
                [] for _ in range(7))
            for sym, d in data.items():
                ts, lab = d["ts"], d[labkey]
                okrow = np.isfinite(d["feats"]).all(axis=1)
                m_tr = (ts < cal_lo) & np.isfinite(lab) & okrow
                m_cal = ((ts >= cal_lo) & (ts < cal_hi)
                         & np.isfinite(lab) & okrow)
                m_te = (ts >= fs) & (ts < fe) & np.isfinite(lab) & okrow
                if m_tr.sum() < 200 or m_cal.sum() < 50:
                    continue
                fm = d["feats"]
                Xtr.append(fm[m_tr]); ytr.append(lab[m_tr])
                Xcal.append(fm[m_cal]); ycal.append(lab[m_cal])
                Xte.append(fm[m_te]); yte.append(lab[m_te])
                meta.append((sym, d, np.where(m_te)[0]))
            if not Xtr:
                continue
            Xtr, ytr = np.vstack(Xtr), np.concatenate(ytr)
            Xcal, ycal = np.vstack(Xcal), np.concatenate(ycal)
            Xte, yte = np.vstack(Xte), np.concatenate(yte)
            if len(ytr) < 20000 or len(ycal) < 500:
                print(f"fold {k} {task}: SKIPPED pooled tr={len(ytr)} "
                      f"cal={len(ycal)}", flush=True)
                continue
            m = lgb.LGBMClassifier(**LGB)
            m.fit(Xtr, ytr)
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(m.predict_proba(Xcal)[:, 1], ycal)
            p = iso.predict(m.predict_proba(Xte)[:, 1])
            brier_mod[task].append(float(np.mean((p - yte) ** 2)))
            base = float(np.mean(yte))
            brier_base[task].append(float(np.mean((base - yte) ** 2)))
            if brier_base[task][-1] > brier_mod[task][-1]:
                fold_ok[task] += 1
            r0 = 0
            for sym, d, ii in meta:
                lastbar: dict[int, int] = {}
                for i in ii:
                    lastbar[int(d["ts"][i] // MS_D)] = i
                for dd, i in lastbar.items():
                    pred[(day_idx[dd], sym)] = float(
                        p[r0 + int(np.searchsorted(ii, i))])
            print(f"fold {k} {task}: tr={len(ytr)} te={len(yte)} brier "
                  f"{brier_mod[task][-1]:.5f} vs {brier_base[task][-1]:.5f}",
                  flush=True)

    # ---- portfolio: daily top-3 / bottom-3 ------------------------- #
    ret_map: dict[tuple[int, str], float] = {}
    for sym, d in data.items():
        lastc: dict[int, float] = {}
        for i, dd in enumerate(d["ts"] // MS_D):
            lastc[int(dd)] = d["cp"][i]
        dts = np.array(sorted(lastc))
        cl = np.array([lastc[x] for x in dts])
        r = np.full(len(dts), np.nan)
        r[1:] = cl[1:] / cl[:-1] - 1.0
        for k2, dd in enumerate(dts):
            ret_map[(day_idx[dd], sym)] = r[k2]

    pvals: list[float] = []
    tvals: list[float] = []
    prev_legs: frozenset = frozenset()
    prev_tc: frozenset | None = None
    for di in range(len(all_days) - 1):
        scored = [(pred[(di, s)], s) for s in data
                  if (di, s) in pred
                  and np.isfinite(ret_map.get((di + 1, s), np.nan))]
        if len(scored) < 2 * N_LEG:
            continue
        scored.sort()
        legs = {s: -1.0 for _p, s in scored[:N_LEG]}
        legs |= {s: 1.0 for _p, s in scored[-N_LEG:]}
        r = float(np.mean([sg * ret_map[(di + 1, s)]
                           for s, sg in legs.items()]))
        c = COST * len(set(legs) ^ prev_legs) if prev_legs else 0.0
        pvals.append(r - c)
        prev_legs = frozenset(legs)
        qs = np.quantile([p for p, _s in scored], [1 / 3, 2 / 3])
        tlong = [s for p, s in scored if p >= qs[1]]
        tshort = [s for p, s in scored if p <= qs[0]]
        tc = frozenset(tlong) | frozenset(tshort)
        tcost = COST * len(tc ^ prev_tc) if prev_tc is not None else 0.0
        tvals.append(
            float(np.mean([ret_map[(di + 1, s)] for s in tlong]
                          + [-ret_map[(di + 1, s)] for s in tshort]))
            - tcost
        )
        prev_tc = tc

    from engine.passed.avsl_cross_s1 import nw_sharpe

    pn, tn = np.array(pvals), np.array(tvals)
    sh = nw_sharpe(pn, lags=5, ann=365)
    bm = float(np.mean([np.mean(v) for v in brier_mod.values()]))
    bb = float(np.mean([np.mean(v) for v in brier_base.values()]))
    fo = min(fold_ok.values())
    pg1 = bm < bb and fo >= 5
    pg2 = bool(np.nanmean(tn) > 0)
    pg3 = bool(np.isfinite(sh) and sh >= 1.0)
    print(f"\n=== gates (pooled TEST, {len(pn)} days with legs) ===")
    print(f"P-G1 brier: model {bm:.5f} vs base {bb:.5f}, fold-wins "
          f"up={fold_ok['up']}/8 dn={fold_ok['dn']}/8 (min {fo}) -> "
          f"{'PASS' if pg1 else 'FAIL'}")
    print(f"P-G2 tercile net daily EV: {float(np.nanmean(tn)) * 1e4:+.2f}bp "
          f"-> {'PASS' if pg2 else 'FAIL'}")
    print(f"P-G3 portfolio net Sharpe_NW: {sh:+.2f} -> "
          f"{'PASS' if pg3 else 'FAIL'}")
    print("ProSP v2:", "PASS" if (pg1 and pg2 and pg3) else
          "CLOSED (gate failed, no re-tuning)")


if __name__ == "__main__":
    main()


