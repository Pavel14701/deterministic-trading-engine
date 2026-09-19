"""Venue config for the okx contour (env/YAML; public-data scope)."""

from __future__ import annotations

import os

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OkxConfig:
    """Public-data venue config; no API keys in this scope."""

    rest_base_url: str = "https://www.okx.com/api/v5"
    ws_public_url: str = "wss://ws.okx.com:8443/ws/v5/business"
    inst_ids: tuple[str, ...] = ("BTC-USDT",)
    bar: str = "1m"
    warmup: int = 100

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> OkxConfig:
        """Build from env with defaults; inst_ids is comma-separated."""
        e = dict(os.environ if env is None else env)
        inst = tuple(
            i.strip()
            for i in e.get("OKX_INST_IDS", "BTC-USDT").split(",")
            if i.strip()
        )
        return OkxConfig(
            rest_base_url=e.get("OKX_REST_URL", "https://www.okx.com/api/v5"),
            ws_public_url=e.get(
                "OKX_WS_URL", "wss://ws.okx.com:8443/ws/v5/business"
            ),
            inst_ids=inst or ("BTC-USDT",),
            bar=e.get("OKX_BAR", "1m"),
            warmup=int(e.get("OKX_WARMUP", "100")),
        )


@dataclass(frozen=True, slots=True)
class CollectorRuntime:
    """Wired live collector parts (transport + source + sink)."""

    config: OkxConfig
    extra: dict[str, object] = field(default_factory=dict)
