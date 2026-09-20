"""Tests for the extended OB pipeline: full-field features, causal
per-bar OB features, chronological split integrity and the enriched
OB encoder passthrough (TZ-06)."""

from datetime import datetime, timezone

import numpy as np
import polars as pl

from engine.features.indicators import compute_atr, compute_ob_features
from engine.infra.datatypes import OrderBlock


def _mk_df(n: int = 64) -> pl.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 0.2, n))
    return pl.DataFrame(
        {
            "ts": np.arange(n, dtype=np.int64) * 60_000,
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": np.full(n, 10.0),
        }
    )


def _mk_ob(**kw) -> OrderBlock:
    d = datetime(2024, 1, 1, tzinfo=timezone.utc)
    defaults = dict(
        id=0,
        block_type="demand",
        start=d,
        break_=d,
        retest=d,
        zone_low=99.0,
        zone_high=100.0,
        strength=2.0,
        structure_label="fresh",
        trend_direction="up",
        start_idx=10,
        end_idx=40,
        timeframe="5m",
        confirm_idx=12,
        retest_idx=-1,
        zone_height_atr=1.5,
    )
    defaults.update(kw)
    return OrderBlock(**defaults)


def test_ob_features_causal_no_lookahead():
    df = _mk_df(64)
    atr = compute_atr(df)
    ob = _mk_ob(confirm_idx=12, start_idx=10, end_idx=40)
    feats = compute_ob_features(df, [ob], atr)
    # nothing known before confirm_idx
    assert np.isinf(feats["dist_demand"][:12]).all()
    assert feats["count_demand"][:12].sum() == 0
    # known between confirm and break
    assert np.isfinite(feats["dist_demand"][12:41]).all()
    # broken flag only after the break
    assert feats["broken_demand"][41:].all()
    assert not feats["broken_demand"][:41].any()


def test_ob_features_all_fields_present_and_bounded():
    df = _mk_df(64)
    atr = compute_atr(df)
    obs = [
        _mk_ob(id=0, block_type="demand", confirm_idx=12, end_idx=40),
        _mk_ob(
            id=1,
            block_type="supply",
            confirm_idx=20,
            end_idx=50,
            zone_low=101.0,
            zone_high=102.0,
        ),
    ]
    feats = compute_ob_features(df, obs, atr)
    expected = {
        "dist_supply",
        "dist_demand",
        "in_zone_supply",
        "in_zone_demand",
        "strength_supply",
        "strength_demand",
        "height_supply",
        "height_demand",
        "age_supply",
        "age_demand",
        "retested_supply",
        "retested_demand",
        "count_supply",
        "count_demand",
        "broken_supply",
        "broken_demand",
    }
    assert set(feats) == expected
    for name, arr in feats.items():
        assert arr.dtype == np.float32
        assert np.isfinite(arr[np.isfinite(arr)]).all() or name.startswith(
            "dist"
        )
    # count is capped and scaled to [0, 1]
    assert feats["count_supply"].max() <= 1.0
    # retested flag propagates from retest_idx
    ob = _mk_ob(confirm_idx=12, end_idx=40, retest_idx=25)
    feats2 = compute_ob_features(df, [ob], atr)
    assert feats2["retested_demand"][:25].sum() == 0
    assert feats2["retested_demand"][26:41].all()


def test_split_chronological_no_overlap_and_context():
    import sys

    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.datasets.okx import split_chronological

    n = 4000
    feat = _mk_df(n)
    labels = pl.DataFrame(
        {"action": np.zeros(n, dtype=int), "outcome": np.zeros(n)}
    )
    ob = _mk_ob(start_idx=100, end_idx=3000, confirm_idx=102)
    segs = split_chronological(feat, labels, [ob], seq_len=128)
    train, val, test = segs["train"], segs["val"], segs["test"]
    # label ranges do not overlap and respect the gap
    t_end = train[3]["label_end"]
    v_start, v_end = val[3]["label_start"], val[3]["label_end"]
    s_start = test[3]["label_start"]
    assert t_end <= v_start
    assert v_end <= s_start
    # val/test context labels are the ignore index
    ctx = val[3]["n_context"]
    assert ctx > 0
    assert (val[1]["action"][:ctx] == -100).all()
    assert (val[1]["action"][ctx:] != -100).all()
    assert (test[1]["action"][: test[3]["n_context"]] == -100).all()
    # OB rebased into each segment
    assert val[2][0].start_idx >= 0


def test_split_short_history_raises_clear_error():
    import pytest

    from engine.datasets.okx import split_chronological

    # 600 bars used to overflow the frame (IndexError) because the gap was
    # added on top of the fractions; it must now fail with a clear
    # "not enough bars" error instead.
    n = 600
    feat = _mk_df(n)
    labels = pl.DataFrame(
        {"action": np.zeros(n, dtype=int), "outcome": np.zeros(n)}
    )
    with pytest.raises(RuntimeError, match="not enough bars"):
        split_chronological(feat, labels, [], seq_len=128)


def test_split_segments_fit_frame_and_reserve_gaps():
    from engine.datasets.okx import split_chronological

    n, seq_len = 1200, 128
    feat = _mk_df(n)
    labels = pl.DataFrame(
        {"action": np.zeros(n, dtype=int), "outcome": np.zeros(n)}
    )
    segs = split_chronological(feat, labels, [], seq_len=seq_len)
    train, val, test = segs["train"], segs["val"], segs["test"]
    # every segment stays inside the frame
    for seg in (train, val, test):
        info = seg[3]
        assert info["ts_start"] == int(feat["ts"][info["file_start"]])
        assert info["label_end"] <= n
        assert info["ts_end"] == int(feat["ts"][info["label_end"] - 1])
    # labelled ranges never overlap and both gaps are excluded
    assert train[3]["label_end"] + seq_len == val[3]["label_start"]
    assert val[3]["label_end"] + seq_len == test[3]["label_start"]
    assert test[3]["label_end"] == n


