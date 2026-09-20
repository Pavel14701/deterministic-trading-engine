"""Stage B model towers over the MTF dataset.

The dataset has one row per (candidate, execution, rule, target).  The
towers follow TZ-11:

- **entry head** - P(r_net > 0) for a reference config (zone stop,
  2R target, market), used as an entry filter with an EV-calibrated
  probability threshold;
- **stop head** - P(survive) per stop rule, used as an argmax policy
  over rules;
- **tp head** - E[r_net] regression, a cross-check on EV estimates.

This module keeps only pure, testable helpers (feature assembly,
threshold calibration, regime reporting); the LightGBM training lives
in ``scripts/train_mtf_model.py``.
"""

from __future__ import annotations

import numpy as np
import polars as pl


REFERENCE_EXECUTION = "market"
REFERENCE_RULE = "zone:1.0"
REFERENCE_TARGET = 2.0

#: numeric features available at decision time (causal by construction)
NUMERIC_FEATURES = [
    "atr_pct",
    "zone_height_atr",
    "zone_dist_atr",
    "z50",
    "slope50",
    "vol_pct",
    "bbw_pct",
    "d_avsl",
    "d_avsr",
    "d_hilo_l",
    "d_hilo_s",
    "d_st",
    "d_bb_l",
    "d_bb_u",
    "h1_trend",
    "h1_slope",
    "h1_below",
    "h1_above",
    "h2_trend",
    "h2_slope",
    "h2_below",
    "h2_above",
    "ltf_impulse",
    "ltf_vol_z",
]

#: categorical features (pandas ``category`` dtype, LightGBM-native)
CATEGORICAL_FEATURES = [
    "side",
    "family",
    "regime_dir",
    "ob_trend",
    "ob_structure",
    "overlap",
]


def candidate_key(df: pl.DataFrame) -> pl.DataFrame:
    """Add the composite candidate key column ``_cand``.

    Long and short candidates can share the same bar (``entry_idx``);
    every per-candidate policy must group on this key, never on
    ``entry_idx`` alone - grouping by bar merges the two sides into one
    phantom candidate and corrupts policy selection.
    """
    return df.with_columns(
        pl.format("{}_{}", pl.col("entry_idx"), pl.col("side")).alias("_cand")
    )


def select_entry_rows(
    df: pl.DataFrame,
    execution: str = REFERENCE_EXECUTION,
    rule: str = REFERENCE_RULE,
    target: float = REFERENCE_TARGET,
) -> pl.DataFrame:
    """One tradeable row per candidate for the reference config.

    Rows with non-finite ``r_net`` are not tradeable at this config
    (e.g. zone stops on zoneless candidates) and are dropped.
    """
    return df.filter(
        (pl.col("execution") == execution)
        & (pl.col("rule") == rule)
        & (pl.col("target") == target)
        & pl.col("r_net").is_not_nan()
    )


def select_stop_rows(
    df: pl.DataFrame,
    execution: str = REFERENCE_EXECUTION,
    target: float = REFERENCE_TARGET,
) -> pl.DataFrame:
    """All stop-rule rows at one target/execution (stop-head input)."""
    return df.filter(
        (pl.col("execution") == execution) & (pl.col("target") == target)
    )


def build_features(
    df: pl.DataFrame,
    extra_categoricals: tuple[str, ...] = (),
) -> "pd.DataFrame":  # type: ignore[name-defined]  # noqa: F821
    """Assemble the LightGBM feature frame (pandas, category dtype).

    NaN numerics are passed through - LightGBM handles them natively.
    """
    import pandas as pd  # local import: keeps the module import-light

    cats = [*CATEGORICAL_FEATURES, *extra_categoricals]
    out = pd.DataFrame(index=np.arange(df.height))
    for name in NUMERIC_FEATURES:
        out[name] = df[name].to_numpy().astype("float32")
    for name in cats:
        out[name] = pd.Categorical(df[name].to_numpy().astype(str))
    return out


