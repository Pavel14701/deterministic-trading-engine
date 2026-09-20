"""Ensemble A/B: heterogeneous ranker blend vs single components.

TZ "ensemble ranking": the monolithic LightGBM head is replaced by a
configurable blend (LightGBM lambdarank + CatBoost YetiRank + L2
logreg).  Every config shares ONE feature matrix and the SAME walk
forward (protocol.py: 8 folds x 56d, expanding past-only train, 7d
embargo) and the SAME replay path (top-s pick per candidate, free
gate, unified sim + state machine) - heads are switched by config
alone.

Config grid is FIXED before the run (TZ item 8: no config fishing):

  lgbm_only        baseline (must reproduce the walk-forward head)
  catboost_only    ordered-boosting bias
  logreg_only      linear-signal diagnostic baseline
  lgbm+catboost    weighted 0.5/0.5
  all_three        weighted 0.4/0.4/0.2
  stacking         3 members, logreg meta on past-only OOF scores

Per config, pooled over folds: replayed-trade pooled_stats (mean R /
n / dd / bucketed sharpe), score-ranked decile spread and top-decile
EV on test picks (r_pess), flips@1e-6 (share of candidates whose
top-pick rule changes under 1e-6 score noise), peak gate EV (max mean
R over score-quantile gates).  Acceptance: ensemble beats the best
single component on peak gate EV and decile spread, dd not worse;
otherwise keep LightGBM-only (TZ item 6).

Usage: python engine/experiments/ensemble_ab.py [--quick]
  --quick: last 3 folds, catboost 60 iters - smoke/regression mode.
Full run saves runs/ensemble_ab.json.
"""

from __future__ import annotations

import json
import sys
import time

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from engine.backtest.protocol import (
    ENCODING_ZEROED,
    RankerData,
    assemble_ranker_data,
    fold_masks,
    load_asset,
    replay,
    train_ensemble_ranker,
    wf_folds,
)
from engine.ensemble.base import ComponentConfig
from engine.ensemble.catboost import CATBOOST_AVAILABLE
from engine.ensemble.combine import EnsembleConfig
from engine.metrics.trade import pooled_stats


TAGS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
QUICK = "--quick" in sys.argv

CATBOOST_FOLDS_PARAMS: dict[str, object] = (
    {"iterations": 60, "depth": 4} if QUICK else {}
)


def configs() -> dict[str, EnsembleConfig]:
    """The pre-registered grid (TZ section 5.2)."""
    return {
        "lgbm_only": EnsembleConfig(
            components=[ComponentConfig("lgbm")]
        ),
        "catboost_only": EnsembleConfig(
            components=[ComponentConfig("catboost")]
        ),
        "logreg_only": EnsembleConfig(
            components=[ComponentConfig("logreg")]
        ),
        "lgbm+catboost": EnsembleConfig(
            components=[
                ComponentConfig("lgbm", weight=0.5),
                ComponentConfig(
                    "catboost",
                    weight=0.5,
                    params=dict(CATBOOST_FOLDS_PARAMS),
                ),
            ]
        ),
        "all_three": EnsembleConfig(
            components=[
                ComponentConfig("lgbm", weight=0.4),
                ComponentConfig(
                    "catboost",
                    weight=0.4,
                    params=dict(CATBOOST_FOLDS_PARAMS),
                ),
                ComponentConfig("logreg", weight=0.2),
            ]
        ),
        "stacking": EnsembleConfig(
            components=[
                ComponentConfig("lgbm"),
                ComponentConfig(
                    "catboost", params=dict(CATBOOST_FOLDS_PARAMS)
                ),
                ComponentConfig("logreg"),
            ],
            combination="stacking",
            meta_learner="logreg",
            meta_folds=3,
        ),
    }


def decile_metrics(
    scores: np.ndarray, r: np.ndarray
) -> dict[str, float]:
    """Spread / top-decile EV over per-candidate top picks."""
    n = len(r)
    if n < 20:
        return {"decile_spread": 0.0, "top_decile_ev": 0.0}
    order = np.argsort(scores)
    k = n // 10
    top = float(r[order[-k:]].mean())
    bottom = float(r[order[:k]].mean())
    return {"decile_spread": top - bottom, "top_decile_ev": top}


def flips_at_1e_6(panel: pl.DataFrame, seed: int = 7) -> float:
    """Share of candidates whose top-pick rule flips under 1e-6 noise.

    Ranking robustness probe: add tiny gaussian noise to the scores
    and re-take the top pick per candidate; a high flip share means
    the head's rule choice is arbitrary among near-ties.
    """
    rng = np.random.default_rng(seed)
    s = panel["s"].to_numpy()
    noisy = s + rng.normal(0.0, 1e-6, size=len(s))
    top0 = (
        panel.with_columns(pl.Series("s", s))
        .sort(["_cand", "s"])
        .group_by("_cand")
        .last()["rule"]
        .to_list()
    )
    top1 = (
        panel.with_columns(pl.Series("s", noisy))
        .sort(["_cand", "s"])
        .group_by("_cand")
        .last()["rule"]
        .to_list()
    )
    if not top0:
        return 0.0
    return sum(a != b for a, b in zip(top0, top1)) / len(top0)


