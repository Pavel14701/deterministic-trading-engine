"""DSL feature-family A/B against the hand-built ranker features.

Same panel rows, same fold calendar, same pess labels as the walk-
forward protocol - only the ranker feature matrix changes (the clean
A/B):

  ranker|enc=zeroed : hand-built features, ENCODING_ZEROED (baseline)
  ranker|enc=native : hand-built features, ENCODING_NATIVE (encoding
                      effect isolated)
  spec|enc=native   : DSL FeatureSpec family (NaN-native) alone
  combo|enc=native  : hand-built + DSL columns, ENCODING_NATIVE

The DSL family is defined once as a FeatureSpec (JSON-serializable,
git-versioned): bar-DSL indicators + 4h as-of HTF columns via
asof_join_features + HybridContextFactory.  All expressions are
scale-free (normalized by ``close``) and causal by construction
(prefix invariance + known_ts joins are pinned by unit tests).

Ranker-only free gate (free >= rule-table gate per the ranker-only
ablation), past-only train mask, deterministic seed.  Also reports the
conditional-EV decile ladder (top vs bottom score decile on test rows)
per arm.  Saves runs/feature_family.json.
"""
from __future__ import annotations

import json
import sys

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    ENCODING_NATIVE,
    ENCODING_ZEROED,
    assemble_ranker_data,
    fold_masks,
    load_asset,
    replay,
    train_ranker,
    wf_folds,
)
from engine.features.mtf import (
    asof_join_features,
    resample_ohlcv,
)
from engine.features.provider import HybridContextFactory
from engine.features.spec import (
    FeatureDef,
    FeatureSpec,
    collect_features,
)
from engine.metrics.trade import pooled_stats


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANT_DIR = ""  # main dataset panel (the protocol reference)
HTF_BAR = "4h"

#: The DSL feature family - one JSON-serializable spec, scale-free.
DSL_SPEC = FeatureSpec(
    features=(
        FeatureDef("mom1", expr="close[1] / close"),
        FeatureDef("mom4", expr="close[4] / close"),
        FeatureDef("atr_pct24", expr="atr(period=24) / close"),
        FeatureDef("rsi", expr="rsi(period=14)"),
        FeatureDef("ema_gap", expr="(close - ema(period=50)) / close"),
        FeatureDef(
            "sma_slope", expr="(sma(period=24) - sma(period=96)) / close"
        ),
        FeatureDef("rng", expr="(high - low) / close"),
        FeatureDef("vol_ratio", expr="volume / (volume[24] + 1.0)"),
        FeatureDef("htf_gap", expr="(close - h4h_close) / close"),
        FeatureDef("htf_low_dist", expr="(close - h4h_low) / close"),
        FeatureDef("htf_high_dist", expr="(h4h_high - close) / close"),
        FeatureDef("htf_range", expr="(h4h_high - h4h_low) / close"),
        FeatureDef("htf_age_h", expr="h4h_age_ms / 3600000.0"),
    )
)
HTF_COLS = ["h4h_close", "h4h_low", "h4h_high", "h4h_age_ms"]


def build_joined(tag: str) -> pl.DataFrame:
    """1h base bars + 4h as-of columns (known_ts-causal) for one tag."""
    raw = pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet")
    base = resample_ohlcv(raw, "1h")
    htf = resample_ohlcv(raw, HTF_BAR)
    return asof_join_features(
        base, htf, ["close", "low", "high"], prefix="h4h_",
        age_col="h4h_age_ms",
    )


def spec_frame(panel: pl.DataFrame, joined: pl.DataFrame) -> pd.DataFrame:
    """DSL feature matrix aligned 1:1 with the panel rows."""
    ev = np.unique(panel["entry_idx"].to_numpy().astype(np.int64))
    factory = HybridContextFactory(joined, HTF_COLS)
    feats = collect_features(
        joined, DSL_SPEC, ev, context_factory=factory
    )
    names = [f.name for f in DSL_SPEC.features]
    pos = {int(e): k for k, e in enumerate(feats["event_idx"].to_list())}
    idx = np.array([pos[int(i)] for i in panel["entry_idx"].to_numpy()])
    out = feats.select(names).to_numpy()[idx]
    return pd.DataFrame(out, columns=names)


def arm_data(
    data: dict[str, dict], tags: list[str], kind: str,
    feats_spec: dict[str, pd.DataFrame],
) -> dict[str, dict]:
    """Return the per-arm ``feats`` view (panel untouched)."""
    out: dict[str, dict] = {}
    for t in tags:
        feats_base = data[t]["feats"]
        if kind == "feats_spec":
            feats = feats_spec[t]
        elif kind == "combo":
            feats = pd.concat(
                [feats_base.reset_index(drop=True), feats_spec[t].reset_index(drop=True)],
                axis=1,
            )
        else:
            feats = feats_base
        out[t] = {**data[t], "feats": feats}
    return out