def ev_threshold(
    p: np.ndarray,
    r_net: np.ndarray,
    grid_size: int = 19,
) -> tuple[float, float, int]:
    """Calibrate the entry-probability threshold on validation data.

    Scans probability quantiles and returns ``(threshold, ev, n)`` for
    the cut with the best mean net EV among trades with ``p >= thr``.
    Ties resolve toward the smaller threshold (more trades).  The
    threshold ``-inf`` (all trades) participates as the grid floor.
    """
    p = np.asarray(p, dtype=np.float64)
    r = np.asarray(r_net, dtype=np.float64)
    finite = np.isfinite(r)
    p, r = p[finite], r[finite]
    if p.size == 0:
        return (-np.inf, 0.0, 0)
    quantiles = np.quantile(
        p, np.linspace(0.0, 1.0, grid_size + 2)[:-1]
    )  # 0.0..0.95
    candidates = np.concatenate([[-np.inf], quantiles])
    best = (-np.inf, 0.0, 0)
    for thr in candidates:
        mask = p >= thr
        n = int(mask.sum())
        if n == 0:
            continue
        ev = float(r[mask].mean())
        if ev > best[1] + 1e-12:
            best = (float(thr), ev, n)
    return best


def describe_by_regime(df: pl.DataFrame) -> pl.DataFrame:
    """Per-regime count / EV / win-rate table (Gate-2 style)."""
    return (
        df.with_columns(pl.col("r_net").fill_nan(None))
        .group_by("regime_dir")
        .agg(
            pl.len().alias("n"),
            pl.col("r_net").mean().alias("ev"),
            (pl.col("r_net") > 0).mean().alias("win_rate"),
        )
        .sort("regime_dir")
    )


def oracle_policy_ev(
    r_net: np.ndarray,
    group_keys: np.ndarray,
) -> tuple[float, int]:
    """Per-candidate best-rule ceiling (max realized net R)."""
    import collections

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, key in enumerate(group_keys):
        if np.isfinite(r_net[i]):
            groups[key].append(i)
    best = [float(np.max(r_net[idxs])) for idxs in groups.values()]
    if not best:
        return (0.0, 0)
    return (float(np.mean(best)), len(best))


def paired_bootstrap_diff(
    a: np.ndarray,
    b: np.ndarray,
    n_boot: int = 2000,
    seed: int = 7,
) -> dict[str, float]:
    """Bootstrap CI for ``mean(a) - mean(b)`` over paired samples.

    ``a``/``b`` are per-candidate realized net R of two policies on the
    same candidate set (NaN pairs dropped).  Returns mean diff, the
    2.5/97.5 percentiles and the fraction of bootstrap draws with
    diff <= 0 (a one-sided pseudo-p-value).
    """
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    n = a.size
    if n == 0:
        return {"diff": 0.0, "lo": 0.0, "hi": 0.0, "p_le0": 1.0, "n": 0}
    diffs = a - b
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = diffs[idx].mean(axis=1)
    return {
        "diff": float(diffs.mean()),
        "lo": float(np.quantile(boot, 0.025)),
        "hi": float(np.quantile(boot, 0.975)),
        "p_le0": float((boot <= 0).mean()),
        "n": int(n),
    }


def random_rule_choice_ev(
    r_net: np.ndarray,
    group_keys: np.ndarray,
    n_boot: int = 200,
    seed: int = 7,
) -> tuple[float, float, int]:
    """Mean +/- std of the expected EV of a uniformly random rule pick.

    The expectation of a uniform pick is the per-candidate mean over
    valid rules - deterministic - so this returns ``(ev, 0.0, n)``;
    kept as an explicit baseline for reporting symmetry.
    """
    import collections

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, key in enumerate(group_keys):
        if np.isfinite(r_net[i]):
            groups[key].append(i)
    if not groups:
        return (0.0, 0.0, 0)
    means = [float(np.mean(r_net[idxs])) for idxs in groups.values()]
    return (float(np.mean(means)), 0.0, len(means))