def test_htf_ob_mapping_is_causal_and_drops_future_blocks():
    import sys

    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.datasets.okx import map_htf_ob_indices

    base_ms, htf_ms = 60_000, 300_000
    base_ts = np.arange(60, dtype=np.int64) * base_ms  # 1m grid
    hts = (np.arange(1, 13, dtype=np.int64)) * htf_ms  # 5m grid, aligned
    # an HTF bar opening at hts[k] closes at hts[k] + htf_ms; the base bar
    # that may first use it opens at hts[k] + htf_ms - base_ms
    ob = _mk_ob(start_idx=2, confirm_idx=3, end_idx=6, retest_idx=4)
    mapped = map_htf_ob_indices([ob], hts, base_ts, htf_ms, base_ms)
    assert len(mapped) == 1
    m = mapped[0]
    assert m.confirm_idx == (hts[3] + htf_ms - base_ms) // base_ms
    assert m.start_idx == (hts[2] + htf_ms - base_ms) // base_ms
    assert m.end_idx == (hts[6] + htf_ms - base_ms) // base_ms
    assert m.retest_idx == (hts[4] + htf_ms - base_ms) // base_ms
    assert m.start_idx <= m.confirm_idx <= m.end_idx
    assert m.confirm_idx < len(base_ts)
    # a block confirmed by the last HTF bar only becomes known after the
    # base range ends -> dropped, never clamped onto the final base bar
    future = _mk_ob(start_idx=10, confirm_idx=11, end_idx=11)
    assert map_htf_ob_indices([future], hts, base_ts, htf_ms, base_ms) == []


def test_htf_ob_mapping_never_precedes_htf_close():
    import sys

    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.datasets.okx import map_htf_ob_indices

    base_ms, htf_ms = 60_000, 900_000  # 1m base, 15m HTF
    base_ts = np.arange(200, dtype=np.int64) * base_ms
    hts = np.arange(1, 14, dtype=np.int64) * htf_ms
    mapped = map_htf_ob_indices(
        [_mk_ob(start_idx=5, confirm_idx=6, end_idx=8)],
        hts,
        base_ts,
        htf_ms,
        base_ms,
    )
    m = mapped[0]
    # the confirmation of HTF bar 6 is only usable from the base bar whose
    # close equals that HTF bar's close
    assert base_ts[m.confirm_idx] == hts[6] + htf_ms - base_ms


def test_ob_lookup_matches_linear_scan():
    """The indexed decision search must equal the brute-force scan.

    Randomized equivalence check: for many bar queries the index has to
    return exactly the block ``_find_entry_ob`` would have returned,
    including the ``end_idx <= bar`` eligibility rule, the "contains bar
    high or low" rule and the structure/trend filters.

    """
    from engine.features.indicators import _find_entry_ob, _OBLookup

    rng = np.random.default_rng(11)
    n_bars = 60
    obs = []
    for k in range(40):
        lo = float(rng.uniform(90, 110))
        obs.append(
            _mk_ob(
                id=k,
                block_type="demand" if k % 2 else "supply",
                zone_low=lo,
                zone_high=lo + float(rng.uniform(0.1, 3.0)),
                start_idx=int(rng.integers(0, 30)),
                end_idx=int(rng.integers(-1, 55)),
                confirm_idx=0,
                trend_direction=str(rng.choice(["up", "down", "flat"])),
                structure_label=str(rng.choice(["fresh", "retested"])),
            )
        )
    closes = 100 + np.cumsum(rng.normal(0, 0.6, n_bars))
    highs = closes + rng.uniform(0.05, 0.8, n_bars)
    lows = closes - rng.uniform(0.05, 0.8, n_bars)
    for trend_filter in (None, "up"):
        lookup = _OBLookup(obs, True, trend_filter)
        for i in range(n_bars):
            lookup.advance(i)
            expected = _find_entry_ob(
                i, float(highs[i]), float(lows[i]), obs, True, trend_filter
            )
            got = lookup.query(float(lows[i]), float(highs[i]))
            assert (expected is None) == (got is None), (i, expected, got)
            if expected is not None:
                assert expected.id == got.id, (i, expected.id, got.id)


def test_ob_lookup_is_exact_at_zone_boundaries():
    """Point queries stay exact strictly inside / outside a zone."""
    from engine.features.indicators import _OBLookup

    ob = _mk_ob(
        id=0, zone_low=100.0, zone_high=105.0, end_idx=0, confirm_idx=0
    )
    lookup = _OBLookup([ob], False, None)
    lookup.advance(0)
    assert lookup.query_point(100.0) == 0  # exactly on the lower edge
    assert lookup.query_point(105.0) == 0  # exactly on the upper edge
    assert lookup.query_point(104.999) == 0
    assert lookup.query_point(99.999) == -1
    assert lookup.query_point(105.001) == -1
    # never-broken zones (end_idx -1) are eligible from the first bar
    active = _mk_ob(
        id=1, zone_low=90.0, zone_high=95.0, end_idx=-1, confirm_idx=0
    )
    lookup2 = _OBLookup([active], False, None)
    lookup2.advance(0)
    assert lookup2.query(92.0, 93.0) is not None
