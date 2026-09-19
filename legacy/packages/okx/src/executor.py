"""L2 executor use-case: place an order with venue rounding (TZ-15)."""

from __future__ import annotations

from okx.src.domain import OrderAck, OrderRequest
from okx.src.mapping import check_min_size, round_price, round_size
from okx.src.ports import InstrumentMap, OrderGateway


def execute(
    req: OrderRequest,
    instruments: InstrumentMap,
    gateway: OrderGateway,
) -> OrderAck:
    """Resolve the request against the instrument spec, then place.

    Deterministic: size rounds down to lotSz, price to tickSz;
    below minSz the request is refused before touching the venue.
    """
    spec = instruments.spec(req.inst_id)
    size = round_size(spec, req.size)
    if not check_min_size(spec, size):
        return OrderAck(
            ok=False, cl_ord_id=req.cl_ord_id, reason="below minSz"
        )
    price = round_price(spec, req.price) if req.price is not None else None
    resolved = OrderRequest(
        inst_id=req.inst_id,
        direction=req.direction,
        size=size,
        price=price,
        td_mode=req.td_mode,
        cl_ord_id=req.cl_ord_id,
        reduce_only=req.reduce_only,
    )
    return gateway.place(resolved)
