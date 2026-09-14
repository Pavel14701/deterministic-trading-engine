"""dishka assembly for the okx contour (TZ-15 section 7, TZ-08 pattern).

Protocol keys, lazy connects, no network at startup. Tests replace
ports with fakes via ``make_container(FakeOkxProvider())``.
"""

from __future__ import annotations

from typing import Any

from dishka import Provider, Scope, provide

from okx.src.domain import PosMode
from okx.src.events import EventLoop
from okx.src.ports import (
    EventSink,
    InstrumentMap,
    OrderGateway,
    RiskGate,
    SignalSource,
    StateStore,
)


class OkxConfig:
    """Venue config (env/YAML in the live contour; plain here)."""

    pos_mode: PosMode = PosMode.NET


class FakeOkxProvider(Provider):
    """Test assembly: every port comes from the caller's fakes."""

    scope = Scope.APP

    def __init__(
        self,
        instruments: InstrumentMap,
        gateway: OrderGateway,
        signals: SignalSource,
        risk: RiskGate,
        store: StateStore,
        sink: EventSink,
    ) -> None:
        super().__init__()
        self._instruments = instruments
        self._gateway = gateway
        self._signals = signals
        self._risk = risk
        self._store = store
        self._sink = sink

    @provide
    def instrument_map(self) -> InstrumentMap:
        """Provide instrument map."""
        return self._instruments

    @provide
    def order_gateway(self) -> OrderGateway:
        """Provide order gateway."""
        return self._gateway

    @provide
    def signal_source(self) -> SignalSource:
        """Provide signal source."""
        return self._signals

    @provide
    def risk_gate(self) -> RiskGate:
        """Provide risk gate."""
        return self._risk

    @provide
    def state_store(self) -> StateStore:
        """Provide state store."""
        return self._store

    @provide
    def event_sink(self) -> EventSink:
        """Provide event sink."""
        return self._sink

    @provide
    def event_loop(
        self,
        instruments: InstrumentMap,
        gateway: OrderGateway,
        signals: SignalSource,
        risk: RiskGate,
        store: StateStore,
        sink: EventSink,
    ) -> EventLoop:
        """Provide the event loop wired with all ports."""
        return EventLoop(
            instruments=instruments,
            gateway=gateway,
            signals=signals,
            risk=risk,
            store=store,
            sink=sink,
        )


def make_okx_container(
    instruments: InstrumentMap,
    gateway: OrderGateway,
    signals: SignalSource,
    risk: RiskGate,
    store: StateStore,
    sink: EventSink,
) -> Any:
    """Assemble the okx contour from port fakes/impls (tests, TZ-15 s.7)."""
    from dishka import make_container

    return make_container(
        FakeOkxProvider(
            instruments=instruments,
            gateway=gateway,
            signals=signals,
            risk=risk,
            store=store,
            sink=sink,
        )
    )
