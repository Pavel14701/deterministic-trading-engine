"""Tests for the T-Invest adapter (mocked HTTP) and source registry."""

from __future__ import annotations

import pytest

import marketdata.okx_source  # noqa: F401  (registers the source)
import marketdata.tinvest_source  # noqa: F401  (registers the source)
import tinvest.src.fetch as fetch_mod
import tinvest.src.instruments as instruments_mod

from marketdata.common import get_source
from tinvest.src.fetch import (
    _quotation_to_float,
    _rows_to_df,
    _ts_to_ms,
    fetch_candles,
)
from tinvest.src.http import api_post
from tinvest.src.instruments import parse_instrument, resolve_instrument
from tinvest.src.mapping import resolve_bar


# --- pure helpers ----------------------------------------------------------


def test_quotation_to_float() -> None:
    assert _quotation_to_float({"units": 123, "nano": 500_000_000}) == 123.5


def test_ts_to_ms_handles_offset_timestamps() -> None:
    # 2024-01-01 00:00 UTC
    assert _ts_to_ms("2024-01-01T03:00:00+03:00") == 1704067200000
    assert _ts_to_ms("2024-01-01T00:00:00Z") == 1704067200000


def test_rows_to_df_canonical_output() -> None:
    candles = [
        {
            "time": "2024-01-01T10:00:00Z",
            "open": {"units": 10, "nano": 0},
            "high": {"units": 11, "nano": 0},
            "low": {"units": 9, "nano": 0},
            "close": {"units": 10, "nano": 500_000_000},
            "volume": {"units": 100, "nano": 0},
        }
    ]
    df = _rows_to_df(candles, None)
    assert df.columns == ["ts", "open", "high", "low", "close", "volume"]
    assert df["ts"][0] == 1704103200000
    assert df["close"][0] == pytest.approx(10.5)
    # duplicate ts rows are dropped on merge
    merged = _rows_to_df(candles, df)
    assert merged.height == 1


def test_resolve_bar_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported bar"):
        resolve_bar("2H")


# --- instrument resolution -------------------------------------------------


def test_parse_instrument_variants() -> None:
    assert parse_instrument("BBG004730N88")["figi"] == "BBG004730N88"
    p = parse_instrument("SBER@MOEX")
    assert p["ticker"] == "SBER" and p["class_code"] == "MOEX"
    assert parse_instrument("GAZP")["ticker"] == "GAZP"


