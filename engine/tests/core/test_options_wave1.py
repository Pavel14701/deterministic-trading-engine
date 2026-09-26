# -*- coding: utf-8 -*-
"""Unit tests for the wave-1 options runner (synthetic data only)."""

import calendar
import json

import numpy as np

from experiments.options._runner import (
    MSEC_DAY,
    entry_iv,
    instrument_name,
    perf,
    simulate,
    skew_call,
    skew_put,
)


BASE = 1_600_000_000_000  # hourly grid anchor


def _synth_ctx(tmp_path):
    n = 14 * 24
    ts1 = (np.arange(n) * 3_600_000 + BASE).astype(np.int64)
    cp = np.full(n, 100.0)
    cp[8 * 24:] = 90.0                       # crash on day 8
    day0 = BASE // MSEC_DAY
    dv_ts = np.array([(day0 + i) * MSEC_DAY
                      for i in range(14)], dtype=np.int64)
    dv_v = np.linspace(40.0, 80.0, 14)

    def spot(ts):
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp[max(j, 0)])

    def dvol(ts):
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(dv_v[max(j, 0)])

    def rv30(ts):
        return 50.0

    def pct_at(ts):
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(max(j, 0) / 13)

    return dict(out=tmp_path, ts1=ts1, cp1=cp, spot=spot, dvol=dvol,
                rv30=rv30, pct_at=pct_at, rolls=[], subset={})


def test_skew_tables():
    assert skew_put(0.875) == 13.23
    assert skew_put(0.30) == 12.74          # clamped low
    assert skew_put(1.20) == 7.00           # clamped high
    assert skew_call(1.10, {}) == 0.0
    assert skew_call(1.10, {100: [5.0, 7.0]}) == 6.0


def test_instrument_name():
    ms = calendar.timegm((2022, 2, 25, 8, 0, 0)) * 1000
    assert instrument_name(ms, 34000, False) == "BTC-25FEB22-34000-P"
    assert instrument_name(ms, 34000, True) == "BTC-25FEB22-34000-C"


def test_entry_iv(tmp_path):
    ctx = _synth_ctx(tmp_path)
    ms = BASE + 5 * MSEC_DAY
    name = instrument_name(ms, 85000, False)
    d = tmp_path / "strangle_trades"
    d.mkdir(parents=True)
    (d / f"{name}.json").write_text(json.dumps(
        {"result": {"trades": [
            {"timestamp": ms - 3600_000, "iv": 50.0},
            {"timestamp": ms, "iv": 60.0},
            {"timestamp": ms + 3600_000, "iv": 70.0},
            {"timestamp": ms + 3 * MSEC_DAY, "iv": 99.0},  # outside +/-1d
        ]}}))
    assert entry_iv(ctx, name, ms) == 60.0
    assert entry_iv(ctx, instrument_name(ms, 99.0, True), ms) is None


def test_simulate_side_signs(tmp_path):
    ctx = _synth_ctx(tmp_path)
    t_r = BASE + 6 * 3_600_000
    nxt = (BASE // MSEC_DAY + 10) * MSEC_DAY
    specs = [(t_r, nxt, "put", 85.0), (t_r, nxt, "call", 105.0)]
    res = simulate(ctx, specs, {"put": -1.0, "call": 1.0})
    legs = res["legs"]
    assert len(legs) == 2
    assert all(leg["mode"] == "proxy" for leg in legs)
    # short OTM put settles worthless -> positive carry
    assert legs[0]["cash0"] > 0 and legs[0]["pnl"] > 0
    # long OTM call settles worthless -> negative carry
    assert legs[1]["cash0"] < 0 and legs[1]["pnl"] < 0
    # daily stream covers the holding window
    days = sorted(res["daily"])
    assert days[0] >= t_r // MSEC_DAY and days[-1] == nxt // MSEC_DAY


def test_simulate_dvol_gate(tmp_path):
    ctx = _synth_ctx(tmp_path)
    nxt = (BASE // MSEC_DAY + 12) * MSEC_DAY
    early = BASE + 6 * 3_600_000              # pct ~ 0
    late = BASE + 11 * MSEC_DAY + 6 * 3_600_000  # pct ~ 0.85
    specs = [(early, nxt, "put", 85.0), (late, nxt, "put", 85.0)]
    res = simulate(ctx, specs, {"put": -1.0}, min_dvol_pct=0.75)
    assert len(res["legs"]) == 1
    assert res["legs"][0]["t_r"] == late


def test_perf():
    pf = perf({1: 1.0, 2: -0.5, 3: 0.5})
    assert pf["n"] == 3
    assert np.isfinite(pf["sharpe"]) and pf["sharpe"] > 0
    assert 0 < pf["dd"] < 1
    assert len(pf["by_year"]) >= 1
    assert perf({}) == dict(n=0)
