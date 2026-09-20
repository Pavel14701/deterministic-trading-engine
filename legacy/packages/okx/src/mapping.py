"""Normalization OKX payload -> T-Invest canon (TZ-15 section 4).

Every rule from the spec's table lives here and only here:
strings->float, ts is bar-open ms, ``confirm`` gates CandleClosed,
volume semantics by instType (SPOT = base ``vol``; SWAP = ``vol`` x
``ctVal``), deterministic price/size rounding by tickSz/lotSz, and the
bidirectional bar map.
"""

from __future__ import annotations

from typing import Any

from contracts import Candle
from okx.src.domain import Direction, InstrumentSpec


# --------------------------------------------------------------------- #
# Bar map: canonical id <-> OKX bar (completeness tested both ways)
# --------------------------------------------------------------------- #

BAR_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1Dutc",
    "1w": "1W",
}

BAR_MAP_REVERSE = {v: k for k, v in BAR_MAP.items()}


def okx_bar(canonical: str) -> str:
    """Canonical bar id -> OKX ``bar`` value; ValueError if unknown."""
    try:
        return BAR_MAP[canonical]
    except KeyError:
        raise ValueError(f"unknown canonical bar: {canonical!r}") from None


def canonical_bar(okx: str) -> str:
    """OKX ``bar`` value -> canonical id; ValueError if unknown."""
    try:
        return BAR_MAP_REVERSE[okx]
    except KeyError:
        raise ValueError(f"unknown OKX bar: {okx!r}") from None


# --------------------------------------------------------------------- #
# Candle row -> canon
# --------------------------------------------------------------------- #


def candle_from_rest_row(
    row: list[str], inst_type: str, ct_val: float
) -> Candle:
    """``/market/candles`` row -> canon ``Candle``.

    Row: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]; str.
    ts is the bar OPEN time in ms. Volume: SPOT = base ``vol``;
    SWAP/FUTURES = ``vol`` (contracts) x ``ctVal`` -> base volume.
    """
    vol = float(row[5])
    if inst_type != "SPOT":
        vol = vol * ct_val
    return Candle(
        inst_id="",  # filled by the caller (client knows the instId)
        ts=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=vol,
    )


def is_confirmed(confirm: str | int) -> bool:
    """OKX ``confirm`` flag -> bar is closed (only 1 builds signals)."""
    return str(confirm) == "1"


def candle_from_ws(msg: dict[str, Any]) -> list[Candle]:
    """WS ``candle{bar}`` channel message -> canon candles.

    Data rows are the same shape as REST rows minus ``confirm``-as-
    string: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm].
    """
    out: list[Candle] = []
    inst_type = str(msg.get("instType", "SPOT"))
    ct_val = float(msg.get("ctVal", 1.0) or 1.0)
    inst_id = str(msg.get("instId", ""))
    for row in msg.get("data", []):
        c = candle_from_rest_row(row, inst_type, ct_val)
        out.append(
            Candle(
                inst_id=inst_id,
                ts=c.ts,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
        )
    return out


# --------------------------------------------------------------------- #
# Deterministic rounding (lotSz / tickSz)
# --------------------------------------------------------------------- #


def round_size(spec: InstrumentSpec, size: float) -> float:
    """Round size DOWN to the ``lotSz`` grid (never oversize)."""
    lot = spec.lot_sz
    rounded = int(size / lot + 1e-9) * lot
    return round(rounded, 12)


def round_price(spec: InstrumentSpec, price: float) -> float:
    """Round price to the ``tickSz`` grid (nearest)."""
    tick = spec.tick_sz
    return round(round(price / tick) * tick, 12)


def check_min_size(spec: InstrumentSpec, size: float) -> bool:
    """True if the rounded size still satisfies ``minSz``."""
    return size + 1e-12 >= spec.min_sz


# --------------------------------------------------------------------- #
# Order side mapping (net vs long_short_mode)
# --------------------------------------------------------------------- #


def order_side(direction: Direction, pos_mode: str) -> tuple[str, str]:
    """Direction -> (side, posSide) per account ``posMode``.

    net: side=buy/sell, posSide=net. long_short_mode: side=buy with
    posSide=long/short (opening side follows direction).
    """
    if pos_mode == "long_short_mode":
        side = "buy" if direction is Direction.LONG else "sell"
        return side, direction.value
    side = "buy" if direction is Direction.LONG else "sell"
    return side, "net"


def make_cl_ord_id(inst_id: str, ts: int, direction: Direction) -> str:
    """Deterministic idempotency key per (inst, bar-open-ts, side)."""
    return f"dte-{inst_id}-{ts}-{direction.value}"
