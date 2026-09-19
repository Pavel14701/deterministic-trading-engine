"""Unit tests for the Stage B model-tower helpers (ai.mtf_model)."""

import numpy as np
import polars as pl
import pytest

from engine.mtf_model import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    apply_rule_table,
    bucketed_sharpe,
    build_features,
    describe_by_regime,
    ev_threshold,
    fit_rule_table,
    fixed_rule_per_candidate,
    oracle_policy_ev,
    paired_bootstrap_diff,
    per_candidate_pick,
    per_trade_sharpe,
    policy_by_rule_choice,
    random_rule_choice_ev,
    select_entry_rows,
    select_stop_rows,
    trade_curve_stats,
)


def _toy_df() -> pl.DataFrame:
    """Two candidates x 2 executions x 2 rules x 1 target."""
    rows = []
    for idx, family, rule, exec_, split, r in [
        (0, "fvg", "zone:1.0", "market", "train", 2.0),
        (0, "fvg", "zone:1.0", "limit:edge", "train", 2.0),
        (0, "fvg", "atr:14", "market", "train", -1.0),
        (0, "fvg", "atr:14", "limit:edge", "train", -1.0),
        (1, "sweep", "zone:1.0", "market", "val", -1.0),
        (1, "sweep", "zone:1.0", "limit:edge", "val", -1.0),
        (1, "sweep", "atr:14", "market", "test", 2.0),
        (1, "sweep", "atr:14", "limit:edge", "test", 2.0),
    ]:
        rows.append(
            dict(
                entry_idx=idx,
                side="long",
                family=family,
                atr_pct=0.3,
                zone_height_atr=1.0,
                zone_dist_atr=0.2,
                z50=0.1,
                slope50=0.01,
                vol_pct=0.5,
                bbw_pct=0.4,
                regime_dir="up",
                ob_trend="up",
                ob_structure="normal",
                overlap=False,
                d_avsl=1.0,
                d_avsr=2.0,
                d_hilo_l=0.5,
                d_hilo_s=0.5,
                d_st=0.7,
                d_bb_l=0.9,
                d_bb_u=1.1,
                h1_trend=1.0,
                h1_slope=0.0,
                h1_below=1.0,
                h1_above=2.0,
                h2_trend=1.0,
                h2_slope=0.0,
                h2_below=1.0,
                h2_above=2.0,
                ltf_impulse=0.3,
                ltf_vol_z=0.2,
                execution=exec_,
                rule=rule,
                target=2.0,
                filled=True,
                r_net=r,
                split=split,
            )
        )
    return pl.DataFrame(rows)


def test_select_entry_rows_filters_reference_config() -> None:
    df = select_entry_rows(_toy_df())
    assert df.height == 2
    assert set(df["execution"]) == {"market"}
    assert set(df["rule"]) == {"zone:1.0"}


def test_select_stop_rows_keeps_all_rules_one_execution() -> None:
    df = select_stop_rows(_toy_df())
    assert df.height == 4
    assert set(df["rule"]) == {"zone:1.0", "atr:14"}
    assert set(df["execution"]) == {"market"}


def test_build_features_columns_and_dtypes() -> None:
    feats = build_features(_toy_df())
    assert feats.shape[0] == _toy_df().height
    for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        assert name in feats.columns
    assert str(feats["family"].dtype) == "category"
    assert str(feats["atr_pct"].dtype) in ("float32", "float64")


def test_ev_threshold_picks_profitable_cut() -> None:
    # top-probability trades are the profitable ones
    p = np.array([0.9, 0.85, 0.8, 0.3, 0.2])
    r = np.array([2.0, 2.0, 2.0, -1.0, -1.0])
    thr, ev, n = ev_threshold(p, r, grid_size=5)
    # the optimal cut keeps exactly the three profitable trades; the
    # threshold is a probability quantile inside (0.3, 0.8]
    assert 0.3 < thr <= 0.8
    assert ev == pytest.approx(2.0)
    assert n == 3


def test_ev_threshold_empty_input() -> None:
    thr, ev, n = ev_threshold(np.array([]), np.array([]))
    assert n == 0
    assert thr == -np.inf
    assert ev == 0.0


def test_describe_by_regime_groups() -> None:
    df = _toy_df().filter(pl.col("execution") == "market")
    table = describe_by_regime(df)
    assert table.height == 1
    row = table.row(0, named=True)
    assert row["regime_dir"] == "up"
    assert row["n"] == 4
    assert row["ev"] == pytest.approx((2.0 - 1.0 + 2.0 - 1.0) / 4)


def test_candidate_key_separates_sides_on_same_bar() -> None:
    from engine.mtf_model import candidate_key

    df = pl.DataFrame(
        {
            "entry_idx": [5, 5],
            "side": ["long", "short"],
            "rule": ["zone:1.0", "zone:1.0"],
            "r_net": [2.0, -1.0],
        }
    )
    keyed = candidate_key(df)
    assert keyed["_cand"].to_list() == ["5_long", "5_short"]
    # grouping by entry_idx alone would merge the sides into one
    # phantom candidate - the composite key must keep them separate
    p = np.array([0.9, 0.9])
    keys, out = per_candidate_pick(
        p, keyed["_cand"].to_numpy(), keyed["r_net"].to_numpy()
    )
    assert keys == ["5_long", "5_short"]
    assert out.tolist() == pytest.approx([2.0, -1.0])


