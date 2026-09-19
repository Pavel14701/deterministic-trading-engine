"""REST client for the T-Invest (Tinkoff Invest) API.

Auth: ``T_INVEST_TOKEN`` environment variable (or an explicit token
argument).  All market-data calls are POSTs on the gRPC-gateway
(``/tinkoff.public.invest.api.contract.v1.MarketDataService/...``) with
JSON bodies; the responses carry camelCase keys.
"""

from __future__ import annotations

import os
import time

import niquests


BASE_URL = "https://invest-public-api.ru"
_API_PREFIX = "/rest"
_PAGE_SLEEP = 0.25  # T-Invest market-data tier is heavily rate limited


def api_post(
    method: str,
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    retries: int = 4,
) -> dict:
    """POST a gRPC-gateway method and return the JSON payload.

    Args:
        method: Full service method path, e.g.
            ``tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles``.
        body: JSON body (camelCase keys as the gateway expects).
        token: T-Invest token; defaults to the ``T_INVEST_TOKEN`` env var.
        timeout: Per-request timeout in seconds.
        retries: Retry attempts on transport/HTTP errors (with
            linear backoff; also honours ``Retry-After``).

    Returns:
        The decoded JSON response dict.

    Raises:
        RuntimeError: On missing token or when all attempts fail.

    """
    tok = token or os.environ.get("T_INVEST_TOKEN")
    if not tok:
        raise RuntimeError(
            "T-Invest token not provided: set the T_INVEST_TOKEN "
            "environment variable or pass token=..."
        )
    url = f"{BASE_URL}{_API_PREFIX}/{method}"
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = niquests.post(
                url,
                json=body or {},
                headers={
                    "Authorization": f"Bearer {tok}",
                    "Content-Type": "application/json",
                    "x-app-name": "deterministic-trading-engine",
                },
                timeout=timeout,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 5))
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            payload = resp.json()
        except (niquests.RequestException, ValueError) as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
            continue
        return payload
    raise RuntimeError(
        f"T-Invest {method} failed after {retries} attempts"
    ) from last_exc
