"""Startup checks: posMode mismatch = refusal to start (TZ-15 s.3)."""

import pytest

from okx.src.domain import PosMode, StartupRefusalError
from okx.src.okx_client import OkxClient
from okx.tests.fakes import FakeTransport


def test_pos_mode_match_passes() -> None:
    t = FakeTransport(
        {"/account/config": {"code": "0", "data": [{"posMode": "net_mode"}]}}
    )
    OkxClient(t).check_account(PosMode.NET)
    assert t.requests == [("GET", "/account/config")]


def test_pos_mode_mismatch_refuses_startup() -> None:
    t = FakeTransport(
        {
            "/account/config": {
                "code": "0",
                "data": [{"posMode": "long_short_mode"}],
            }
        }
    )
    with pytest.raises(StartupRefusalError, match="posMode mismatch"):
        OkxClient(t).check_account(PosMode.NET)


def test_candles_history_normalizes_to_canon() -> None:
    t = FakeTransport(
        {
            "/market/candles": {
                "code": "0",
                "data": [
                    [
                        "1700000000000",
                        "50000",
                        "50100",
                        "49900",
                        "50050",
                        "2.5",
                        "125000",
                        "125000",
                        "1",
                    ]
                ],
            }
        }
    )
    batch = OkxClient(t).candles_history("BTC-USDT", "1h", 1)
    assert batch.inst_id == "BTC-USDT"
    assert len(batch.candles) == 1
    c = batch.candles[0]
    assert c.ts == 1700000000000
    assert c.volume == pytest.approx(2.5)


def test_instruments_parse_specs() -> None:
    from okx.src.domain import InstType

    t = FakeTransport(
        {
            "/public/instruments": {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT",
                        "instType": "SPOT",
                        "lotSz": "0.0001",
                        "tickSz": "0.1",
                        "minSz": "0.0001",
                    }
                ],
            }
        }
    )
    specs = OkxClient(t).instruments(InstType.SPOT)
    assert specs[0].inst_id == "BTC-USDT"
    assert specs[0].tick_sz == pytest.approx(0.1)
