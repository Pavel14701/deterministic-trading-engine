"""D.14: FeatureSpec feature family A/B against the D.13 baseline.

Same panel rows, same fold calendar, same pess labels as the D.13
protocol - only the ranker feature matrix changes (the clean A/B):

  d13|enc=d13  : D.13 features, ENCODING_D13 (baseline reproduction)
  d13|enc=d8b  : D.13 features, ENCODING_D8B (isolates the encoding)
  d14|enc=d8b  : D.14 FeatureSpec family (NaN-native), D.13 dropped
  combo|enc=d8b: D.13 + D.14 columns, ENCODING_D8B

The D.14 family is defined once as a FeatureSpec (JSON-serializable,
git-versioned): bar-DSL indicators + 4h as-of HTF columns via
asof_join_features + HybridContextFactory.  All expressions are
scale-free (normalized by ``close``) and causal by construction
(prefix invariance + known_ts joins are pinned by unit tests).

Ranker-only free gate (the D.13g finding: free >= table), past-only
train mask, deterministic seed.  Also reports the conditional-EV
decile ladder (top vs bottom score decile on test rows) per arm.
Saves runs/d14_feature_family.json.
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

from engine.feature_provider import HybridContextFactory  # noqa: E402
from engine.feature_spec import FeatureDef, FeatureSpec, collect_features  # noqa: E402
from engine.mtf import asof_join_features, resample_ohlcv  # noqa: E402
from engine.protocol import (  # noqa: E402
    ENCODING_D13,
    ENCODING_D8B,
    assemble_ranker_data,
    fold_masks,
    load_asset,
    pooled_stats,
    replay,
    train_ranker,
    wf_folds,
)

TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
VARIANT_DIR = ""  # main dataset panel (the D.13 reference)
HTF_BAR = "4h"

#: The D.14 feature family - one JSON-serializable spec, scale-free.
D14_SPEC = FeatureSpec(
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
D14_COLS = ["h4h_close", "h4h_low", "h4h_high", "h4h_age_ms"]


def build_joined(tag: str) -> pl.DataFrame:
    """1h base bars + 4h as-of columns (known_ts-causal) for one tag."""
    raw = pl.read_parquet(REPO / f"data/okx/raw_{tag}_1m.parquet")
    base = resample_ohlcv(raw, "1h")
    htf = resample_ohlcv(raw, HTF_BAR)
    return asof_join_features(
        base, htf, ["close", "low", "high"], prefix="h4h_",
        age_col="h4h_age_ms",
    )


def d14_frame(panel: pl.DataFrame, joined: pl.DataFrame) -> pd.DataFrame:
    """D.14 feature matrix aligned 1:1 with the panel rows."""
    ev = np.unique(panel["entry_idx"].to_numpy().astype(np.int64))
    factory = HybridContextFactory(joined, D14_COLS)
    feats = collect_features(
        joined, D14_SPEC, ev, context_factory=factory
    )
    names = [f.name for f in D14_SPEC.features]
    pos = {int(e): k for k, e in enumerate(feats["event_idx"].to_list())}
    idx = np.array([pos[int(i)] for i in panel["entry_idx"].to_numpy()])
    out = feats.select(names).to_numpy()[idx]
    return pd.DataFrame(out, columns=names)


def arm_data(
    data: dict[str, dict], tags: list[str], kind: str,
    d14: dict[str, pd.DataFrame],
) -> dict[str, dict]:
    """Return the per-arm ``feats`` view (panel untouched)."""
    out: dict[str, dict] = {}
    for t in tags:
        f13 = data[t]["feats"]
        if kind == "d14":
            feats = d14[t]
        elif kind == "combo":
            feats = pd.concat(
                [f13.reset_index(drop=True), d14[t].reset_index(drop=True)],
                axis=1,
            )
        else:
            feats = f13
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
    d14 = {t: d14_frame(data[t]["panel"], joined[t]) for t in TAGS}
    for t in TAGS:
        print(
            f"  {t}: panel={data[t]['panel'].height} rows, "
            f"d14 feats={d14[t].shape[1]} cols, "
            f"NaN share={float(np.isnan(d14[t].to_numpy()).mean()):.3f}",
            flush=True,
        )

    arms = {
        "d13|enc=d13": (ENCODING_D13, "d13"),
        "d13|enc=d8b": (ENCODING_D8B, "d13"),
        "d14|enc=d8b": (ENCODING_D8B, "d14"),
        "combo|enc=d8b": (ENCODING_D8B, "combo"),
    }
    rds = {
        name: assemble_ranker_data(
            arm_data(data, TAGS, kind, d14), TAGS, enc
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
        "\n=== D.14 feature family A/B: test pess R (free gate) ===",
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
        "spec": D14_SPEC.to_dict(),
        "folds": len(folds),
    }
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "d14_feature_family.json").write_text(
        json.dumps(results, indent=1)
    )
    print("saved runs/d14_feature_family.json", flush=True)


if __name__ == "__main__":
    main()