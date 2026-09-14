"""Live smoke tests against the real OKX public API.

Skipped unless OKX is reachable (integration marker, testing
convention section 2: no hard network dependency in the suite).
"""

from __future__ import annotations

import os
import socket

import pytest

from okx.src.collector import LiveCollector
from okx.src.config import OkxConfig
from okx.src.http_impl import HttpTransport
from okx.src.okx_client import OkxClient
from okx.src.ws_impl import WsTransport
from okx.tests.fakes import FakeSink


def _okx_reachable() -> bool:
    """TCP probe of the REST host, 3 s budget."""
    try:
        with socket.create_connection(("www.okx.com", 443), timeout=3):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OKX_LIVE_SMOKE") != "1" or not _okx_reachable(),
        reason="live OKX smoke disabled (set OKX_LIVE_SMOKE=1)",
    ),
]


def test_rest_history_returns_valid_canon_candles() -> None:
    cfg = OkxConfig()
    client = OkxClient(HttpTransport(cfg.rest_base_url))  # type: ignore[arg-type]
    batch = client.candles_history("BTC-USDT", "1m", 5)
    assert batch.inst_id == "BTC-USDT"
    assert len(batch.candles) == 5
    for c in batch.candles:
        assert c.ts > 0
        assert c.low <= c.high
        assert c.low <= c.close <= c.high
        assert c.low <= c.open <= c.high
        assert c.volume >= 0.0
    # strictly ordered bar-open timestamps, ms, descending (REST order)
    ts = [c.ts for c in batch.candles]
    assert ts == sorted(ts, reverse=True)
    assert all(t % 60_000 == 0 for t in ts)


def test_rest_instruments_spec() -> None:
    from okx.src.domain import InstType

    cfg = OkxConfig()
    client = OkxClient(HttpTransport(cfg.rest_base_url))  # type: ignore[arg-type]
    specs = client.instruments(InstType.SPOT)
    btc = [s for s in specs if s.inst_id == "BTC-USDT"]
    assert btc, "BTC-USDT must exist on OKX SPOT"
    assert btc[0].tick_sz > 0 and btc[0].lot_sz > 0


def test_ws_stream_receives_confirmed_candle() -> None:
    import asyncio

    async def run() -> int:
        cfg = OkxConfig()
        sink = FakeSink()
        ws = WsTransport(cfg.ws_public_url)
        http = HttpTransport(cfg.rest_base_url)
        client = OkxClient(http)  # type: ignore[arg-type]
        collector = LiveCollector(
            transport=ws,  # type: ignore[arg-type]
            source=client,  # type: ignore[arg-type]
            sink=sink,
            inst_ids=list(cfg.inst_ids),
            bar=cfg.bar,
            warmup=0,
        )
        try:
            return await asyncio.wait_for(
                collector.run(max_events=1), timeout=120.0
            )
        finally:
            await ws.close()
            http.close()

    assert asyncio.run(run()) == 1
