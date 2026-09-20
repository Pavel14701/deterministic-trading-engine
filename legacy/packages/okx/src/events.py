"""L2 event loop (TZ-15 section 6).

One queue per instrument (no parallel reactions on one instrument),
a config-driven event -> reaction registry. Invariants enforced here
(code, not config): an order only on a confirmed candle; every order
goes through the RiskGate; ``clOrdId`` is deterministic per
(inst, bar-open-ts, direction) so a replayed candle cannot double-fire;
reconcile is the source of truth after a WS break.
"""

from __future__ import annotations

import asyncio

from typing import Any

from contracts import Candle, OhlcvBatch
from okx.src.domain import Direction, OkxEvent, OrderRequest
from okx.src.mapping import is_confirmed, make_cl_ord_id, round_size
from okx.src.ports import (
    EventSink,
    InstrumentMap,
    OrderGateway,
    RiskGate,
    SignalSource,
    StateStore,
)


class EventLoop:
    """Serial event loop with per-instrument ordering."""

    def __init__(
        self,
        instruments: InstrumentMap,
        gateway: OrderGateway,
        signals: SignalSource,
        risk: RiskGate,
        store: StateStore,
        sink: EventSink,
    ) -> None:
        self.instruments = instruments
        self.gateway = gateway
        self.signals = signals
        self.risk = risk
        self.store = store
        self.sink = sink
        self._queues: dict[str, asyncio.Queue[OkxEvent]] = {}
        self._seen_candles: set[tuple[str, int]] = set()
        self.audit: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- #
    # Ingress
    # ---------------------------------------------------------------- #

    def submit(self, event: OkxEvent) -> None:
        """Queue an event; ordering is preserved per instrument."""
        q = self._queues.setdefault(event.inst_id, asyncio.Queue())
        q.put_nowait(event)

    # ---------------------------------------------------------------- #
    # Reactions
    # ---------------------------------------------------------------- #

    def _dispatch(self, event: OkxEvent) -> None:
        if event.kind == "candle_closed":
            self._on_candle_closed(event)
        elif event.kind == "order_filled":
            self._on_order_filled(event)
        elif event.kind == "ws_disconnected":
            self.reconcile()
        # position/account/algo events v1: recorded to the audit only.
        self.audit.append({"event": event.kind, "inst": event.inst_id})

    def _on_candle_closed(self, event: OkxEvent) -> None:
        p = event.payload
        if not is_confirmed(str(p.get("confirm", 0))):
            return  # unconfirmed bar never reaches the DSL (TZ-04 s.5)
        ts = int(p["ts"])
        key = (event.inst_id, ts)
        if key in self._seen_candles:
            return  # idempotency: replayed candle -> no duplicate order
        self._seen_candles.add(key)

        batch = OhlcvBatch(
            inst_id=event.inst_id,
            candles=[
                Candle(
                    inst_id=event.inst_id,
                    ts=ts,
                    open=float(p["open"]),
                    high=float(p["high"]),
                    low=float(p["low"]),
                    close=float(p["close"]),
                    volume=float(p.get("volume", 0.0)),
                )
            ],
        )
        self.sink.push("md.ohlcv", batch)
        canonical = self.instruments.to_canonical(event.inst_id)
        for signal in self.signals.on_candle(batch):
            direction = Direction(str(signal["direction"]))
            size = round_size(
                self.instruments.spec(event.inst_id),
                float(signal["size"]),
            )
            decision = self.risk.check(
                canonical, direction, float(signal["entry_price"]), size
            )
            if not getattr(decision, "approve", False):
                reason = str(getattr(decision, "reason", "rejected"))
                self.store.record_reject(event.inst_id, ts, reason)
                self.sink.push(
                    "audit.reject",
                    {"inst": event.inst_id, "ts": ts, "reason": reason},
                )
                continue
            req = OrderRequest(
                inst_id=event.inst_id,
                direction=direction,
                size=size,
                price=float(signal["entry_price"]),
                cl_ord_id=make_cl_ord_id(event.inst_id, ts, direction),
            )
            ack = self.gateway.place(req)
            self.sink.push(
                "evt.order_ack",
                {
                    "cl_ord_id": req.cl_ord_id,
                    "ok": ack.ok,
                    "order_id": ack.order_id,
                },
            )

    def _on_order_filled(self, event: OkxEvent) -> None:
        p = event.payload
        self.store.save_fill(
            event.inst_id,
            int(p.get("ts", event.ts)),
            str(p.get("side", "")),
            float(p.get("size", 0.0)),
            float(p.get("price", 0.0)),
        )

    # ---------------------------------------------------------------- #
    # Reconcile (source of truth after a break)
    # ---------------------------------------------------------------- #

    def reconcile(self) -> None:
        """Pull REST snapshots; pending orders + positions are truth."""
        for inst_id in list(self._queues):
            for order in self.gateway.pending(inst_id):
                self.audit.append(
                    {
                        "reconcile": "order",
                        "inst": inst_id,
                        "order_id": order.order_id,
                        "state": order.state,
                    }
                )
            pos = self.gateway.open_position(inst_id)
            if pos is not None:
                self.audit.append(
                    {
                        "reconcile": "position",
                        "inst": inst_id,
                        "size": pos.size,
                    }
                )

    async def run_once(self) -> OkxEvent | None:
        """Process one event from any instrument queue.

        Returns the processed event, or None when all queues are empty.
        """
        for q in self._queues.values():
            if q.empty():
                continue
            event = q.get_nowait()
            self._dispatch(event)
            return event
        return None

    async def drain(self) -> int:
        """Process every queued event; returns the number processed."""
        n = 0
        while await self.run_once() is not None:
            n += 1
        return n
