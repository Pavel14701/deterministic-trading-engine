"""L1 ports: the single DI seam (TZ-15 section 5.1).

Protocols only; implementations live in L3/L4. L2 depends on nothing
else. Cross-cutting services (Risk Engine, DSL) reach the loop through
``RiskGate``/``SignalSource`` - okx never imports backtest or dsl.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from okx.src.domain import (
    AmendRequest,
    InstrumentSpec,
    OrderAck,
    OrderRequest,
    OrderState,
    Position,
)


if TYPE_CHECKING:
    from contracts import OhlcvBatch
    from okx.src.domain import Direction


@runtime_checkable
class VenueTransport(Protocol):
    """Bare transport (L4 behind); no OKX protocol knowledge."""

    async def connect(self) -> None:
        """Open the transport."""

    async def close(self) -> None:
        """Close the transport."""

    async def send(self, payload: dict[str, Any]) -> None:
        """Send one raw payload."""

    async def recv(self) -> dict[str, Any] | None:
        """Receive one raw message; None on close."""

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous REST call; parsed JSON dict."""

    @property
    def connected(self) -> bool:
        """True while the transport is open."""


@runtime_checkable
class MarketDataSource(Protocol):
    """L2 <- L3: normalized market data."""

    def candles_history(self, inst_id: str, bar: str, n: int) -> OhlcvBatch:
        """Last ``n`` closed bars as a canon batch."""

    def subscribe_candles(self, inst_id: str, bar: str) -> None:
        """Subscribe the WS candle channel."""

    def instruments(self, inst_type: str) -> list[InstrumentSpec]:
        """Trading specs for an instrument type."""


@runtime_checkable
class OrderGateway(Protocol):
    """L2 <- L3: execution; the only place knowing the trade API."""

    def place(self, req: OrderRequest) -> OrderAck:
        """Place an order; returns the venue ack."""

    def cancel(self, inst_id: str, order_id: str) -> None:
        """Cancel one order."""

    def amend(self, req: AmendRequest) -> OrderAck:
        """Amend size/price of an order."""

    def pending(self, inst_id: str) -> list[OrderState]:
        """Pending-orders snapshot (reconcile)."""

    def open_position(self, inst_id: str) -> Position | None:
        """Current position; None when flat."""


@runtime_checkable
class AccountReader(Protocol):
    """L2 <- L3: portfolio state for the Risk Engine."""

    def balance_available(self, ccy: str) -> float:
        """Available balance in ccy."""

    def portfolio_state(self) -> Any:
        """PortfolioState for the risk engine."""


@runtime_checkable
class InstrumentMap(Protocol):
    """Canonical symbol <-> venue instId + spec."""

    def to_venue(self, canonical: str) -> str:
        """Canonical symbol -> venue instId."""

    def to_canonical(self, inst_id: str) -> str:
        """Venue instId -> canonical symbol."""

    def spec(self, inst_id: str) -> InstrumentSpec:
        """Spec for a venue instId."""


@runtime_checkable
class EventSink(Protocol):
    """Push domain events out (md.ohlcv / audit / log)."""

    def push(self, queue: str, payload: Any) -> None:
        """Emit a payload to a named sink."""


@runtime_checkable
class RiskGate(Protocol):
    """Single decision entrance; risk.engine behind the port."""

    def check(
        self,
        inst_id: str,
        direction: Direction,
        entry_price: float,
        size: float,
    ) -> Any:
        """Decide: approve with size or reject."""


@runtime_checkable
class SignalSource(Protocol):
    """DSL behind the port: candles in, signals out."""

    def on_candle(self, batch: OhlcvBatch) -> list[Any]:
        """Evaluate signals on a confirmed batch."""


@runtime_checkable
class StateStore(Protocol):
    """Fill journal / last snapshot (reconcile source of truth)."""

    def save_fill(
        self, inst_id: str, ts: int, side: str, size: float, price: float
    ) -> None:
        """Journal the fill / the reject."""

    def last_candle_ts(self, inst_id: str) -> int:
        """Last processed bar-open ms per instrument."""

    def record_reject(self, inst_id: str, ts: int, reason: str) -> None:
        """Journal a risk reject for the audit."""
