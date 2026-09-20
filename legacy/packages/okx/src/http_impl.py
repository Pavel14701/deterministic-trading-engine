"""L4 REST transport: niquests against the OKX public API (TZ-15).

Bare bytes-in/out: no OKX protocol knowledge beyond the base URL and
JSON parsing. Implements the ``VenueTransport`` REST half.
"""

from __future__ import annotations

from typing import Any

import niquests


class HttpTransport:
    """Synchronous REST transport (public endpoints need no signing)."""

    def __init__(self, base_url: str = "https://www.okx.com/api/v5") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: niquests.Session | None = None

    def _ensure_session(self) -> niquests.Session:
        if self._session is None:
            self._session = niquests.Session()
        return self._session

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform a REST call; return the parsed JSON dict.

        Signed calls (private endpoints) are not part of the public
        data scope; the caller passes full headers via ``headers`` on
        the session when that contour opens.
        """
        session = self._ensure_session()
        url = f"{self.base_url}{path}"
        resp = session.request(
            method, url, json=body if body is not None else None
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        return payload

    def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None:
            self._session.close()
            self._session = None

    # --- VenueTransport WS-side stubs (REST-only transport) --------- #

    async def connect(self) -> None:
        """No-op: this transport has no WS half."""

    async def send(self, payload: dict[str, Any]) -> None:
        """Unsupported: use WsTransport for the WS half."""
        raise NotImplementedError("HttpTransport is REST-only")

    async def recv(self) -> dict[str, Any] | None:
        """Unsupported: use WsTransport for the WS half."""
        raise NotImplementedError("HttpTransport is REST-only")

    @property
    def connected(self) -> bool:
        """Session open (REST is connectionless)."""
        return self._session is not None
