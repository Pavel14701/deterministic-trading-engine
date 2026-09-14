"""dishka assembly test: the container builds an EventLoop from fakes."""

from okx.src.di import make_okx_container
from okx.src.events import EventLoop
from okx.src.instruments import StaticInstrumentMap
from okx.tests.fakes import (
    BTC,
    ApproveGate,
    FakeGateway,
    FakeSignals,
    FakeSink,
    FakeStore,
)


def test_container_resolves_event_loop() -> None:
    container = make_okx_container(
        instruments=StaticInstrumentMap({"BTCUSDT": BTC}),
        gateway=FakeGateway(),
        signals=FakeSignals(),
        risk=ApproveGate(),
        store=FakeStore(),
        sink=FakeSink(),
    )
    loop = container.get(EventLoop)
    assert isinstance(loop, EventLoop)
    assert loop.instruments.to_venue("BTCUSDT") == "BTC-USDT"


def test_unknown_instrument_refused() -> None:
    import pytest

    from okx.src.domain import StartupRefusalError

    m = StaticInstrumentMap({"BTCUSDT": BTC})
    with pytest.raises(StartupRefusalError):
        m.to_venue("ETHUSDT")