def peak_gate_ev(scores: np.ndarray, r: np.ndarray) -> float:
    """Max mean R over score-quantile gates (top-q candidates).

    Returns the actual maximum (possibly negative - do not read 0.0
    as "no gate helped" vs "no picks").
    """
    if len(r) < 20:
        return 0.0
    order = np.argsort(scores)[::-1]
    best = -np.inf
    for q in (0.05, 0.1, 0.15, 0.2, 0.3, 0.5):
        k = max(20, int(len(r) * q))
        if k <= len(r):
            best = max(best, float(r[order[:k]].mean()))
    return best


def run_config(
    name: str,
    cfg: EnsembleConfig,
    rd: RankerData,
    data: dict[str, dict[str, object]],
    folds: list[tuple[int, int]],
) -> dict[str, object]:
    """One config through the full WF + replay loop."""
    acc_r: list[np.ndarray] = []
    acc_ts: list[np.ndarray] = []
    pick_s: list[np.ndarray] = []
    pick_r: list[np.ndarray] = []
    flips: list[float] = []
    t_start = time.time()
    for fi, (fs_, fe) in enumerate(folds):
        tr, te = fold_masks(rd.ts, fs_, fe)
        sc = train_ensemble_ranker(
            rd.x, rd.y, rd.row, rd.ts, np.where(tr)[0], cfg
        )
        for ai, t in enumerate(TAGS):
            mask = rd.asset_row == ai
            panel = data[t]["panel"].with_columns(
                pl.Series("s", sc[mask]),
                pl.Series("is_test", te[mask]),
            )
            picks = (
                panel.filter(pl.col("is_test"))
                .sort(["_cand", "s"])
                .group_by("_cand")
                .last()
                .sort("entry_idx")
            )
            pick_s.append(picks["s"].to_numpy())
            pick_r.append(picks["r_pess"].to_numpy())
            flips.append(flips_at_1e_6(picks))
            r, ts_, _meta = replay(panel, data[t])
            if r.size:
                acc_r.append(r)
                acc_ts.append(ts_)
        print(f"  {name} f{fi}: {time.time() - t_start:,.0f}s",
              flush=True)
    pooled = np.concatenate(acc_r) if acc_r else np.array([0.0])
    pooled_ts = np.concatenate(acc_ts) if acc_ts else np.array([0.0])
    s_all = np.concatenate(pick_s)
    r_all = np.concatenate(pick_r)
    stats = pooled_stats(pooled, pooled_ts)
    spread = decile_metrics(s_all, r_all)
    out: dict[str, object] = {
        "pooled": stats,
        "decile_spread": spread["decile_spread"],
        "top_decile_ev": spread["top_decile_ev"],
        "flips_at_1e_6": float(np.mean(flips)) if flips else 0.0,
        "peak_gate_ev": peak_gate_ev(s_all, r_all),
        "wall_s": time.time() - t_start,
    }
    print(
        f"=> {name}: pess={stats['mean']:+.3f} "
        f"(n={stats['n']}, dd={stats['dd']:.1f}R) "
        f"spread={out['decile_spread']:+.3f} "
        f"peak_gate={out['peak_gate_ev']:+.3f} "
        f"flips@1e-6={out['flips_at_1e_6']:.3f}",
        flush=True,
    )
    return out


def main() -> None:
    if not CATBOOST_AVAILABLE:
        raise SystemExit(
            "catboost is not installed - the grid needs it; "
            "install catboost or drop its configs"
        )
    print("loading assets...", flush=True)
    data = {t: load_asset("", t) for t in TAGS}
    for t, d in data.items():
        print(t, "rows:", d["panel"].height,
              "range:", d["panel"]["ts"].min(), "->",
              d["panel"]["ts"].max())
    rd = assemble_ranker_data(data, TAGS, ENCODING_ZEROED)
    t0 = int(min(data[t]["panel"]["ts"].min() for t in TAGS))
    t1 = int(max(data[t]["panel"]["ts"].max() for t in TAGS))
    folds = wf_folds(t0, t1)[-3:] if QUICK else wf_folds(t0, t1)
    print(f"\n=== ensemble A/B: {len(folds)} folds, "
          f"{rd.x.shape[0]} rows x {rd.x.shape[1]} feats ===",
          flush=True)

    results: dict[str, object] = {}
    for name, cfg in configs().items():
        print(f"--- {name} ---", flush=True)
        results[name] = run_config(name, cfg, rd, data, folds)

    base = results["lgbm_only"]
    print("\n=== acceptance vs lgbm_only (TZ section 6) ===")
    verdict = {}
    for name, res in results.items():
        if name == "lgbm_only":
            continue
        verdict[name] = {
            "mean_R_beats": res["pooled"]["mean"]
            > base["pooled"]["mean"],
            "spread_beats": res["decile_spread"]
            > base["decile_spread"],
            "peak_gate_beats": res["peak_gate_ev"]
            > base["peak_gate_ev"],
            "dd_not_worse": res["pooled"]["dd"]
            <= base["pooled"]["dd"] + 1.0,
        }
        print(name, verdict[name])
    (REPO / "runs").mkdir(exist_ok=True)
    (REPO / "runs" / "ensemble_ab.json").write_text(
        json.dumps(
            {
                "results": results,
                "verdict": verdict,
                "quick": QUICK,
                "n_folds": len(folds),
            },
            indent=1,
            default=float,
        )
    )
    print("saved runs/ensemble_ab.json")


if __name__ == "__main__":
    main()
