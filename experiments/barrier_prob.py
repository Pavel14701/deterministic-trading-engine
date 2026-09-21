# -*- coding: utf-8 -*-
"""Barrier-probability model: P(hit TP before SL), first-passage frame.

PRE-REGISTERED single-shot test (STATUS.md, BARRIER-PROBABILITY MODEL
-- PRE-REGISTRATION).  Label = TP-first before SL within 48 bars
(SL-first pessimism; timeout = 0), LightGBM binary per side x config,
isotonic calibration, walk-forward 8x56d, EV>0 trading rule, P&L from
the pessimistic simulator.  Gates K1-K3 fixed before the run.
"""
from __future__ import annotations

import sys

from pathlib import Path

import lightgbm as lgb
import numpy as np

from numpy.lib.stride_tricks import sliding_window_view


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import wf_folds
from experiments.avsl_baseline import DAY
from experiments.avsl_trailing import REPO, _read_okx
from experiments.donchian_breakout import _roll
from ta.src.volatility.atr import atr_ind


ASSETS = ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB")
CONFIGS = ((1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (3.0, 1.0), (4.0, 1.5))
HORIZON = 48
COMM, GEN_SLIP, GAP = 0.001, 0.0005, 0.25
CAL_DAYS = 56
FEATS = ("atr_pct", "atr_pctr", "bbw", "bbw_pctr", "ret1", "ret4",
         "ret12", "ret48", "d_dc20u", "d_dc20l", "d_dc55u", "d_dc55l",
         "d_sma200")


def _features(o, h, l, c, atr):
    """Causal entry-time features (dict of arrays, NaN-safe)."""
    n = len(c)
    atr_pct = atr / c
    atr_pctr = np.full(n, np.nan)
    for i in range(500, n):
        w = atr_pct[i - 500:i]
        atr_pctr[i] = (w < atr_pct[i]).mean() if np.isfinite(atr_pct[i]) else np.nan
    sd = _roll(c, 20, np.std)
    bbw = 4.0 * sd / c
    bbw_pctr = np.full(n, np.nan)
    for i in range(500, n):
        w = bbw[i - 500:i]
        bbw_pctr[i] = (w < bbw[i]).mean() if np.isfinite(bbw[i]) else np.nan
    dc20u = np.concatenate(([np.nan], _roll(h, 20, np.max)[:-1]))
    dc20l = np.concatenate(([np.nan], _roll(l, 20, np.min)[:-1]))
    dc55u = np.concatenate(([np.nan], _roll(h, 55, np.max)[:-1]))
    dc55l = np.concatenate(([np.nan], _roll(l, 55, np.min)[:-1]))
    sma200 = _roll(c, 200, np.mean)

    def ret(k: int) -> np.ndarray:
        return np.concatenate((np.full(k, np.nan), c[k:] / c[:-k] - 1))

    with np.errstate(invalid="ignore", divide="ignore"):
        return {
            "atr_pct": atr_pct, "atr_pctr": atr_pctr, "bbw": bbw,
            "bbw_pctr": bbw_pctr, "ret1": ret(1), "ret4": ret(4),
            "ret12": ret(12), "ret48": ret(48),
            "d_dc20u": (c - dc20u) / atr, "d_dc20l": (c - dc20l) / atr,
            "d_dc55u": (c - dc55u) / atr, "d_dc55l": (c - dc55l) / atr,
            "d_sma200": (c - sma200) / atr,
        }


def _barrier_labels(o, h, l, atr, tp_r, sl_r):
    """For every signal bar i (entry open[i+1]) both sides at once.

    Returns (lab_L, lab_S) arrays: 1 = TP touched before SL within
    HORIZON bars, SL-first on same-bar touches, timeout = 0.
    """
    n = len(o)
    m = n - 1 - HORIZON  # last usable signal bar
    lab_L = np.full(n, np.nan)
    lab_S = np.full(n, np.nan)
    if m < 1:
        return lab_L, lab_S
    idx = np.arange(1, m + 1)          # entry bar indices (fill = open[idx])
    fill = o[idx]
    a = atr[idx - 1]                   # ATR of the signal bar
    ok = np.isfinite(a) & (a > 0)
    idx, fill, a = idx[ok], fill[ok], a[ok]
    hw = sliding_window_view(h, HORIZON)[idx]
    lw = sliding_window_view(l, HORIZON)[idx]
    for side, sgn in (("L", 1.0), ("S", -1.0)):
        tp = fill + sgn * tp_r * a
        sl = fill - sgn * sl_r * a
        hit_tp = (hw >= tp[:, None]) if sgn > 0 else (lw <= tp[:, None])
        hit_sl = (lw <= sl[:, None]) if sgn > 0 else (hw >= sl[:, None])
        f_tp = np.where(hit_tp.any(1), hit_tp.argmax(1), HORIZON + 9)
        f_sl = np.where(hit_sl.any(1), hit_sl.argmax(1), HORIZON + 9)
        lab = np.where((f_tp < HORIZON + 9) & (f_tp < f_sl), 1.0, 0.0)
        lab_s = np.full(n, np.nan)
        lab_s[idx - 1] = lab
        if side == "L":
            lab_L = lab_s
        else:
            lab_S = lab_s
    return lab_L, lab_S


E_MULT, X_MULT = 2.0, 2.0


def sim_trade(o, h, l, c, fill_idx, side, sl, tp, hold, atr=1.0):
    """Pessimistic r (SL-first, slip, gap), mirrors adaptive_tp.sim_trade."""
    sign = 1.0 if side == "long" else -1.0
    fill = o[fill_idx]
    risk = abs(fill - sl)
    if risk <= 0:
        return np.nan
    cost_r = (2 * COMM * fill + GEN_SLIP * fill) / risk
    pess = E_MULT * GEN_SLIP * fill / risk
    last = min(len(c) - 1, fill_idx + hold - 1)
    for j in range(fill_idx, last + 1):
        hit_sl = l[j] <= sl if sign > 0 else h[j] >= sl
        hit_tp = h[j] >= tp if sign > 0 else l[j] <= tp
        if hit_sl:
            r = sign * (sl * (1 - sign * GEN_SLIP) - fill) / risk - cost_r
            return r - pess - (X_MULT - 1) * GEN_SLIP * abs(sl) / risk \
                - GAP * atr / risk
        if hit_tp:
            r = sign * (tp - fill) / risk - cost_r
            return r - pess
        if j == last:
            px = c[j] * (1 - sign * GEN_SLIP)
            r = sign * (px - fill) / risk - cost_r
            return r - pess - (X_MULT - 1) * GEN_SLIP * abs(px) / risk
    return np.nan


def run() -> None:
    """Barrier-probability pre-registered run (gates K1-K3)."""
    from sklearn.isotonic import IsotonicRegression

    print("BARRIER-PROBABILITY 1H: 6 majors, configs (tp_r,sl_r)="
          f"{CONFIGS}, horizon={HORIZON}, WF 8x56d + isotonic; "
          "gates K1-K3 per STATUS.md prereg; one shot.", flush=True)
    data = {}
    for sym in ASSETS:
        ts, o, l, h, c, _v = _read_okx(f"{sym}-USDT", "1H")
        atr = atr_ind(h, l, c, 14, use_talib=False)
        feats = _features(o, h, l, c, atr)
        labs = {}
        for tp_r, sl_r in CONFIGS:
            labs[tp_r, sl_r] = _barrier_labels(o, h, l, atr, tp_r, sl_r)
        data[sym] = dict(ts=ts, o=o, h=h, l=l, c=c, atr=atr,
                         feats=feats, labs=labs)
        print(f"{sym:>5}: {len(c)} bars", flush=True)

    t0 = min(int(d["ts"][0]) for d in data.values())
    t1 = max(int(d["ts"][-1]) for d in data.values())
    folds = wf_folds(t0, t1, 8, 56)

    def feat_mat(d, mask):
        return np.column_stack([d["feats"][k][mask] for k in FEATS])

    brier_mod = {cf: [] for cf in CONFIGS}
    brier_base = {cf: [] for cf in CONFIGS}
    all_rp = []   # (pess_r, ev, sym, side, ts) for EV>0 candidates
    lgb_params = dict(n_estimators=400, learning_rate=0.05, num_leaves=15,
                      min_child_samples=40, random_state=7, verbosity=-1)

    for k, (fs, fe) in enumerate(folds):
        cal_hi = fs - 7 * DAY
        cal_lo = cal_hi - CAL_DAYS * DAY
        for tp_r, sl_r in CONFIGS:
            for side, si in (("long", 0), ("short", 1)):
                Xtr, ytr, Xcal, ycal, Xte, yte, meta = [], [], [], [], [], [], []
                for sym, d in data.items():
                    ts = d["ts"]
                    lab = d["labs"][tp_r, sl_r][si]
                    m_tr = (ts < cal_lo) & np.isfinite(lab)
                    m_cal = (ts >= cal_lo) & (ts < cal_hi) & np.isfinite(lab)
                    m_te = (ts >= fs) & (ts < fe) & np.isfinite(lab)
                    if m_tr.sum() < 5000 or m_cal.sum() < 200:
                        continue
                    Xtr.append(feat_mat(d, m_tr))
                    ytr.append(lab[m_tr])
                    Xcal.append(feat_mat(d, m_cal))
                    ycal.append(lab[m_cal])
                    Xte.append(feat_mat(d, m_te))
                    yte.append(lab[m_te])
                    meta.append((sym, np.where(m_te)[0]))
                if not Xtr:
                    continue
                Xtr, ytr = np.vstack(Xtr), np.concatenate(ytr)
                Xcal, ycal = np.vstack(Xcal), np.concatenate(ycal)
                Xte, yte = np.vstack(Xte), np.concatenate(yte)
                m = lgb.LGBMClassifier(**lgb_params)
                m.fit(Xtr, ytr)
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(m.predict_proba(Xcal)[:, 1], ycal)
                p_te = iso.predict(m.predict_proba(Xte)[:, 1])
                brier_mod[tp_r, sl_r].append(
                    float(np.mean((p_te - yte) ** 2)))
                base = sl_r / (tp_r + sl_r)
                brier_base[tp_r, sl_r].append(
                    float(np.mean((base - yte) ** 2)))
                rr = tp_r / sl_r
                r0 = 0
                for sym, ii in meta:
                    ni = len(ii)
                    p_asset = p_te[r0:r0 + ni]
                    r0 += ni
                    d = data[sym]
                    sgn = 1.0 if side == "long" else -1.0
                    for j, i in enumerate(ii):
                        fill_i = i + 1
                        if fill_i >= len(d["c"]):
                            continue
                        fill = d["o"][fill_i]
                        risk = sl_r * d["atr"][i]
                        if not (np.isfinite(risk) and risk > 0):
                            continue
                        cost_r = (2 * COMM + GEN_SLIP) * fill / risk
                        ev = (p_asset[j] * rr - (1 - p_asset[j]) - cost_r)
                        if ev > 0:
                            slp = fill - sgn * sl_r * risk / sl_r
                            tpp = fill + sgn * tp_r * risk / sl_r
                            rp = sim_trade(d["o"], d["h"], d["l"], d["c"],
                                           fill_i, side, slp, tpp,
                                           HORIZON, d["atr"][i])
                            if np.isfinite(rp):
                                all_rp.append((float(rp), float(ev), sym,
                                               side, int(d["ts"][i])))
        print(f"fold {k}: done", flush=True)

    # ---- per-asset position slot, chronological ----------------------
    taken = []
    busy = {sym: -2 for sym in ASSETS}
    for rp, ev, sym, side, ts_i in sorted(all_rp, key=lambda x: x[4]):
        if ts_i > busy[sym]:
            taken.append((rp, ev, sym, side))
            busy[sym] = ts_i + HORIZON // 2   # ~occupancy while in trade

    print("\n=== portfolio (EV>0 rule, per-asset slot) ===")
    rp_arr = np.array([t[0] for t in taken]) if taken else np.array([])
    ev_arr = np.array([t[1] for t in taken]) if taken else np.array([])
    if rp_arr.size:
        eq = np.cumsum(rp_arr)
        dd = float(np.max(np.maximum.accumulate(eq) - eq))
        order = np.argsort(ev_arr)
        top = rp_arr[order[int(0.9 * len(order)):]]
        print(f"trades: n={rp_arr.size}  pess EV all={rp_arr.mean():+.4f}R "
              f"win={(rp_arr > 0).mean():.0%}")
        print(f"top-decile by model EV: pess EV={top.mean():+.4f}R "
              f"(n={top.size})")
        print(f"pooled maxDD={dd:.1f}R")
        for sd in ("long", "short"):
            msk = np.array([t[3] == sd for t in taken])
            if msk.any():
                print(f"  {sd:5s}: n={int(msk.sum())} "
                      f"ev={rp_arr[msk].mean():+.4f}R")

    print("\n=== gates ===")
    bm = float(np.mean([np.mean(v) for v in brier_mod.values()]))
    bb = float(np.mean([np.mean(v) for v in brier_base.values()]))
    ok_cfg = sum(
        float(np.mean(brier_base[cf])) - float(np.mean(brier_mod[cf])) > 0
        for cf in CONFIGS
    )
    k1 = (bb > bm) and ok_cfg >= 7
    if rp_arr.size >= 10:
        top = rp_arr[np.argsort(ev_arr)[int(0.9 * len(ev_arr)):]]
        k2 = bool(top.mean() > 0) and rp_arr.size >= 300
        dd = float(np.max(np.maximum.accumulate(np.cumsum(rp_arr))
                          - np.cumsum(rp_arr)))
    else:
        k2, dd = False, 99.0
    k3 = dd <= 20.0
    print(f"K1 brier: model {bm:.5f} vs base {bb:.5f} "
          f"(improved {ok_cfg}/10 cfgs): {'PASS' if k1 else 'FAIL'}")
    print(f"K2 top-decile EV>0 & n>=300: {'PASS' if k2 else 'FAIL'}")
    print(f"K3 maxDD {dd:.1f}R <= 20: {'PASS' if k3 else 'FAIL'}")
    print("OVERALL:", "PASS" if (k1 and k2 and k3) else "FAIL")


if __name__ == "__main__":
    run()



