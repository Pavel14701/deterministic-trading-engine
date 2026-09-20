"""OB/AVSL ablation - decompose the stack edge (+0.44R test pess).

Four panel variants (BTC/ETH/SOL, 1h base, identical builder code):
  A  real OB zones + AVSL              (control; input = wf_ab cell B)
  B  placebo OB zones + AVSL           (isolates the OB contribution)
  C  real OB zones, AVSL off           (isolates the AVSL contribution)
  D  placebo OB zones, AVSL off        (detector-free stack: stop/TP
                                        geometry + ranker + gate only)

Placebo scheme (causal): every order block keeps its side, height and
confirm time but is shifted OUTWARD - demand further below price,
supply further above - by U(0.25, 3.0) x ATR(confirm_idx).  This
destroys the exact swing alignment while keeping touch plausibility
(zones stay on their natural side of price) and uses no future data.
The same seed per asset makes the placebo zones identical in B and D,
so D - B isolates AVSL and A - B isolates OB exactly.

AVSL-off: the avsl/avsr anchor series are set to NaN everywhere, so
the avsl_bounce family yields nothing, the d_avsl/d_avsr features are
NaN (0 after the wf nan_to_num) and the anchor:avsl*/avsr* stop rules
degenerate to invalid rows - AVSL information is removed end to end.

Panels: data/ablation/{V}/{TAG}_1h.parquet (same schema as
data/mtf_dataset).  Evaluation is a verbatim port of the wf_ab cell B
protocol: 8 folds x 56 days, 7-day embargo, expanding train,
multi-asset lambdarank (seed 7), rule-table gate, cap state machine.
Results: runs/ablation.json + console table.
"""

from __future__ import annotations

import json
import os
import sys
import zlib

from dataclasses import replace
from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    assemble_ranker_data,
    fold_masks,
    load_asset as protocol_load_asset,
    replay,
    train_ranker,
    wf_folds,
)
from engine.datasets.mtf import (
    LTF_BAR,
    _anchors_nan_safe,
    _entry_feature_row,
    _htf_asof_state,
    _htf_zone_ts,
    _ltf_asof_features,
    _outcome_rows,
)
from engine.datasets.okx import detect_order_blocks
from engine.datasets.stops import STOP_PANEL
from engine.features.indicators import compute_atr
from engine.features.mtf import resample_ohlcv
from engine.features.panel import (
    assign_splits,
    rolling_percentile,
    trend_state,
)
from engine.infra.config import load_config
from engine.metrics.trade import trade_curve_stats
from engine.model.ranker import fit_rule_table
from engine.structure.candidates import collect_candidates
from engine.structure.zones import (
    build_tp_sl as _build_tp_sl,
    paint_zone as _paint_zone,
)


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANTS = ("A", "B", "C", "D")
PLACEBO_ATR = (0.25, 3.0)
# Robustness: ABL_SEED / ABL_SUFFIX / ABL_VARIANTS env vars let a rerun
# rebuild only some variants with another placebo seed into suffixed
# dirs (e.g. ABL_SEED=2 ABL_VARIANTS=B,D ABL_SUFFIX=s2).
RNG_SEED = int(os.environ.get("ABL_SEED", "20260919"))
ABL_SUFFIX = os.environ.get("ABL_SUFFIX", "")
ABL_VARIANTS = tuple(
    v for v in os.environ.get("ABL_VARIANTS", "A,B,C,D").split(",") if v
)
N_FOLDS, FOLD_DAYS, EMBARGO_DAYS = 8, 56, 7
DAY_MS = 86_400_000
BASE_TF = "1h"
HTF_BARS = ["4h", "1d"]


def abl_dir(variant: str) -> Path:
    """Directory holding the variant panels."""
    return REPO / "data" / "ablation" / (variant + ABL_SUFFIX)


def tag_file(variant: str, tag: str) -> Path:
    """Panel parquet path for one (variant, asset) pair."""
    return abl_dir(variant) / f"{tag.replace('-', '')}_1h.parquet"


def placebo_obs(obs: list, atr: np.ndarray, rng: np.random.Generator) -> list:
    """Shift each zone outward by U(0.25, 3.0) x ATR(confirm_idx).

    Demand zones move further below price, supply zones further above;
    side, height and confirm timing are preserved, so the placebo keeps
    the touch machinery alive while destroying swing alignment.
    """
    out = []
    for ob in obs:
        i = max(ob.confirm_idx, 0)
        a = atr[i] if i < len(atr) else np.nan
        if not np.isfinite(a) or a <= 0:
            out.append(ob)
            continue
        shift = float(rng.uniform(*PLACEBO_ATR)) * a
        if ob.block_type == "demand":
            out.append(replace(
                ob,
                zone_low=ob.zone_low - shift,
                zone_high=ob.zone_high - shift,
            ))
        else:
            out.append(replace(
                ob,
                zone_low=ob.zone_low + shift,
                zone_high=ob.zone_high + shift,
            ))
    return out


