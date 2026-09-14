"""L2 collector use-case: candles -> md.ohlcv (TZ-15).

Live mode: WS ``candle{bar}`` channel -> normalize -> confirm gate ->
OhlcvBatch -> EventSink. Warm-up pulls closed-bar history over REST
before the stream starts, so indicators see a full lookback window.
"""

from __future__ import annotations

import asyncio

from typing import Any

from contracts import OhlcvBatch
from okx.src.mapping import BAR_MAP, candle_from_rest_row, is_confirmed
from okx.src.ports import EventSink, MarketDataSource, VenueTransport


def publish(batch: OhlcvBatch, sink: EventSink) -> None:
    """Push a normalized batch to the md.ohlcv sink."""
    sink.push("md.ohlcv", batch)


def _subscribe_frame(inst_id: str, bar: str) -> dict[str, Any]:
    """OKX WS subscribe frame for the candle channel."""
    return {
        "op": "subscribe",
        "args": [
            {"channel": f"candle{BAR_MAP[bar]}", "instId": inst_id}
        ],
    }


def batch_from_ws(msg: dict[str, Any]) -> OhlcvBatch | None:
    """WS ``candle{bar}`` message -> canon batch of CONFIRMED candles.

    Unconfirmed rows (confirm=0) are dropped here: the collector never
    publishes a forming bar. Returns None when nothing is confirmed.
    """
    rows = [
        r
        for r in msg.get("data", [])
        if isinstance(r, list) and len(r) >= 9
    ]
    confirmed = [r for r in rows if is_confirmed(str(r[8]))]
    if not confirmed:
        return None
    inst_type = str(msg.get("instType", "SPOT"))
    ct_val = float(msg.get("ctVal", 1.0) or 1.0)
    inst_id = str(
        msg.get("instId") or msg.get("arg", {}).get("instId", "")
    )
    candles = []
    for row in confirmed:
        c = candle_from_rest_row(row, inst_type, ct_val)
        candles.append(
            type(c)(
                inst_id=inst_id,
                ts=c.ts,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
        )
    return OhlcvBatch(inst_id=inst_id, candles=candles)


class LiveCollector:
    """Warm-up over REST, then stream confirmed candles from WS."""

    def __init__(
        self,
        transport: VenueTransport,
        source: MarketDataSource,
        sink: EventSink,
        inst_ids: list[str],
        bar: str = "1m",
        warmup: int = 100,
    ) -> None:
        self.transport = transport
        self.source = source
        self.sink = sink
        self.inst_ids = inst_ids
        self.bar = bar
        self.warmup = warmup

    def warm_up(self) -> int:
        """Pull REST history for every instrument; returns bar count."""
        total = 0
        for inst_id in self.inst_ids:
            batch = self.source.candles_history(
                inst_id, self.bar, self.warmup
            )
            publish(batch, self.sink)
            total += len(batch.candles)
        return total

    async def run(self, max_events: int | None = None) -> int:
        """Subscribe and stream; returns processed confirmed events.

        ``max_events`` bounds the loop (tests / graceful stops); None
        streams until the socket closes.
        """
        await self.transport.connect()
        for inst_id in self.inst_ids:
            await self.transport.send(_subscribe_frame(inst_id, self.bar))
        seen = 0
        while max_events is None or seen < max_events:
            msg = await self.transport.recv()
            if msg is None:
                continue
            if msg.get("event") == "subscribe":
                continue
            batch = batch_from_ws(msg)
            if batch is None:
                continue
            publish(batch, self.sink)
            seen += 1
        return seen

    def stop(self) -> None:
        """Request stop by closing the transport (fire-and-forget)."""
        asyncio.get_event_loop().create_task(self.transport.close())