def decile_ladder(
    s: np.ndarray, y: np.ndarray, n_buckets: int = 10,
) -> list[dict]:
    """Mean pess-R per score decile (pooled test rows)."""
    edges = np.quantile(s, np.linspace(0.0, 1.0, n_buckets + 1)[1:-1])
    b = np.searchsorted(edges, s, side="right")
    return [
        {
            "decile": k,
            "n": int((b == k).sum()),
            "mean_r": float(y[b == k].mean()) if (b == k).any()
            else float("nan"),
        }
        for k in range(n_buckets)
    ]


def main() -> None:
    print("=== loading panels ===", flush=True)
    data = {t: load_asset(VARIANT_DIR, t, None) for t in TAGS}
    joined = {t: build_joined(t) for t in TAGS}
    feats_spec = {t: spec_frame(data[t]["panel"], joined[t]) for t in TAGS}
    for t in TAGS:
        print(
            f"  {t}: panel={data[t]['panel'].height} rows, "
            f"feats_spec feats={feats_spec[t].shape[1]} cols, "
            f"NaN share={float(np.isnan(feats_spec[t].to_numpy()).mean()):.3f}",
            flush=True,
        )

    arms = {
        "ranker|enc=zeroed": (ENCODING_ZEROED, "ranker"),
        "ranker|enc=native": (ENCODING_NATIVE, "ranker"),
        "spec|enc=native": (ENCODING_NATIVE, "spec"),
        "combo|enc=native": (ENCODING_NATIVE, "combo"),
    }
    rds = {
        name: assemble_ranker_data(
            arm_data(data, TAGS, kind, feats_spec), TAGS, enc
        )
        for name, (enc, kind) in arms.items()
    }

    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    folds = wf_folds(t0, t1)
    print(f"=== {len(folds)} folds ===", flush=True)

    acc: dict[str, dict[str, list[np.ndarray]]] = {
        name: {"r": [], "ts": []} for name in arms
    }
    lad: dict[str, dict[str, list[np.ndarray]]] = {
        name: {"s": [], "y": []} for name in arms
    }
    fold_means: dict[str, list[float]] = {name: [] for name in arms}
    for fi, (fs_, fe) in enumerate(folds):
        line = f"  f{fi}:"
        for name in arms:
            rd = rds[name]
            tr, te = fold_masks(rd.ts, fs_, fe)
            sc = train_ranker(rd.x, rd.y, rd.row, np.where(tr)[0])
            rs, ts_taken = [], []
            for ai, t in enumerate(TAGS):
                pm = data[t]["panel"].with_columns(
                    pl.Series("s", sc[rd.asset_row == ai]),
                    pl.Series("is_test", te[rd.asset_row == ai]),
                )
                r, ts_, _ = replay(pm, data[t], None)  # free gate
                rs.append(r)
                ts_taken.append(ts_)
                m = te[rd.asset_row == ai]
                lad[name]["s"].append(sc[rd.asset_row == ai][m])
                lad[name]["y"].append(rd.y[rd.asset_row == ai][m])
            r_all = np.concatenate([x for x in rs if x.size])
            acc[name]["r"].append(r_all)
            acc[name]["ts"].append(np.concatenate(ts_taken))
            fold_means[name].append(
                float(r_all.mean()) if r_all.size else float("nan")
            )
            line += f"  {name.split('|')[0]}={r_all.mean():+.3f}"
        print(line, flush=True)

    results: dict = {}
    print(
        "\n=== feature family A/B: test pess R (free gate) ===",
        flush=True,
    )
    for name in arms:
        pooled = np.concatenate(acc[name]["r"])
        pooled_ts = np.concatenate(acc[name]["ts"])
        g = pooled_stats(pooled, pooled_ts)
        s_all = np.concatenate(lad[name]["s"])
        y_all = np.concatenate(lad[name]["y"])
        ladder = decile_ladder(s_all, y_all)
        spread = ladder[-1]["mean_r"] - ladder[0]["mean_r"]
        results[name] = {
            "pooled": g,
            "fold_means": fold_means[name],
            "deciles": ladder,
            "decile_spread": spread,
        }
        d = " ".join(f"{x['mean_r']:+.2f}" for x in ladder)
        print(
            f"  {name:16s} pess={g['mean']:+.3f} (n={g['n']}, "
            f"dd={g['dd']:.1f}R, sharpe={g['sharpe_ann_bucketed']:.2f})  "
            f"decile spread={spread:+.3f}\n"
            f"    ladder: {d}",
            flush=True,
        )

    results["_meta"] = {
        "tags": TAGS,
        "variant_dir": VARIANT_DIR,
        "htf_bar": HTF_BAR,
        "spec": DSL_SPEC.to_dict(),
        "folds": len(folds),
    }
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "feature_family.json").write_text(
        json.dumps(results, indent=1)
    )
    print("saved runs/feature_family.json", flush=True)


if __name__ == "__main__":
    main()