def test_bootstrap_aligns_composite_keys_with_different_rules() -> None:
    # the short side's zone rule is invalid (NaN) and its only valid
    # rule is anchor:st: paired diff must drop that side (no finite
    # pair), not pair it against an unrelated outcome
    rules = np.array(["zone:1.0", "zone:1.0", "anchor:st:0.5", "anchor:st:0.5"])
    keys = np.array(["5_long", "5_short", "5_long", "5_short"])
    r = np.array([2.0, np.nan, np.nan, 1.0])
    _, pol = per_candidate_pick(
        np.array([0.9, 0.2, 0.0, 0.8]), keys, r, payoff=2.0
    )
    _, fix = fixed_rule_per_candidate(rules, keys, r, "zone:1.0")
    assert fix[0] == pytest.approx(2.0) and np.isnan(fix[1])
    res = paired_bootstrap_diff(pol, fix, n_boot=100)
    # only "5_long" has both picks finite: 2.0 - 2.0 = 0
    assert res["n"] == 1
    assert res["diff"] == pytest.approx(0.0)


def test_trade_curve_stats_known_sequence() -> None:
    r = np.array([1.0, -1.0, 1.0, 1.0])
    s = trade_curve_stats(r)
    assert s["n"] == 4
    # equity [1, 0, 1, 2] -> max drawdown 1R
    assert s["max_dd_r"] == pytest.approx(1.0)
    # gross wins 3 / gross losses 1
    assert s["profit_factor"] == pytest.approx(3.0)
    # t-stat: mean 0.25 / (std*2) ... computed directly
    std = r.std(ddof=1)
    assert s["t_stat"] == pytest.approx(r.mean() / std * np.sqrt(4))


def test_trade_curve_stats_edge_cases() -> None:
    empty = trade_curve_stats(np.array([]))
    assert empty["n"] == 0 and empty["max_dd_r"] == 0.0
    all_win = trade_curve_stats(np.array([1.0, 2.0]))
    assert all_win["profit_factor"] == float("inf")
    assert all_win["max_dd_r"] == 0.0
    # NaN rows are ignored
    assert trade_curve_stats(np.array([np.nan, 1.0]))["n"] == 1


def test_trade_curve_stats_dd_depends_on_order() -> None:
    """max_dd_r is a chronological statistic: same multiset of trades in
    a different order gives a different drawdown.  Callers must sort by
    trade time before pooling (d13c/wf_ab pool per asset then fold)."""
    loss_first = np.array([-2.0, 1.0, 1.0, 1.0, 1.0])
    loss_in_middle = np.array([1.0, 1.0, -2.0, 1.0, 1.0])
    assert trade_curve_stats(loss_first)["max_dd_r"] == pytest.approx(0.0)
    assert trade_curve_stats(loss_in_middle)["max_dd_r"] == pytest.approx(2.0)
    # same trades, same mean - only the curve shape differs
    assert loss_first.mean() == pytest.approx(loss_in_middle.mean())


def test_t_stat_inflated_by_pooled_correlated_copies() -> None:
    """t_stat assumes independent trades.  Pooling k identical copies
    (proxy for correlated assets / overlapping trades) multiplies it by
    ~sqrt(k) without adding information - why t=14 is NOT a Sharpe."""
    rng = np.random.default_rng(7)
    r = rng.normal(0.1, 1.0, size=200)
    t1 = trade_curve_stats(r)["t_stat"]
    r3 = np.tile(r, 3)
    t3 = trade_curve_stats(r3)["t_stat"]
    # exact: same mean/std up to ddof weighting, n scaled by 3
    assert t3 == pytest.approx(
        r3.mean() / r3.std(ddof=1) * np.sqrt(r3.size), rel=1e-12)
    assert t3 / t1 == pytest.approx(np.sqrt(3), rel=1e-2)


def test_per_trade_sharpe_known_values() -> None:
    r = np.array([2.0, -1.0, 2.0, -1.0, 2.0, -1.0])
    std = r.std(ddof=1)
    assert per_trade_sharpe(r) == pytest.approx(r.mean() / std)
    assert per_trade_sharpe(np.array([1.0])) == 0.0
    assert per_trade_sharpe(np.array([2.0, 2.0])) == 0.0  # zero dispersion
    assert per_trade_sharpe(np.array([np.nan, 1.0, 3.0])) == pytest.approx(
        np.array([1.0, 3.0]).mean() / np.array([1.0, 3.0]).std(ddof=1))


