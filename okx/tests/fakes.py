"""Shared fakes for the okx test suite (TZ-15 acceptance: fake transport)."""

from __future__ import annotations

from typing import Any

from okx.src.domain import Direction, InstrumentSpec
from okx.src.instruments import StaticInstrumentMap


BTC = InstrumentSpec(
    inst_id="BTC-USDT",
    inst_type="SPOT",
    lot_sz=0.0001,
    tick_sz=0.1,
    min_sz=0.0001,
)


def make_map() -> StaticInstrumentMap:
    return StaticInstrumentMap({"BTCUSDT": BTC})


class FakeGateway:
    """Records orders; configurable pending/position for reconcile."""

    def __init__(self) -> None:
        self.placed: list[Any] = []
        self.cancelled: list[tuple[str, str]] = []
        self.pending_orders: list[Any] = []
        self.position: Any | None = None

    def place(self, req: Any) -> Any:
        from okx.src.domain import OrderAck

        self.placed.append(req)
        return OrderAck(
            ok=True, order_id=f"o{len(self.placed)}", cl_ord_id=req.cl_ord_id
        )

    def cancel(self, inst_id: str, order_id: str) -> None:
        self.cancelled.append((inst_id, order_id))

    def amend(self, req: Any) -> Any:
        from okx.src.domain import OrderAck

        return OrderAck(ok=True, order_id=req.order_id)

    def pending(self, inst_id: str) -> list[Any]:
        return self.pending_orders

    def open_position(self, inst_id: str) -> Any | None:
        return self.position


class FakeSignals:
    """Emits a fixed signal list per on_candle call."""

    def __init__(self, signals: list[dict[str, Any]] | None = None) -> None:
        self.signals = signals or [
            {
                "direction": "long",
                "size": 0.5,
                "entry_price": 50_000.1234,
            }
        ]
        self.calls: list[Any] = []

    def on_candle(self, batch: Any) -> list[dict[str, Any]]:
        self.calls.append(batch)
        return self.signals


class ApproveGate:
    """RiskGate fake: approves everything."""

    def check(
        self,
        inst_id: str,
        direction: Direction,
        entry_price: float,
        size: float,
    ) -> Any:
        from risk.engine import Decision

        return Decision(approve=True, size=size)


class RejectGate:
    """RiskGate fake: rejects with a reason."""

    def check(
        self,
        inst_id: str,
        direction: Direction,
        entry_price: float,
        size: float,
    ) -> Any:
        from risk.engine import Decision

        return Decision(approve=False, reason="cap: too large", rule="cap")


class FakeStore:
    """Fill journal + dedupe keys + reject audit."""

    def __init__(self) -> None:
        self.fills: list[tuple[Any, ...]] = []
        self.rejects: list[tuple[str, int, str]] = []
        self.last_ts: dict[str, int] = {}

    def save_fill(
        self, inst_id: str, ts: int, side: str, size: float, price: float
    ) -> None:
        self.fills.append((inst_id, ts, side, size, price))
        self.last_ts[inst_id] = ts

    def last_candle_ts(self, inst_id: str) -> int:
        return self.last_ts.get(inst_id, 0)

    def record_reject(self, inst_id: str, ts: int, reason: str) -> None:
        self.rejects.append((inst_id, ts, reason))


class FakeSink:
    """Collects everything pushed."""

    def __init__(self) -> None:
        self.pushed: list[tuple[str, Any]] = []

    def push(self, queue: str, payload: Any) -> None:
        self.pushed.append((queue, payload))


class FakeTransport:
    """Fake VenueTransport with canned REST responses."""

    def __init__(
        self, responses: dict[str, dict[str, Any]] | None = None
    ) -> None:
        self.responses = responses or {}
        self.requests: list[tuple[str, str]] = []
        self.sent: list[dict[str, Any]] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def recv(self) -> dict[str, Any] | None:
        return None

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.requests.append((method, path))
        for key, resp in self.responses.items():
            if path.startswith(key):
                return resp
        return {"code": "0", "data": []}

    @property
    def connected(self) -> bool:
        return self._connected
