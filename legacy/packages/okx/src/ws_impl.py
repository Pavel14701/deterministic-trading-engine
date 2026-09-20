"""L4 WebSocket transport: websockets against OKX public WS (TZ-15).

Bare transport: connect/send/recv of dicts (JSON). No OKX protocol —
login/subscribe framing lives in L3. Reconnect with backoff is the
caller's (L2) job via ``okx.src.reconnect``.
"""

from __future__ import annotations

import json

from typing import Any

import websockets.asyncio.client


class WsTransport:
    """Async WS transport for the OKX public WS endpoint."""

    def __init__(
        self, url: str = "wss://ws.okx.com:8443/ws/v5/business"
    ) -> None:
        self.url = url
        self._ws: Any | None = None

    async def connect(self) -> None:
        """Open the WS connection (idempotent)."""
        if self._ws is not None:
            return
        self._ws = await websockets.asyncio.client.connect(self.url)

    async def close(self) -> None:
        """Close the WS connection (idempotent)."""
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send(self, payload: dict[str, Any]) -> None:
        """Send one JSON payload (subscribe/login frames)."""
        if self._ws is None:
            raise ConnectionError("ws not connected")
        await self._ws.send(json.dumps(payload))

    async def recv(self) -> dict[str, Any] | None:
        """Receive one JSON message; None on clean close.

        OKX sends literal ``pong`` text frames for heartbeats; those
        are swallowed here (they carry no data).
        """
        if self._ws is None:
            raise ConnectionError("ws not connected")
        raw = await self._ws.recv()
        if raw == "pong":
            return None
        obj: dict[str, Any] = json.loads(raw)
        return obj

    @property
    def connected(self) -> bool:
        """True while the socket is open."""
        return self._ws is not None