def build_panel(variant: str, tag: str, risk) -> dict:
    """Build one variant panel.

    Verbatim port of build_mtf_dataset's per-asset body with the
    variant knobs (placebo OB / AVSL-off) applied at the zone level.
    """
    import time

    t0 = time.time()
    rng = np.random.default_rng(RNG_SEED + zlib.crc32(tag.encode()))
    df1m = pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet")
    ltf = resample_ohlcv(df1m, LTF_BAR)
    base = resample_ohlcv(df1m, BASE_TF)
    htf_frames = []
    for h in HTF_BARS:
        f = resample_ohlcv(df1m, h)
        f = f.with_columns(pl.Series("_atr", compute_atr(f, risk=risk)))
        htf_frames.append(f)

    atr = compute_atr(base, risk=risk)
    obs = detect_order_blocks(base, atr, timeframe=BASE_TF)
    n_real = len(obs)
    if variant in ("B", "D"):
        obs = placebo_obs(obs, atr, rng)
    anchors = _anchors_nan_safe(base)
    if variant in ("C", "D"):
        anchors["avsl"] = np.full(len(base), np.nan)
        anchors["avsr"] = np.full(len(base), np.nan)
    cands = collect_candidates(
        base, obs, atr, avsl=anchors["avsl"], avsr=anchors["avsr"]
    )

    open_p = base["open"].to_numpy()
    high = base["high"].to_numpy()
    low = base["low"].to_numpy()
    close = base["close"].to_numpy()
    ts = base["ts"].to_numpy()
    n = len(base)
    z50, slope50, _sign = trend_state(close, atr)
    atr_pct = np.where(close > 0, atr / close, np.nan)
    vol_pct = rolling_percentile(atr_pct, window=500)
    bbw = (anchors["bb_u"] - anchors["bb_l"]) / close
    bbw_pct = rolling_percentile(bbw, window=500)
    obs_by_id = {ob.id: ob for ob in obs}

    ltf_known_ts = ltf["known_ts"].to_numpy()
    ltf_close = ltf["close"].to_numpy()
    ltf_vol = ltf["volume"].to_numpy()
    htf_zts = []
    for h, f in zip(HTF_BARS, htf_frames):
        hobs = detect_order_blocks(f, f["_atr"].to_numpy(), timeframe=h)
        if variant in ("B", "D"):
            hobs = placebo_obs(hobs, f["_atr"].to_numpy(), rng)
        htf_zts.append(_htf_zone_ts(hobs, f))

    rows = []
    for side in ("long", "short"):
        sub = cands.filter(pl.col("side") == side)
        if sub.is_empty():
            continue
        blocks = [
            ob for ob in obs
            if (ob.block_type.lower() == "demand") == (side == "long")
        ]
        zone_arr = _paint_zone(blocks, n, side)
        rule_levels = {
            rule: _build_tp_sl(
                close, atr, rule, 2.0, side, zone_arr,
                anchors=anchors, min_risk_atr=0.5,
            )
            for rule in STOP_PANEL
        }
        for cand in sub.iter_rows(named=True):
            i = int(cand["entry_idx"])
            if i + 1 >= n or not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            htf_states = [
                _htf_asof_state(f, zts, int(ts[i]), atr[i])
                for f, zts in zip(htf_frames, htf_zts)
            ]
            ltf_feats = _ltf_asof_features(
                ltf_known_ts, ltf_close, ltf_vol, int(ts[i]), atr[i]
            )
            feat = _entry_feature_row(
                cand, i, int(ts[i]), open_p, high, low, close, atr,
                anchors, z50, slope50, vol_pct, bbw_pct, obs_by_id,
                htf_states, ltf_feats,
            )
            rows += _outcome_rows(
                feat, i, side, cand["zone_low"], cand["zone_high"],
                open_p, high, low, close, atr, rule_levels, 48,
                risk.commission_pct, risk.slippage_pct, 0.1, 5,
                min_risk_atr=0.5,
            )

    table = pl.DataFrame(rows)
    entry_idxs = table["entry_idx"].unique().to_numpy().astype(np.int64)
    split_map = dict(zip(entry_idxs.tolist(), assign_splits(entry_idxs, n, 48)))
    table = table.with_columns(
        pl.col("entry_idx")
        .replace_strict(split_map, default="", return_dtype=pl.Utf8)
        .alias("split")
    )
    out = tag_file(variant, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.write_parquet(out)
    fam = cands.group_by("family").len().sort("family").to_dicts()
    print(f"  {variant}/{tag}: {n_real} OB -> {cands.height} cands, "
          f"{table.height} rows ({time.time() - t0:.0f}s) -> {out}",
          flush=True)
    return {"ob": n_real, "cands": cands.height, "rows": table.height,
            "by_family": {d["family"]: d["len"] for d in fam}}


def load_asset(variant: str, tag: str) -> dict:
    """Load one variant panel exactly like wf_ab's load_asset."""
    d = protocol_load_asset(variant + ABL_SUFFIX, tag)
    d["tag"] = tag
    return d


def replay_panel(panel, d):
    """Rule-table gate + unified sim + state machine (wf_ab port)."""
    table = fit_rule_table(panel.filter(~pl.col("is_test")))
    r, _ts, _meta = replay(panel, d, table)
    return r


def evaluate(variant: str) -> dict:
    """Walk-forward cell-B evaluation of one variant (wf_ab port)."""
    print(f"\n=== evaluating variant {variant} ===", flush=True)
    data = {t: load_asset(variant, t) for t in TAGS}
    for t, d in data.items():
        print(f"  {t}: rows={d['panel'].height}", flush=True)

    rd = assemble_ranker_data(data, TAGS)
    FEATS_ALL, ASSET_ROW = rd.x, rd.asset_row
    Y_ALL, TS_ALL, ROW_ALL = rd.y, rd.ts, rd.row

    def lgb_ranker(tr_ix):
        return train_ranker(FEATS_ALL, Y_ALL, ROW_ALL, tr_ix)

    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    folds = wf_folds(t0, t1)

    fold_means, all_r = [], []
    for fi, (fs_, fe) in enumerate(folds):
        tr_mask, te_mask = fold_masks(TS_ALL, fs_, fe)
        sc = lgb_ranker(np.where(tr_mask)[0])
        eb = []
        for ai, t in enumerate(TAGS):
            pm = data[t]["panel"].with_columns(
                pl.Series("s", sc[ASSET_ROW == ai]),
                pl.Series("is_test", te_mask[ASSET_ROW == ai]))
            eb.append(replay_panel(pm, data[t]))
        eb = np.concatenate([x for x in eb if x.size]) \
            if any(x.size for x in eb) else np.array([])
        fold_means.append(float(eb.mean()) if eb.size else float("nan"))
        all_r.append(eb)
        print(f"  f{fi}: {variant} pess={eb.mean():+.3f} (n={eb.size})",
              flush=True)

    pooled = np.concatenate([x for x in all_r if x.size])
    res = {"mean": float(pooled.mean()), "n": int(pooled.size),
           "dd": float(trade_curve_stats(pooled)["max_dd_r"]),
           "folds": fold_means}
    print(f"  => variant {variant}: pess={res['mean']:+.3f} "
          f"(n={res['n']}, dd={res['dd']:.1f}R)", flush=True)
    return res


def main() -> None:
    """Build all variant panels (reuse existing with --reuse), evaluate."""
    import time

    t0 = time.time()
    risk = load_config(risk_profile="wide").risk
    summaries = {}
    for v in ABL_VARIANTS:
        for t in TAGS:
            if "--reuse" in sys.argv and tag_file(v, t).exists():
                continue
            summaries[f"{v}/{t}"] = build_panel(v, t, risk)

    results = {v: evaluate(v) for v in ABL_VARIANTS}
    a = results.get("A", results[min(results)])
    print("\n=== ABLATION: contribution to test pess R ===", flush=True)
    desc = {
        "A": "OB + AVSL (control)",
        "B": "placebo OB + AVSL",
        "C": "real OB, AVSL off",
        "D": "placebo OB, AVSL off",
    }
    for v in ABL_VARIANTS:
        r = results[v]
        print(f"  {v}  {r['mean']:+.3f}  (n={r['n']:4d}, dd={r['dd']:.1f}R)"
              f"  {desc[v]}", flush=True)
    if "A" in results and "B" in results:
        print(f"\n  OB contribution     (A - B): "
              f"{results['A']['mean'] - results['B']['mean']:+.3f}R",
              flush=True)
    if "A" in results and "C" in results:
        print(f"  AVSL contribution   (A - C): "
              f"{results['A']['mean'] - results['C']['mean']:+.3f}R",
              flush=True)
    if "D" in results:
        print(f"  detector-free stack (D):    {results['D']['mean']:+.3f}R",
              flush=True)
        if a["mean"]:
            print(f"  share of A explained by D:  "
                  f"{results['D']['mean'] / a['mean']:.0%}", flush=True)

    out = {
        "seed": RNG_SEED, "placebo_atr": PLACEBO_ATR,
        "variants": results, "build": summaries,
        "elapsed_s": time.time() - t0,
    }
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / f"ablation{ABL_SUFFIX}.json").write_text(json.dumps(out, indent=1))
    print(f"saved runs/ablation{ABL_SUFFIX}.json", flush=True)


if __name__ == "__main__":
    main()
