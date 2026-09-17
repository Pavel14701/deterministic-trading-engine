"""Event-loop e2e tests (TZ-15 acceptance criteria)."""

import pytest

from okx.src.domain import OkxEvent
from okx.src.events import EventLoop
from okx.tests.fakes import RejectGate


def make_loop(gate) -> tuple[EventLoop, tuple]:
    from okx.tests.fakes import (
        ApproveGate,
        FakeGateway,
        FakeSignals,
        FakeSink,
        FakeStore,
        make_map,
    )

    gateway = FakeGateway()
    signals = FakeSignals()
    store = FakeStore()
    sink = FakeSink()
    loop = EventLoop(
        instruments=make_map(),
        gateway=gateway,
        signals=signals,
        risk=gate or ApproveGate(),
        store=store,
        sink=sink,
    )
    return loop, (gateway, signals, store, sink)


def candle_event(ts: int = 1700000000000) -> OkxEvent:
    return OkxEvent(
        kind="candle_closed",
        inst_id="BTC-USDT",
        ts=ts,
        payload={
            "confirm": 1,
            "ts": ts,
            "open": 50000.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50050.0,
            "volume": 2.5,
        },
    )


@pytest.mark.asyncio
async def test_candle_closed_approve_places_one_order_with_cl_ord_id() -> None:
    loop, (gateway, signals, _store, sink) = make_loop(None)
    loop.submit(candle_event())
    assert await loop.drain() == 1

    assert len(signals.calls) == 1  # DSL saw the confirmed batch
    assert len(gateway.placed) == 1
    req = gateway.placed[0]
    assert req.cl_ord_id == "dte-BTC-USDT-1700000000000-long"
    # deterministic rounding: size 0.5 -> lot 0.0001 grid, price -> tick
    assert req.size == pytest.approx(0.5)
    assert req.price == pytest.approx(50_000.1)
    queues = [q for q, _ in sink.pushed]
    assert "md.ohlcv" in queues
    assert "evt.order_ack" in queues


@pytest.mark.asyncio
async def test_replayed_candle_does_not_duplicate_order() -> None:
    loop, (gateway, signals, _store, _sink) = make_loop(None)
    loop.submit(candle_event())
    loop.submit(candle_event())  # same (inst, ts) => same clOrdId
    await loop.drain()
    assert len(gateway.placed) == 1
    assert len(signals.calls) == 1


@pytest.mark.asyncio
async def test_unconfirmed_bar_never_reaches_dsl() -> None:
    loop, (gateway, signals, _store, _sink) = make_loop(None)
    ev = candle_event()
    ev = OkxEvent(
        kind="candle_closed",
        inst_id=ev.inst_id,
        ts=ev.ts,
        payload={**ev.payload, "confirm": 0},
    )
    loop.submit(ev)
    await loop.drain()
    assert signals.calls == []
    assert gateway.placed == []


@pytest.mark.asyncio
async def test_risk_reject_no_order_and_audit() -> None:
    loop, (gateway, _signals, store, sink) = make_loop(RejectGate())
    loop.submit(candle_event())
    await loop.drain()
    assert gateway.placed == []
    assert store.rejects == [("BTC-USDT", 1700000000000, "cap: too large")]
    assert any(q == "audit.reject" for q, _ in sink.pushed)


@pytest.mark.asyncio
async def test_order_filled_updates_store() -> None:
    loop, (_g, _s, store, _sink) = make_loop(None)
    loop.submit(
        OkxEvent(
            kind="order_filled",
            inst_id="BTC-USDT",
            ts=1700000001000,
            payload={"side": "buy", "size": 0.5, "price": 50000.0},
        )
    )
    await loop.drain()
    assert store.fills == [("BTC-USDT", 1700000001000, "buy", 0.5, 50000.0)]


@pytest.mark.asyncio
async def test_ws_disconnected_triggers_reconcile() -> None:
    loop, (gateway, _s, _store, _sink) = make_loop(None)
    gateway.pending_orders = []
    gateway.position = None
    loop.submit(candle_event())
    loop.submit(OkxEvent(kind="ws_disconnected", inst_id="BTC-USDT", ts=1))
    await loop.drain()
    # reconcile ran over the known instruments (empty snapshots, no crash)
    assert any(a.get("event") == "ws_disconnected" for a in loop.audit)


@pytest.mark.asyncio
async def test_per_instrument_ordering_preserved() -> None:
    loop, (gateway, _s, _store, _sink) = make_loop(None)
    loop.submit(candle_event(ts=1700000000000))
    loop.submit(candle_event(ts=1700000002000))
    await loop.drain()
    assert len(gateway.placed) == 2
    assert gateway.placed[0].cl_ord_id.endswith("1700000000000-long")
    assert gateway.placed[1].cl_ord_id.endswith("1700000002000-long")
