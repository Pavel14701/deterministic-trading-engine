"""Stage B: train the MTF model towers and produce the Gate-2 report.

Usage::

    uv run python scripts/train_mtf_model.py \
        --dataset data/mtf_dataset/BTCUSDT_1h.parquet

Towers (LightGBM, all features causal by construction):

- entry head  - P(r_net > 0) at the reference config, used as an entry
  filter with an EV-calibrated threshold tuned on the val split;
- stop head   - P(survive) per stop rule, argmax policy vs the fixed
  zone rule;
- tp head     - E[r_net] regression, a sanity cross-check.

Outputs ``data/mtf_model/report.json`` and ``*.txt`` boosters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import lightgbm as lgb  # noqa: E402

from ai.src.mtf_model import (  # noqa: E402
    REFERENCE_RULE,
    REFERENCE_TARGET,
    apply_rule_table,
    build_features,
    candidate_key,
    describe_by_regime,
    ev_threshold,
    fit_rule_table,
    fixed_rule_per_candidate,
    oracle_policy_ev,
    paired_bootstrap_diff,
    per_candidate_pick,
    policy_by_rule_choice,
    random_rule_choice_ev,
    select_entry_rows,
    select_stop_rows,
    trade_curve_stats,
)

LGB_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=30,
    subsample=0.9,
    subsample_freq=1,
    colsample_bytree=0.9,
    random_state=7,
    verbosity=-1,
)

RULE_COL = "rule"


def _ev(df: pl.DataFrame) -> dict[str, float]:
    r = df["r_net"].fill_nan(None).drop_nulls()
    return {
        "n": df.height,
        "ev": float(r.mean() or 0.0),
        "win_rate": float((r > 0).mean() or 0.0),
    }


def _fit_clf(X_tr, y_tr, cat_names: list[str]):
    m = lgb.LGBMClassifier(**LGB_PARAMS)
    m.fit(X_tr, y_tr, categorical_feature=cat_names)
    return m


def train_entry_head(
    entry: pl.DataFrame, out_dir: Path
) -> tuple[dict, object, float]:
    """Entry filter: p_win model + EV-calibrated threshold."""
    train = entry.filter(pl.col("split") == "train")
    val = entry.filter(pl.col("split") == "val")
    test = entry.filter(pl.col("split") == "test")

    X_tr = build_features(train)
    cat_names = [c for c in X_tr.columns if str(X_tr[c].dtype) == "category"]
    y_tr = (train["r_net"].to_numpy() > 0).astype(int)
    model = _fit_clf(X_tr, y_tr, cat_names)
    model.booster_.save_model(str(out_dir / "entry_head.txt"))

    report: dict = {"baseline": {}, "filtered": {}, "threshold": {}}
    thr = 0.5
    for name, part in (("train", train), ("val", val), ("test", test)):
        report["baseline"][name] = _ev(part)
        p = model.predict_proba(build_features(part))[:, 1]
        if name == "val":
            thr, ev, n = ev_threshold(p, part["r_net"].to_numpy())
            report["threshold"] = {"thr": thr, "val_ev": ev, "val_n": n}
        mask = p >= thr
        report["filtered"][name] = _ev(part.filter(pl.Series(mask)))

    # Gate-2 style: filtered EV per regime on test
    p_test = model.predict_proba(build_features(test))[:, 1]
    kept = test.filter(pl.Series(p_test >= thr))
    report["by_regime_test"] = describe_by_regime(kept).to_dicts()
    report["by_family_test"] = (
        kept.group_by("family")
        .agg(
            pl.len().alias("n"),
            pl.col("r_net").fill_nan(None).mean().alias("ev"),
        )
        .sort("family")
        .to_dicts()
    )
    return report, model, thr


def train_stop_head(
    stop: pl.DataFrame,
    out_dir: Path,
    entry_model: object | None = None,
    entry_thr: float = 0.5,
) -> tuple[dict, object]:
    """P(survive) per rule + argmax policy vs fixed zone rule."""
    valid = stop.filter(pl.col("r_net").is_not_nan())
    train = valid.filter(pl.col("split") == "train")
    val = valid.filter(pl.col("split") == "val")
    test = valid.filter(pl.col("split") == "test")

    X_tr = build_features(train, extra_categoricals=(RULE_COL,))
    cat_names = [c for c in X_tr.columns if str(X_tr[c].dtype) == "category"]
    y_tr = (train["r_net"].to_numpy() > 0).astype(int)
    model = _fit_clf(X_tr, y_tr, cat_names)
    model.booster_.save_model(str(out_dir / "stop_head.txt"))

    report: dict = {"fixed_zone": {}, "policy": {}, "combined": {}}
    payoff = float(REFERENCE_TARGET)
    for name, part in (("train", train), ("val", val), ("test", test)):
        part = candidate_key(part)
        fixed = part.filter(pl.col(RULE_COL) == REFERENCE_RULE)
        report["fixed_zone"][name] = _ev(fixed)
        p = model.predict_proba(build_features(part, (RULE_COL,)))[:, 1]
        ev, n = policy_by_rule_choice(
            p,
            part[RULE_COL].to_numpy().astype(str),
            part["_cand"].to_numpy(),
            part["r_net"].to_numpy(),
            payoff=payoff,
        )
        report["policy"][name] = {"ev": ev, "n": n}
        if entry_model is not None:
            # combined: only candidates whose entry row passed the filter
            cand_keys = part.group_by("_cand").first()
            pe = entry_model.predict_proba(build_features(cand_keys))[:, 1]
            keep = cand_keys.filter(pl.Series(pe >= entry_thr))["_cand"]
            sub = part.filter(pl.col("_cand").is_in(keep))
            ev2, n2 = policy_by_rule_choice(
                model.predict_proba(build_features(sub, (RULE_COL,)))[:, 1],
                sub[RULE_COL].to_numpy().astype(str),
                sub["_cand"].to_numpy(),
                sub["r_net"].to_numpy(),
                payoff=payoff,
            )
            report["combined"][name] = {"ev": ev2, "n": n2}
    return report, model


def train_tp_head(entry: pl.DataFrame, out_dir: Path) -> dict:
    """E[r_net] regression cross-check."""
    from scipy.stats import spearmanr

    train = entry.filter(pl.col("split") == "train")
    X_tr = build_features(train)
    cat_names = [c for c in X_tr.columns if str(X_tr[c].dtype) == "category"]
    model = lgb.LGBMRegressor(**LGB_PARAMS)
    model.fit(X_tr, train["r_net"].to_numpy(), categorical_feature=cat_names)
    model.booster_.save_model(str(out_dir / "tp_head.txt"))

    report: dict = {}
    for name in ("val", "test"):
        part = entry.filter(pl.col("split") == name)
        pred = model.predict(build_features(part))
        r = part["r_net"].fill_nan(None).drop_nulls().to_numpy()
        pred_finite = pred[np.isfinite(part["r_net"].to_numpy())]
        rho = spearmanr(pred_finite, r).statistic
        top = part.filter(pl.Series(pred >= np.quantile(pred, 0.7)))
        report[name] = {
            "spearman": float(rho),
            "top30_ev": _ev(top)["ev"],
            "top30_n": top.height,
        }
    return report


def harden_policy(
    stop: pl.DataFrame, model: object, full_df: pl.DataFrame, table: dict
) -> dict:
    """Honest evaluation of the stop policy: baselines, CI, limits.

    - oracle ceiling and random-rule baseline on the same candidates;
    - paired bootstrap CI of policy vs fixed zone rule;
    - no-ML regime/side rule table (fit on train only, passed in);
    - limit executions on the policy-chosen (candidate, rule) pairs.
    """
    valid = stop.filter(pl.col("r_net").is_not_nan())
    train = valid.filter(pl.col("split") == "train")

    report: dict = {"rule_table": {}, "splits": {}, "limit_execution": {}}
    report["rule_table"]["table"] = {
        f"{r}|{s}": rule for (r, s), rule in table.items()
    }
    for name in ("train", "val", "test"):
        part = candidate_key(valid.filter(pl.col("split") == name))
        p = model.predict_proba(build_features(part, (RULE_COL,)))[:, 1]
        rules = part[RULE_COL].to_numpy().astype(str)
        keys_np = part["_cand"].to_numpy()
        r = part["r_net"].to_numpy()

        keys, pol_r = per_candidate_pick(p, keys_np, r)
        _, fix_r = fixed_rule_per_candidate(rules, keys_np, r, REFERENCE_RULE)
        boot = paired_bootstrap_diff(pol_r, fix_r)
        rand_ev, _, rand_n = random_rule_choice_ev(r, keys_np)
        orc_ev, orc_n = oracle_policy_ev(r, keys_np)

        tbl = apply_rule_table(part, table)
        report["splits"][name] = {
            "policy_vs_fixed": boot,
            "random_rule_ev": rand_ev,
            "random_n": rand_n,
            "oracle_ev": orc_ev,
            "oracle_n": orc_n,
            "rule_table": _ev(tbl),
        }

    # limit executions on policy-chosen pairs (test split)
    test = candidate_key(valid.filter(pl.col("split") == "test"))
    p_test = model.predict_proba(build_features(test, (RULE_COL,)))[:, 1]
    scored = test.with_columns(
        (pl.Series(p_test) * 2.0 - 1.0).alias("_score")
    ).sort(["_cand", "_score"])
    picks = (
        scored.group_by("_cand")
        .last()
        .select(["entry_idx", "side", "rule"])
    )
    for exec_ in ("limit:edge", "limit:mid"):
        rows = (
            full_df.filter(
                (pl.col("execution") == exec_)
                & (pl.col("target") == 2.0)
            )
            .join(picks, on=["entry_idx", "side", "rule"], how="inner")
        )
        filled = rows["filled"].cast(pl.Float64)
        r = rows["r_net"].fill_nan(None)
        payoff_rows = (r.fill_null(0.0) * filled).to_numpy()
        report["limit_execution"][exec_] = {
            "n_signals": rows.height,
            "fill_rate": float(filled.mean() or 0.0),
            "ev_per_signal": float(payoff_rows.mean() or 0.0),
            "ev_when_filled": float(
                r.filter(rows["filled"] & r.is_not_null()).mean() or 0.0
            ),
        }
    return report


def ml_upgrades(stop: pl.DataFrame, model: object, table: dict) -> dict:
    """Consensus gate + confidence sizing (B.3), calibrated on val.

    - consensus: trade only when the LGBM pick equals the rule-table
      pick for the candidate's (regime, side) cell;
    - table-fallback: on disagreement trade the table's rule instead;
    - sized policy: scale every policy trade by its stop-head
      confidence bucket (tertiles of the train pick probabilities).
    """
    stop = stop.filter(pl.col("r_net").is_not_nan())

    def picks(part: pl.DataFrame) -> pl.DataFrame:
        p = model.predict_proba(build_features(part, (RULE_COL,)))[:, 1]
        return (
            candidate_key(part)
            .with_columns(pl.Series("_p", p))
            .sort(["_cand", "_p"])
            .group_by("_cand")
            .last()
        )

    train_picks = picks(stop.filter(pl.col("split") == "train"))
    qs = np.quantile(
        train_picks["_p"].to_numpy(), [1.0 / 3.0, 2.0 / 3.0]
    ).tolist()
    table_map = {f"{r}|{s}": rule for (r, s), rule in table.items()}

    def tbl_rule_col(d: pl.DataFrame) -> pl.DataFrame:
        return d.with_columns(
            pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
            .replace_strict(
                list(table_map.keys()), list(table_map.values()),
                default=REFERENCE_RULE,
            )
            .alias("tbl_rule")
        )

    out: dict = {"p_tertiles_train": [float(q) for q in qs]}
    for name in ("val", "test"):
        d = tbl_rule_col(picks(stop.filter(pl.col("split") == name)))
        agree = d.filter(pl.col("rule") == pl.col("tbl_rule"))
        # table pick's realized result for the disagreement subset
        valid = stop.filter(pl.col("split") == name)
        tbl_rows = apply_rule_table(candidate_key(valid), table)
        d = d.join(
            tbl_rows.select("_cand", pl.col("r_net").alias("tbl_r")),
            on="_cand",
            how="left",
        )
        fallback_r = (
            d.filter(pl.col("rule") != pl.col("tbl_rule"))
            .select(pl.col("tbl_r").fill_null(pl.col("r_net")).alias("r"))
            .get_column("r")
            .to_numpy()
        )
        policy_r = d["r_net"].to_numpy()

        # confidence sizing: train-tertile buckets -> trade fraction
        w = np.select(
            [d["_p"].to_numpy() < qs[0], d["_p"].to_numpy() < qs[1]],
            [0.5, 0.75],
            default=1.0,
        )
        sized = w * policy_r

        # combine both: consensus subset, confidence-sized
        wa = np.select(
            [agree["_p"].to_numpy() < qs[0], agree["_p"].to_numpy() < qs[1]],
            [0.5, 0.75],
            default=1.0,
        )
        sized_agree = wa * agree["r_net"].to_numpy()

        out[name] = {
            "policy": {**_ev(d), **trade_curve_stats(policy_r)},
            "consensus": {**_ev(agree), **trade_curve_stats(agree["r_net"].to_numpy())},
            "consensus_sized": {
                "ev_weighted": float(np.nansum(sized_agree) / np.sum(wa)),
                "n": agree.height,
                **trade_curve_stats(sized_agree),
            },
            "table_fallback": trade_curve_stats(
                np.concatenate([
                    agree["r_net"].to_numpy(),
                    fallback_r[np.isfinite(fallback_r)],
                ])
            )
            | {"ev": float(np.nanmean(np.concatenate([
                agree["r_net"].to_numpy(),
                fallback_r[np.isfinite(fallback_r)],
            ])))},
            "sized_policy": {
                "ev_weighted": float(np.nansum(sized) / np.sum(w)),
                **trade_curve_stats(sized),
            },
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/mtf_dataset/BTCUSDT_1h.parquet"),
    )
    ap.add_argument("--out", type=Path, default=Path("data/mtf_model"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pl.read_parquet(args.dataset)
    entry = select_entry_rows(df)
    stop = select_stop_rows(df)
    print(f"entry rows: {entry.height}, stop rows: {stop.height}")

    entry_report, entry_model, entry_thr = train_entry_head(entry, args.out)
    stop_report, stop_model = train_stop_head(
        stop, args.out, entry_model=entry_model, entry_thr=entry_thr
    )
    table = fit_rule_table(
        stop.filter(pl.col("r_net").is_not_nan() & (pl.col("split") == "train"))
    )
    report = {
        "dataset": str(args.dataset),
        "entry_head": entry_report,
        "stop_head": stop_report,
        "harden_policy": harden_policy(stop, stop_model, df, table),
        "ml_upgrade": ml_upgrades(stop, stop_model, table),
        "tp_head": train_tp_head(entry, args.out),
    }
    (args.out / "report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