def test_resolve_instrument_via_api_and_cache(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def fake_post(method: str, body=None, token=None, **kw) -> dict:
        calls.append(body or {})
        return {
            "instruments": [
                {"figi": "BBG004730N88", "ticker": "SBER", "classCode": "MOEX"}
            ]
        }

    monkeypatch.setattr(instruments_mod, "api_post", fake_post)
    cache = tmp_path / "figi.json"
    figi = resolve_instrument("SBER@MOEX", token="t", cache_path=cache)
    assert figi == "BBG004730N88"
    # second call must come from the cache, no API hit
    calls.clear()
    figi2 = resolve_instrument("SBER@MOEX", token="t", cache_path=cache)
    assert figi2 == "BBG004730N88"
    assert not calls


def test_api_post_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("T_INVEST_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="T_INVEST_TOKEN"):
        api_post("any/Method", body={})


# --- fetch_candles with mocked pages ---------------------------------------


def _fake_page(times_ms: list[int]) -> list[dict]:
    return [
        {
            "time": _ms_to_iso(ts),
            "open": {"units": 1, "nano": 0},
            "high": {"units": 2, "nano": 0},
            "low": {"units": 0, "nano": 5},
            "close": {"units": 1, "nano": 500_000_000},
            "volume": {"units": 7, "nano": 0},
        }
        for ts in times_ms
    ]


def _ms_to_iso(ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00"
    )


def test_fetch_candles_paginates_and_tails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1H bars: window = max_bars hours; chunk = 1000h > window -> one page
    pages: dict[int, list[dict]] = {}

    def fake_page(figi, interval, from_ms, to_ms, token) -> list[dict]:
        pages[from_ms] = _fake_page(
            [from_ms + 3_600_000 * (i + 1) for i in range(5)]
        )
        return pages[from_ms]

    monkeypatch.setattr(fetch_mod, "_candles_page", fake_page)
    monkeypatch.setattr(
        fetch_mod,
        "resolve_instrument",
        lambda inst, token=None, cache_path=None: "FIGI1",
    )
    df = fetch_candles(
        "SBER@MOEX", bar="1H", max_bars=4, cache_dir=tmp_path, token="t"
    )
    assert df.height == 4  # tail(max_bars)
    assert df["ts"].is_sorted()
    assert (df["close"] == 1.5).all()
    # the cache was written and the next call hits it without HTTP
    cache = tmp_path / "raw_SBER@MOEX_1H.parquet"
    assert cache.exists()
    df2 = fetch_candles(
        "SBER@MOEX", bar="1H", max_bars=4, cache_dir=tmp_path, token="t"
    )
    assert df2.height == 4


# --- source registry --------------------------------------------------------


def test_registry_returns_sources() -> None:
    okx = get_source("okx")
    assert okx.BAR_MS["1m"] == 60_000
    ti = get_source("tinvest")
    assert ti.BAR_MS["1H"] == 3_600_000
    with pytest.raises(ValueError, match="unknown data source"):
        get_source("moex")


def test_tinvest_depth_limit_rejects_year_of_minutes() -> None:
    ti = get_source("tinvest")
    with pytest.raises(ValueError, match="limited to"):
        ti.check_depth("1m", years=1.0)
    ti.check_depth("1H", years=1.0)  # allowed
    okx = get_source("okx")
    okx.check_depth("1m", years=1.0)  # OKX is not depth-limited


def test_okx_supports_daily_bars_and_derives_bars_per_year() -> None:
    okx = get_source("okx")
    for bar in ("1m", "5m", "15m", "1H", "1D"):
        assert okx.supports_bar(bar)
    # bars-per-year is derived from BAR_MS (365.25-day year)
    assert okx.bars_per_year("1D") == pytest.approx(365.25, abs=1e-6)
    assert okx.bars_per_year("1m") == pytest.approx(525_960.0, abs=1.0)
    assert not okx.supports_bar("2m")
    with pytest.raises(ValueError, match="unsupported bar"):
        okx.bars_per_year("2m")


def test_validate_bars_reports_unsupported_and_too_deep() -> None:
    ti = get_source("tinvest")
    with pytest.raises(ValueError, match="does not support bar"):
        ti.validate_bars(["2H"], years=0.1)
    with pytest.raises(ValueError, match="limited to"):
        ti.validate_bars(["1m"], years=1.0)
    # a request both venues can serve passes silently
    okx = get_source("okx")
    okx.validate_bars(["1m", "5m", "1D"], years=1.0)


def test_resolve_assets_mixes_sources() -> None:
    from scripts.prepare_okx_dataset import resolve_assets

    resolved = resolve_assets(
        get_source("okx"),
        ["BTC-USDT", "okx:ETH-USDT", "tinvest:SBER@MOEX"],
        ["1H", "1D"],
        years=1.0,
    )
    assert [(name, inst) for name, inst, _ in resolved] == [
        ("okx", "BTC-USDT"),
        ("okx", "ETH-USDT"),
        ("tinvest", "SBER@MOEX"),
    ]
    # each asset keeps its own source instance
    assert resolved[0][2] is not resolved[2][2]


def test_resolve_assets_rejects_unknown_prefix() -> None:
    from scripts.prepare_okx_dataset import resolve_assets

    with pytest.raises(ValueError, match="unknown source prefix"):
        resolve_assets(get_source("okx"), ["moex:SBER"], ["1H"], years=0.1)


def test_resolve_assets_rejects_bar_missing_on_prefix_source() -> None:
    from scripts.prepare_okx_dataset import resolve_assets

    # T-Invest has no 2H interval: the mixed request must fail up front
    # with a clear message instead of a KeyError inside the fetch loop
    with pytest.raises(ValueError, match="does not support bar"):
        resolve_assets(
            get_source("okx"),
            ["okx:BTC-USDT", "tinvest:SBER@MOEX"],
            ["2H"],
            years=0.1,
        )
