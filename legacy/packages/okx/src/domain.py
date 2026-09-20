"""L1 domain: OKX venue types (TZ-15 section 5).

No I/O, no external frameworks. msgspec structs only; the canon types
(``Candle``, ``OhlcvBatch``) come from ``contracts`` and are the target
of normalization at the boundary.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import msgspec


class InstType(str, Enum):
    """OKX instrument type."""

    SPOT = "SPOT"
    SWAP = "SWAP"
    FUTURES = "FUTURES"


class PosMode(str, Enum):
    """OKX account position mode."""

    NET = "net_mode"
    LONG_SHORT = "long_short_mode"


class TdMode(str, Enum):
    """OKX trade mode (per order)."""

    CASH = "cash"
    CROSS = "cross"
    ISOLATED = "isolated"


class Direction(str, Enum):
    """Canonical long/short direction (TZ-02 canon)."""

    LONG = "long"
    SHORT = "short"


class InstrumentSpec(msgspec.Struct, frozen=True):
    """Deterministic trading constraints for one instrument."""

    inst_id: str
    inst_type: str
    lot_sz: float
    tick_sz: float
    min_sz: float
    ct_val: float = 1.0  # contract value (SWAP); 1.0 for SPOT


class OrderRequest(msgspec.Struct, frozen=True):
    """A fully-resolved order the executor wants to place."""

    inst_id: str
    direction: Direction
    size: float
    price: float | None = None  # None => market
    td_mode: str = "cash"
    cl_ord_id: str = ""
    reduce_only: bool = False


class OrderAck(msgspec.Struct, frozen=True):
    """Venue acknowledgement for a placed/amended order."""

    ok: bool
    order_id: str = ""
    cl_ord_id: str = ""
    reason: str = ""


class OrderState(msgspec.Struct, frozen=True):
    """Snapshot of a venue order (pending list / reconcile)."""

    order_id: str
    inst_id: str
    side: str
    size: float
    filled: float
    state: str


class AmendRequest(msgspec.Struct, frozen=True):
    """Amend an existing order."""

    inst_id: str
    order_id: str
    new_size: float | None = None
    new_price: float | None = None


class Position(msgspec.Struct, frozen=True):
    """Net position on one instrument."""

    inst_id: str
    size: float  # signed; positive = long
    avg_price: float


class OkxEvent(msgspec.Struct, frozen=True, tag=True):
    """One event flowing through the event loop (TZ-15 section 6)."""

    kind: str  # candle_closed | order_filled | algo_triggered |
    # position_updated | account_updated | ws_disconnected
    inst_id: str
    ts: int = 0  # event time, unix ms
    payload: dict[str, Any] = msgspec.field(default_factory=dict)


class StartupRefusalError(RuntimeError):
    """Raised when the venue config mismatches ours (TZ-00 determinism)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
