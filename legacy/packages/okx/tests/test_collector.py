"""Live collector unit tests: WS parsing, warm-up, backoff (no network)."""

import pytest

from okx.src.collector import LiveCollector, _subscribe_frame, batch_from_ws
from okx.src.reconnect import ReconnectPolicy, connect_with_backoff
from okx.tests.fakes import FakeSink, FakeTransport


WS_CONFIRMED = {
    "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
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
WS_UNCONFIRMED = {
    "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
    "data": [
        [
            "1700000060000",
            "50050",
            "50110",
            "50000",
            "50080",
            "1.0",
            "50000",
            "50000",
            "0",
        ]
    ],
}


def test_ws_confirmed_row_normalized_to_canon() -> None:
    batch = batch_from_ws(WS_CONFIRMED)
    assert batch is not None
    assert batch.inst_id == "BTC-USDT"
    c = batch.candles[0]
    assert c.ts == 1700000000000
    assert c.close == pytest.approx(50050.0)
    assert c.volume == pytest.approx(2.5)


def test_ws_unconfirmed_bar_is_dropped() -> None:
    assert batch_from_ws(WS_UNCONFIRMED) is None


def test_ws_mixed_rows_keep_only_confirmed() -> None:
    msg = {
        "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
        "data": [*WS_CONFIRMED["data"], *WS_UNCONFIRMED["data"]],
    }
    batch = batch_from_ws(msg)
    assert batch is not None
    assert len(batch.candles) == 1
    assert batch.candles[0].ts == 1700000000000


def test_short_rows_are_ignored() -> None:
    msg = {"arg": {}, "data": [["1", "2", "3"]]}
    assert batch_from_ws(msg) is None


def test_subscribe_frame_uses_okx_bar() -> None:
    frame = _subscribe_frame("BTC-USDT", "1h")
    assert frame == {
        "op": "subscribe",
        "args": [{"channel": "candle1H", "instId": "BTC-USDT"}],
    }


def test_swap_volume_via_ctval_on_ws() -> None:
    msg = {**WS_CONFIRMED, "instType": "SWAP", "ctVal": 0.01}
    batch = batch_from_ws(msg)
    assert batch is not None
    assert batch.candles[0].volume == pytest.approx(0.025)


def test_warm_up_pulls_history_per_instrument() -> None:
    t = FakeTransport(
        {
            "/market/candles": {
                "code": "0",
                "data": [
                    [
                        "1700000000000",
                        "1",
                        "2",
                        "0.5",
                        "1.5",
                        "3",
                        "",
                        "",
                        "1",
                    ]
                ],
            }
        }
    )
    from okx.src.okx_client import OkxClient

    client = OkxClient(t)
    sink = FakeSink()
    collector = LiveCollector(
        transport=t,
        source=client,  # type: ignore[arg-type]
        sink=sink,
        inst_ids=["BTC-USDT", "ETH-USDT"],
        warmup=5,
    )
    n = collector.warm_up()
    assert n == 2
    assert len(t.requests) == 2
    assert all(q == "md.ohlcv" for q, _ in sink.pushed)


@pytest.mark.asyncio
async def test_run_processes_confirmed_and_skips_service_frames() -> None:
    class ScriptedTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.queue: list[dict | str] = [
                WS_UNCONFIRMED,  # dropped: not confirmed
                {"event": "subscribe"},  # service frame
                WS_CONFIRMED,  # -> one event
            ]

        async def recv(self) -> dict | None:
            if not self.queue:
                raise ConnectionError("stream end")
            item = self.queue.pop(0)
            return item  # type: ignore[return-value]

    sink = FakeSink()
    from okx.src.okx_client import OkxClient

    t = ScriptedTransport()
    collector = LiveCollector(
        transport=t,
        source=OkxClient(t),  # type: ignore[arg-type]
        sink=sink,
        inst_ids=["BTC-USDT"],
    )
    with pytest.raises(ConnectionError):
        await collector.run(max_events=5)
    assert len(sink.pushed) == 1


def test_reconnect_policy_backoff_monotonic_capped() -> None:
    p = ReconnectPolicy(base_delay=0.5, max_delay=4.0, factor=2.0)
    assert [p.delay_for(i) for i in range(5)] == [
        pytest.approx(0.5),
        pytest.approx(1.0),
        pytest.approx(2.0),
        pytest.approx(4.0),
        pytest.approx(4.0),
    ]


@pytest.mark.asyncio
async def test_connect_with_backoff_retries_then_raises() -> None:
    class Failing:
        attempts = 0

        async def connect(self) -> None:
            self.attempts += 1
            raise ConnectionError("no")

    f = Failing()
    p = ReconnectPolicy(base_delay=0.001, max_delay=0.002, max_attempts=3)
    with pytest.raises(ConnectionError):
        await connect_with_backoff(f, p)  # type: ignore[arg-type]
    assert f.attempts == 3


@pytest.mark.asyncio
async def test_connect_with_backoff_succeeds_after_failures() -> None:
    class Flaky:
        attempts = 0

        async def connect(self) -> None:
            self.attempts += 1
            if self.attempts < 3:
                raise ConnectionError("no")

    f = Flaky()
    p = ReconnectPolicy(base_delay=0.001, max_delay=0.002, max_attempts=5)
    await connect_with_backoff(f, p)  # type: ignore[arg-type]
    assert f.attempts == 3