def fit_rule_table(
    train: pl.DataFrame,
    min_trades: int = 30,
    fallback: str = REFERENCE_RULE,
) -> dict[tuple[str, str], str]:
    """Best rule per (regime_dir, side) by train EV with a floor.

    Falls back to ``fallback`` (zone rule) when no rule clears
    ``min_trades`` or the best EV is negative.
    """
    table: dict[tuple[str, str], str] = {}
    stats = (
        train.with_columns(pl.col("r_net").fill_nan(None))
        .group_by(["regime_dir", "side", "rule"])
        .agg(pl.len().alias("n"), pl.col("r_net").mean().alias("ev"))
        .filter(pl.col("ev").is_not_nan())
    )
    for (regime, side), sub in stats.group_by(
        ["regime_dir", "side"], maintain_order=True
    ):
        sub = sub.sort("ev", descending=True)
        top = sub.row(0, named=True)
        if top["n"] >= min_trades and top["ev"] > 0:
            table[str(regime), str(side)] = str(top["rule"])
        else:
            table[str(regime), str(side)] = fallback
    return table


def apply_rule_table(
    df: pl.DataFrame,
    table: dict[tuple[str, str], str],
) -> pl.DataFrame:
    """Rows where the candidate's regime/side matches its table rule."""
    mapping = {f"{r}|{s}": rule for (r, s), rule in table.items()}
    key = pl.format("{}|{}", pl.col("regime_dir"), pl.col("side"))
    chosen = key.replace_strict(
        list(mapping.keys()), list(mapping.values()), default=None
    )
    return df.filter(chosen == pl.col("rule"))


def policy_by_rule_choice(
    p_survive: np.ndarray,
    rules: np.ndarray,
    group_keys: np.ndarray,
    r_net: np.ndarray,
    payoff: float = 2.0,
) -> tuple[float, int]:
    """Stop-head policy EV: pick the max-``p * payoff - (1 - p)`` rule.

    Pure helper: ``p_survive`` are per-row stop-head probabilities,
    ``group_keys`` tie rows of the same candidate (e.g. entry_idx),
    ``payoff`` is the TP win size in R (the target multiple).  Rows
    with non-finite ``r_net`` (rule not applicable for that candidate)
    are excluded from both scoring and the realized average.  Returns
    ``(ev, n_groups)`` of the chosen-rule realized net EV.
    """
    import collections

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, key in enumerate(group_keys):
        if np.isfinite(r_net[i]):
            groups[key].append(i)
    chosen: list[float] = []
    for idxs in groups.values():
        best_i, best_score = idxs[0], -np.inf
        for i in idxs:
            p = float(p_survive[i])
            score = p * payoff - (1.0 - p)
            if score > best_score:
                best_i, best_score = i, score
        chosen.append(float(r_net[best_i]))
    if not chosen:
        return (0.0, 0)
    return (float(np.mean(chosen)), len(chosen))


def per_candidate_pick(
    p_survive: np.ndarray,
    group_keys: np.ndarray,
    r_net: np.ndarray,
    payoff: float = 2.0,
) -> tuple[list[str], np.ndarray]:
    """Realized net R of the stop-head argmax pick per candidate.

    Returns ``(keys, r)`` sorted by key; NaN candidates are dropped.
    """
    import collections

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, key in enumerate(group_keys):
        if np.isfinite(r_net[i]):
            groups[key].append(i)
    keys = sorted(groups)
    out = np.full(len(keys), np.nan)
    for j, key in enumerate(keys):
        idxs = groups[key]
        best_i = max(
            idxs,
            key=lambda i: float(p_survive[i]) * payoff - (1.0 - p_survive[i]),
        )
        out[j] = float(r_net[best_i])
    return keys, out


def fixed_rule_per_candidate(
    rules: np.ndarray,
    group_keys: np.ndarray,
    r_net: np.ndarray,
    rule: str,
) -> tuple[list[str], np.ndarray]:
    """Realized net R of one fixed rule per candidate (NaN if absent)."""
    import collections

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, key in enumerate(group_keys):
        if np.isfinite(r_net[i]):
            groups[key].append(i)
    keys = sorted(groups)
    out = np.full(len(keys), np.nan)
    for j, key in enumerate(keys):
        for i in groups[key]:
            if str(rules[i]) == rule:
                out[j] = float(r_net[i])
                break
    return keys, out

