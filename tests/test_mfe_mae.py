"""Tests for the DSL-configured MFE/MAE collector (engine.mfe_mae)."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from dsl import Context, InProcessProvider
from dsl.exceptions import DSLError
from engine.features import compute_atr
from engine.mfe_mae import MfeMaeSpec, collect_mfe_mae


STEP = 3_600_000
T0 = 1_700_000_000_000


def make_bars(
    closes,
    opens=None,
    highs=None,
    lows=None,
    volume=None,
) -> pl.DataFrame:
    """Handcrafted bar frame; defaults keep o/h/l consistent with close."""
    closes = np.asarray(closes, dtype=np.float64)
    n = len(closes)
    opens = closes if opens is None else np.asarray(opens, dtype=np.float64)
    highs = (
        np.maximum(opens, closes)
        if highs is None
        else np.asarray(highs, dtype=np.float64)
    )
    lows = (
        np.minimum(opens, closes)
        if lows is None
        else np.asarray(lows, dtype=np.float64)
    )
    data = {
        "ts": T0 + STEP * np.arange(n),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    }
    if volume is not None:
        data["volume"] = np.asarray(volume, dtype=np.float64)
    return pl.DataFrame(data)


# One signal event at bar 1 (high == 10.4), entry next_open at bar 2.
# Excursion bars (from bar 2): highs 11.2/10.8/10.1/10.0, lows
# 9.5/10.0/9.95/10.0, entry open = 10.0.
SCENARIO = dict(
    closes=[10, 10, 10, 10, 10, 10],
    opens=[10, 10, 10, 10, 10, 10],
    highs=[10.0, 10.4, 11.2, 10.8, 10.1, 10.0],
    lows=[9.9, 9.8, 9.5, 10.0, 9.95, 10.0],
)
SPEC_AT_BAR1 = MfeMaeSpec(signal="high == 10.4", horizon=24)


def single_row(df: pl.DataFrame) -> dict:
    assert df.height == 1
    return df.row(0, named=True)


def test_long_handcrafted_mfe_mae() -> None:
    ev = single_row(collect_mfe_mae(make_bars(**SCENARIO), SPEC_AT_BAR1))
    assert ev["mfe_abs"] == pytest.approx(1.2)  # high[2]=11.2 - entry 10
    assert ev["mae_abs"] == pytest.approx(0.5)  # entry 10 - low[2]=9.5
    assert ev["entry_price"] == pytest.approx(10.0)
    assert ev["signal_ts"] == T0 + STEP
    assert ev["entry_ts"] == T0 + 2 * STEP
    assert ev["entry_idx"] == 2
    assert ev["bars_measured"] == 4


def test_short_side_mirrors() -> None:
    spec = MfeMaeSpec(signal="high == 10.4", side="short", horizon=24)
    ev = single_row(collect_mfe_mae(make_bars(**SCENARIO), spec))
    assert ev["mfe_abs"] == pytest.approx(0.5)
    assert ev["mae_abs"] == pytest.approx(1.2)


def test_horizon_truncation() -> None:
    bars = make_bars(**SCENARIO)
    ev = single_row(
        collect_mfe_mae(bars, MfeMaeSpec(signal="high == 10.4", horizon=2))
    )
    assert ev["bars_measured"] == 2
    assert ev["mfe_abs"] == pytest.approx(1.2)
    assert ev["mae_abs"] == pytest.approx(0.5)
    # signal at bar 3, horizon 1: only bar 4 (high 10.1, low 9.95)
    ev = single_row(
        collect_mfe_mae(bars, MfeMaeSpec(signal="high == 10.8", horizon=1))
    )
    assert ev["bars_measured"] == 1
    assert ev["mfe_abs"] == pytest.approx(0.1)
    assert ev["mae_abs"] == pytest.approx(0.05)


def test_incomplete_partial_vs_drop() -> None:
    bars = make_bars(**SCENARIO)  # event at bar 4 -> only bar 5 remains
    ev = single_row(
        collect_mfe_mae(
            bars,
            MfeMaeSpec(signal="high == 10.1", horizon=24,
                       incomplete="partial"),
        )
    )
    assert ev["bars_measured"] == 1
    assert ev["mfe_abs"] == 0.0
    assert ev["mae_abs"] == 0.0
    out = collect_mfe_mae(
        bars,
        MfeMaeSpec(signal="high == 10.1", horizon=24, incomplete="drop"),
    )
    assert out.height == 0


def test_entry_next_open_vs_signal_close() -> None:
    rest = {k: v for k, v in SCENARIO.items() if k != "opens"}
    bars = make_bars(opens=[10, 10, 9.7, 10, 10, 10], **rest)
    ev = single_row(collect_mfe_mae(bars, SPEC_AT_BAR1))
    assert ev["entry_price"] == pytest.approx(9.7)
    assert ev["mfe_abs"] == pytest.approx(11.2 - 9.7)
    assert ev["mae_abs"] == pytest.approx(9.7 - 9.5)
    ev = single_row(collect_mfe_mae(
        bars,
        MfeMaeSpec(signal="high == 10.4", entry="signal_close", horizon=24),
    ))
    assert ev["entry_price"] == pytest.approx(10.0)
    assert ev["entry_ts"] == T0 + STEP  # filled at the signal bar close
    # window starts at bar 2 either way (fill bar excluded for close)
    assert ev["mfe_abs"] == pytest.approx(1.2)
    assert ev["mae_abs"] == pytest.approx(0.5)


def test_mae_zero_when_never_adverse() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    bars = make_bars(closes=closes,
                     highs=[c + 0.5 for c in closes])
    ev = single_row(
        collect_mfe_mae(bars, MfeMaeSpec(signal="high == 1.5", horizon=24))
    )
    # entry = open[1] = 2.0; all later lows = closes >= 2.0 -> no adverse
    assert ev["mae_abs"] == 0.0
    assert ev["mfe_abs"] == pytest.approx(6.5 - 2.0)


def test_no_lookahead_prefix_invariance() -> None:
    bars = make_bars(**SCENARIO)
    spec = MfeMaeSpec(signal="high == 10.4", horizon=2)
    base = single_row(collect_mfe_mae(bars, spec))
    # 1) prefix run: same event, same numbers
    head = single_row(collect_mfe_mae(bars.head(4), spec))
    for k in ("signal_ts", "entry_ts", "entry_price",
              "mfe_abs", "mae_abs", "bars_measured"):
        assert head[k] == base[k]
    # 2) mutating the far future must not change past events
    mutated = bars.with_columns(
        pl.when(pl.arange(0, pl.len()) == 5)
        .then(pl.col("high") * 10)
        .otherwise(pl.col("high"))
        .alias("high")
    )
    after = single_row(collect_mfe_mae(mutated, spec))
    assert after["mfe_abs"] == base["mfe_abs"]
    assert after["mae_abs"] == base["mae_abs"]


def test_dsl_sma_and_let_signals() -> None:
    closes = [5.0, 5.0, 5.0, 5.0, 6.0, 6.0, 6.0, 6.0]
    bars = make_bars(closes=closes)
    spec = MfeMaeSpec(signal="close > sma(period=3)", horizon=1)
    out = collect_mfe_mae(bars, spec)
    # sma(3) at t = mean(close[t-2..t]); close exceeds it at bars 4,5
    # (at bar 6 the window is all 6s -> close == sma, not greater)
    assert out["signal_ts"].to_list() == [T0 + 4 * STEP, T0 + 5 * STEP]
    spec = MfeMaeSpec(signal="let d = close - open in d > 0", horizon=1)
    bars = make_bars(opens=[5, 5, 5, 5, 5, 5],
                     closes=[5, 4.9, 5.1, 5.0, 5.2, 5.0])
    out = collect_mfe_mae(bars, spec)
    assert out["signal_ts"].to_list() == [T0 + 2 * STEP, T0 + 4 * STEP]


def test_historical_offset_warmup_is_silent() -> None:
    bars = make_bars(closes=[1.0, 2.0, 3.0, 4.0])
    spec = MfeMaeSpec(signal="close[1] < close", horizon=1)
    out = collect_mfe_mae(bars, spec)
    # strictly rising: fires on bars 1..2 (bar 3 has no next bar to
    # fill in); bar 0 has no history and must NOT fire (NaN warm-up),
    # nor crash
    assert out["signal_ts"].to_list() == [T0 + STEP, T0 + 2 * STEP]


def test_unknown_indicator_fails_fast() -> None:
    with pytest.raises(DSLError):
        collect_mfe_mae(
            make_bars(closes=[1, 1, 1]),
            MfeMaeSpec(signal="wibblex(period=2) > 5"),
        )


def test_spec_validation_and_roundtrip() -> None:
    for kwargs in (
        {"signal": "close > 0", "side": "both"},
        {"signal": "close > 0", "entry": "open"},
        {"signal": "close > 0", "incomplete": "skip"},
        {"signal": "close > 0", "exit": "stop"},
        {"signal": "close > 0", "horizon": 0},
        {"signal": "close > 0", "sl_atr_mult": 0.0},
    ):
        with pytest.raises(ValueError):
            MfeMaeSpec(**kwargs)
    spec = MfeMaeSpec(signal="close >= sma(period=5)", side="short",
                      horizon=2, entry="signal_close", atr_period=5,
                      sl_atr_mult=1.5, incomplete="drop", exit="sl_hit")
    out = collect_mfe_mae(make_bars(**SCENARIO),
                          MfeMaeSpec.from_dict(spec.to_dict()))
    # flat closes: signal fires on every bar; drop keeps bars 0..3
    # (their 2-bar windows fit); bar 4 needs bars 5..6, bar 5 has no fill
    assert out.height == 4


def test_atr_and_r_normalization() -> None:
    bars = make_bars(**SCENARIO)
    spec = MfeMaeSpec(signal="high == 10.4", horizon=24, atr_period=3,
                      sl_atr_mult=2.0)
    ev = single_row(collect_mfe_mae(bars, spec))
    atr1 = float(compute_atr(bars, period=3)[1])
    assert ev["mfe_atr"] == pytest.approx(ev["mfe_abs"] / atr1)
    assert ev["mae_atr"] == pytest.approx(ev["mae_abs"] / atr1)
    assert ev["mfe_r"] == pytest.approx(ev["mfe_abs"] / (2.0 * atr1))
    assert ev["mae_r"] == pytest.approx(ev["mae_abs"] / (2.0 * atr1))


def test_empty_result_schema() -> None:
    out = collect_mfe_mae(
        make_bars(closes=[1, 2, 3]),
        MfeMaeSpec(signal="close < 0"),
    )
    assert out.height == 0
    assert out.columns == [
        "signal_ts", "entry_ts", "entry_idx", "entry_price",
        "bars_measured", "mfe_abs", "mae_abs", "mfe_atr", "mae_atr",
        "mfe_r", "mae_r", "sl_hit",
    ]
    assert out.schema["signal_ts"] == pl.Int64
    assert out.schema["mfe_r"] == pl.Float64


def test_context_factory_hook() -> None:
    """Custom wiring: an external provider drives the signal."""
    manifest = {"indicators": {"sig": {"attributes": []}}}
    provider = InProcessProvider(
        manifest, lambda ind, params, attrs, off: 6.0
    )

    def factory(cache, bar_idx: int) -> Context:
        return Context([provider])

    out = collect_mfe_mae(
        make_bars(closes=[1, 2, 3]),
        MfeMaeSpec(signal="sig > 5", horizon=1),
        context_factory=factory,
    )
    assert out.height == 2  # bars 0..1 (bar 2 cannot fill next_open)
    assert out["entry_idx"].to_list() == [1, 2]


def test_volume_column_optional_but_usable() -> None:
    bars = make_bars(closes=[10, 10, 10], volume=[100, 900, 100])
    out = collect_mfe_mae(
        bars, MfeMaeSpec(signal="volume > 500", horizon=1)
    )
    assert out["signal_ts"].to_list() == [T0 + STEP]
    # missing volume column only breaks if the signal uses it
    with pytest.raises(DSLError):
        collect_mfe_mae(
            make_bars(closes=[10, 10, 10],
                      volume=[1, 1, 1]).drop("volume"),
            MfeMaeSpec(signal="volume > 500", horizon=1),
        )
    out2 = collect_mfe_mae(
        make_bars(closes=[10, 10, 10], volume=[1, 1, 1]).drop("volume"),
        MfeMaeSpec(signal="close > 0", horizon=1),
    )
    assert out2.height == 2


def test_exit_sl_hit_truncates_window() -> None:
    """Window ends at the first stop-touch bar (independent oracle)."""
    bars = make_bars(**SCENARIO)  # signal at bar 1, entry open[2] = 10
    spec = MfeMaeSpec(signal="high == 10.4", horizon=24, atr_period=3,
                      sl_atr_mult=1.0, exit="sl_hit")
    ev = single_row(collect_mfe_mae(bars, spec))
    atr1 = float(compute_atr(bars, period=3)[1])
    stop = 10.0 - 1.0 * atr1  # long stop under entry
    lows = [9.5, 10.0, 9.95, 10.0]  # window bars 2..5
    hit = next(k for k, lo in enumerate(lows) if lo <= stop)
    assert ev["sl_hit"] is True
    assert ev["bars_measured"] == hit + 1
    assert ev["mae_abs"] == pytest.approx(10.0 - min(lows[:hit + 1]))
    # MFE counts only bars up to the hit
    highs = [11.2, 10.8, 10.1, 10.0]
    assert ev["mfe_abs"] == pytest.approx(max(highs[:hit + 1]) - 10.0)


def test_exit_sl_hit_not_triggered_runs_full_window() -> None:
    bars = make_bars(**SCENARIO)
    spec = MfeMaeSpec(signal="high == 10.4", horizon=24, atr_period=3,
                      sl_atr_mult=2.0, exit="sl_hit")  # stop far below
    ev = single_row(collect_mfe_mae(bars, spec))
    assert ev["sl_hit"] is False
    assert ev["bars_measured"] == 4
    assert ev["mfe_abs"] == pytest.approx(1.2)
    assert ev["mae_abs"] == pytest.approx(0.5)


def test_sl_hit_mid_window_and_horizon_mode_flag() -> None:
    bars = make_bars(
        closes=[10, 10, 10, 10, 10, 10],
        highs=[10.0, 10.4, 10.3, 10.2, 10.6, 10.0],
        lows=[9.9, 9.8, 9.7, 9.0, 9.1, 9.9],
    )
    # signal at bar 1, entry open[2] = 10; atr(3)[1] = (0.1 + 0.6) / 2
    atr1 = float(compute_atr(bars, period=3)[1])
    stop = 10.0 - 2.0 * atr1
    assert 9.7 > stop >= 9.0  # hit lands on the 3rd window bar
    ev = single_row(collect_mfe_mae(
        bars,
        MfeMaeSpec(signal="high == 10.4", horizon=24, atr_period=3,
                   sl_atr_mult=2.0, exit="sl_hit"),
    ))
    assert ev["sl_hit"] is True
    assert ev["bars_measured"] == 2  # bars 2..3; bar 3 low 9.0 hits stop
    assert ev["mfe_abs"] == pytest.approx(10.3 - 10.0)  # pre-hit highs
    # horizon mode: same window fully walked, sl_hit is informational
    ev = single_row(collect_mfe_mae(
        bars,
        MfeMaeSpec(signal="high == 10.4", horizon=24, atr_period=3,
                   sl_atr_mult=2.0, exit="horizon"),
    ))
    assert ev["sl_hit"] is True
    assert ev["bars_measured"] == 4
    assert ev["mfe_abs"] == pytest.approx(10.6 - 10.0)
    assert ev["mae_abs"] == pytest.approx(10.0 - 9.0)


def test_exit_sl_hit_short_side() -> None:
    bars = make_bars(**SCENARIO)  # short entry 10 at bar 2
    spec = MfeMaeSpec(signal="high == 10.4", side="short", horizon=24,
                      atr_period=3, sl_atr_mult=1.0, exit="sl_hit")
    ev = single_row(collect_mfe_mae(bars, spec))
    atr1 = float(compute_atr(bars, period=3)[1])
    assert ev["entry_price"] == pytest.approx(10.0 + 0.0)
    assert ev["sl_hit"] is bool(11.2 >= 10.0 + 1.0 * atr1)
    assert ev["mfe_abs"] == pytest.approx(10.0 - 9.5)  # first bar only
    assert ev["bars_measured"] == 1
