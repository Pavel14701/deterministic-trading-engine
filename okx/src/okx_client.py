"""L3 OKX client: protocol, signing, startup checks (TZ-15 section 3)."""

from __future__ import annotations

import json
import time

from typing import Any

from contracts import Candle, OhlcvBatch
from okx.src.domain import (
    InstrumentSpec,
    InstType,
    PosMode,
    StartupRefusalError,
)
from okx.src.mapping import candle_from_rest_row, okx_bar
from okx.src.ports import VenueTransport


class OkxClient:
    """REST-side OKX protocol over a VenueTransport (L4)."""

    def __init__(
        self,
        transport: VenueTransport,
        api_key: str = "",
        secret: str = "",
        passphrase: str = "",
    ) -> None:
        self.transport = transport
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase

    # --------------------------------------------------------------- #
    # Startup check (TZ-00 determinism: mismatch = refuse to start)
    # --------------------------------------------------------------- #

    def check_account(self, expected_pos_mode: PosMode) -> None:
        """``GET /account/config`` posMode must match the venue config."""
        resp = self.transport.request("GET", "/account/config")
        data = resp.get("data", [{}])[0]
        actual = str(data.get("posMode", ""))
        if actual != expected_pos_mode.value:
            raise StartupRefusalError(
                f"posMode mismatch: venue={actual!r}, "
                f"config={expected_pos_mode.value!r}"
            )

    # --------------------------------------------------------------- #
    # Market data (REST only for history/snapshots, WS-first otherwise)
    # --------------------------------------------------------------- #

    def instruments(self, inst_type: InstType) -> list[InstrumentSpec]:
        """``GET /public/instruments`` -> specs with lot/tick/ctVal."""
        resp = self.transport.request(
            "GET", f"/public/instruments?instType={inst_type.value}"
        )
        out: list[InstrumentSpec] = []
        for row in resp.get("data", []):
            out.append(
                InstrumentSpec(
                    inst_id=str(row["instId"]),
                    inst_type=str(row.get("instType", inst_type.value)),
                    lot_sz=float(row.get("lotSz", 1.0)),
                    tick_sz=float(row.get("tickSz", 0.1)),
                    min_sz=float(row.get("minSz", 1.0)),
                    ct_val=float(row.get("ctVal", 1.0) or 1.0),
                )
            )
        return out

    def candles_history(
        self, inst_id: str, bar: str, n: int, inst_type: str = "SPOT"
    ) -> OhlcvBatch:
        """``GET /market/candles`` -> canon batch (bar-open ts ms)."""
        path = f"/market/candles?instId={inst_id}&bar={okx_bar(bar)}&limit={n}"
        resp = self.transport.request("GET", path)
        spec_ct = 1.0
        if inst_type != "SPOT":
            spec_ct = self._contract_value(inst_id)
        rows = resp.get("data", [])
        candles = []
        for row in rows:
            c = candle_from_rest_row(row, inst_type, spec_ct)
            candles.append(
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
        return OhlcvBatch(inst_id=inst_id, candles=candles)

    def _contract_value(self, inst_id: str) -> float:
        """CtVal for a derivatives instrument (1.0 fallback)."""
        resp = self.transport.request(
            "GET", f"/public/instruments?instId={inst_id}"
        )
        data = resp.get("data", [])
        if not data:
            return 1.0
        return float(data[0].get("ctVal", 1.0) or 1.0)

    # --------------------------------------------------------------- #
    # Signed request helpers (used by L3 gateway in the live contour)
    # --------------------------------------------------------------- #

    def signed_headers(
        self, method: str, path: str, body: str
    ) -> dict[str, str]:
        """Build OK-ACCESS-* headers for a signed REST call."""
        from okx.src.signing import sign_request

        ts = str(time.time())
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign_request(
                self.secret, ts, method, path, body
            ),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }

    def ws_login_payload(self) -> dict[str, Any]:
        """Build the private-WS ``login`` op payload."""
        from okx.src.signing import sign_ws_login

        ts = str(time.time())
        body = json.dumps(
            {"apiKey": self.api_key, "passphrase": self.passphrase}
        )
        return {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": ts,
                    "sign": sign_ws_login(self.secret, ts, body),
                }
            ],
        }
