"""Reconnect policy for the WS collector (TZ-09 pattern reuse).

Exponential backoff; the collector re-subscribes after each successful
reconnect. A break never loses candles silently: on resume the
collector re-pulls history via REST (reconcile-first principle).
"""

from __future__ import annotations

import asyncio

from okx.src.ports import VenueTransport


class ReconnectPolicy:
    """Exponential backoff parameters (same semantics as TZ-09)."""

    def __init__(
        self,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        factor: float = 2.0,
        max_attempts: int = 10,
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor
        self.max_attempts = max_attempts

    def delay_for(self, attempt: int) -> float:
        """Delay before retry number ``attempt`` (0-based)."""
        return min(self.base_delay * (self.factor**attempt), self.max_delay)


async def connect_with_backoff(
    transport: VenueTransport, policy: ReconnectPolicy
) -> None:
    """Connect retrying with the policy; raise after max_attempts."""
    last: Exception | None = None
    for attempt in range(max(policy.max_attempts, 1)):
        try:
            await transport.connect()
            return
        except Exception as exc:
            last = exc
            await asyncio.sleep(policy.delay_for(attempt))
    if last is not None:
        raise last
