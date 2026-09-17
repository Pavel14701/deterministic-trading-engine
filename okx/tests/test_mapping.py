"""Normalization payload -> canon tests (TZ-15 acceptance)."""

import pytest

from okx.src.domain import Direction
from okx.src.mapping import (
    candle_from_rest_row,
    canonical_bar,
    check_min_size,
    is_confirmed,
    make_cl_ord_id,
    okx_bar,
    order_side,
    round_price,
    round_size,
)


ROW_SPOT = [
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


def test_bar_map_round_trip() -> None:
    for canon, okx in {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1Dutc",
        "1w": "1W",
    }.items():
        assert okx_bar(canon) == okx
        assert canonical_bar(okx) == canon


def test_bar_map_unknown_raises() -> None:
    with pytest.raises(ValueError, match="canonical bar"):
        okx_bar("2h")
    with pytest.raises(ValueError, match="OKX bar"):
        canonical_bar("2H")


def test_rest_row_spot_volume_is_base() -> None:
    c = candle_from_rest_row(ROW_SPOT, "SPOT", 1.0)
    assert c.ts == 1700000000000  # bar open time, ms
    assert (c.open, c.high, c.low, c.close) == (
        50000.0,
        50100.0,
        49900.0,
        50050.0,
    )
    assert c.volume == 2.5


def test_rest_row_swap_volume_multiplies_ctval() -> None:
    c = candle_from_rest_row(ROW_SPOT, "SWAP", 0.01)
    assert c.volume == pytest.approx(0.025)


def test_confirm_flag() -> None:
    assert is_confirmed("1")
    assert is_confirmed(1)
    assert not is_confirmed("0")
    assert not is_confirmed(0)


def test_round_size_down_to_lot_grid() -> None:
    from okx.tests.fakes import BTC

    assert round_size(BTC, 0.54321) == pytest.approx(0.5432)
    assert round_size(BTC, 0.00005) == 0.0
    assert not check_min_size(BTC, 0.0)


def test_round_price_to_tick_grid() -> None:
    from okx.tests.fakes import BTC

    assert round_price(BTC, 50_000.1234) == pytest.approx(50_000.1)
    assert round_price(BTC, 50_000.17) == pytest.approx(50_000.2)


def test_order_side_net_vs_long_short() -> None:
    assert order_side(Direction.LONG, "net_mode") == ("buy", "net")
    assert order_side(Direction.SHORT, "net_mode") == ("sell", "net")
    assert order_side(Direction.LONG, "long_short_mode") == ("buy", "long")
    assert order_side(Direction.SHORT, "long_short_mode") == ("sell", "short")


def test_cl_ord_id_deterministic() -> None:
    a = make_cl_ord_id("BTC-USDT", 1700000000000, Direction.LONG)
    b = make_cl_ord_id("BTC-USDT", 1700000000000, Direction.LONG)
    c = make_cl_ord_id("BTC-USDT", 1700000000001, Direction.LONG)
    assert a == b
    assert a != c