def test_bucketed_sharpe_known_series() -> None:
    """Two weeks, 2R per week, zero dispersion -> std 0 -> Sharpe 0."""
    day = 86_400_000
    ts = np.array([0, 1 * day, 8 * day, 9 * day], dtype=float)
    r = np.array([1.0, 1.0, 1.0, 1.0])
    assert bucketed_sharpe(r, ts) == 0.0


def test_bucketed_sharpe_computes_from_weekly_sums() -> None:
    day = 86_400_000
    # week 0: +3R total, week 1: -1R, week 2: +2R, week 4: +2R
    ts = np.array([0, 1 * day, 8 * day, 16 * day, 30 * day], dtype=float)
    r = np.array([1.0, 2.0, -1.0, 2.0, 2.0])
    s = bucketed_sharpe(r, ts)
    weekly = np.array([3.0, -1.0, 2.0, 0.0, 2.0])  # week 3 flat = 0
    expected = weekly.mean() / weekly.std(ddof=1) * np.sqrt(365.25 / 7)
    assert s == pytest.approx(expected)


def test_bucketed_sharpe_unsorted_input_and_edges() -> None:
    day = 86_400_000
    ts = np.array([16 * day, 0.0, 8 * day], dtype=float)
    r = np.array([2.0, 3.0, -1.0])
    s_sorted = bucketed_sharpe(r, ts)
    s_unsorted = bucketed_sharpe(r[::-1], ts[::-1])
    # sums per bucket are order-independent, so Sharpe must match
    assert s_unsorted == pytest.approx(s_sorted)
    assert s_sorted != 0.0
    # degenerate inputs
    assert bucketed_sharpe(np.array([1.0]), np.array([0.0])) == 0.0
    assert bucketed_sharpe(np.array([np.nan, 1.0, 2.0]),
                           np.array([0.0, 0.0, 7 * 86_400_000.0])) != 0.0


def test_policy_skips_invalid_rows_and_picks_best_rule() -> None:
    # candidate 0: zone valid (+2), atr invalid (NaN); candidate 1: both valid
    p = np.array([0.9, 0.8, np.nan, 0.4, 0.6, 0.5])
    rules = np.array(["zone:1.0", "atr:14", "zone:1.0", "atr:14", "zone:1.0", "atr:14"])
    keys = np.array([0, 0, 1, 1, 1, 1])
    r = np.array([2.0, np.nan, np.nan, -1.0, -1.0, 2.0])
    ev, n = policy_by_rule_choice(p, rules, keys, r, payoff=2.0)
    # candidate 0 -> zone (+2); candidate 1 -> atr (score 0.4*2-0.6=0.2
    # beats zone 0.6*2-0.4=0.8? no: zone wins -> -1)
    assert n == 2
    assert ev == pytest.approx((2.0 + -1.0) / 2)


def test_per_candidate_pick_matches_policy() -> None:
    p = np.array([0.9, 0.8, 0.4, 0.6])
    keys = np.array([0, 0, 1, 1])
    r = np.array([2.0, 1.0, -1.0, 2.0])
    k, out = per_candidate_pick(p, keys, r, payoff=2.0)
    assert k == [0, 1]
    # cand 0: zone score 0.8 vs atr 0.4 -> +2; cand 1: zone 0.2 vs atr 0.8 -> +2
    assert out.tolist() == pytest.approx([2.0, 2.0])


def test_fixed_rule_per_candidate() -> None:
    rules = np.array(["zone:1.0", "atr:14", "atr:14"])
    keys = np.array([0, 0, 1])
    r = np.array([2.0, -1.0, 3.0])
    k, out = fixed_rule_per_candidate(rules, keys, r, "atr:14")
    assert k == [0, 1]
    assert out.tolist() == pytest.approx([-1.0, 3.0])


def test_paired_bootstrap_diff_positive() -> None:
    rng = np.random.default_rng(3)
    a = rng.normal(0.5, 1.0, 300)
    b = rng.normal(0.0, 1.0, 300)
    res = paired_bootstrap_diff(a, b, n_boot=500)
    assert res["diff"] == pytest.approx(float((a - b).mean()))
    assert res["lo"] > 0
    assert res["p_le0"] < 0.05


def test_oracle_and_random_baselines() -> None:
    r = np.array([2.0, -1.0, -1.0, 2.0])
    keys = np.array([0, 0, 1, 1])
    ev, n = oracle_policy_ev(r, keys)
    assert ev == pytest.approx(2.0)
    assert n == 2
    rand_ev, _, rand_n = random_rule_choice_ev(r, keys)
    assert rand_ev == pytest.approx(0.5)
    assert rand_n == 2


def test_rule_table_fit_and_apply() -> None:
    df = _toy_df().filter(pl.col("execution") == "market")
    # force: in "up" regime atr:14 wins for this toy set
    table = fit_rule_table(df, min_trades=1)
    assert set(table) == {("up", "long")}
    chosen = apply_rule_table(df, table)
    # one rule wins for the single (regime, side) cell; both candidates follow it
    assert chosen.height == 2
    assert chosen["rule"].n_unique() == 1
