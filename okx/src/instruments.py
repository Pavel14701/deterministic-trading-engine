"""Static InstrumentMap: canonical symbol <-> venue instId (TZ-15)."""

from __future__ import annotations

from okx.src.domain import InstrumentSpec, StartupRefusalError


class StaticInstrumentMap:
    """Dict-driven map from venue config (TZ-10 will move it to PG)."""

    def __init__(self, mapping: dict[str, InstrumentSpec]) -> None:
        # key: canonical symbol; spec carries the venue inst_id.
        self._by_canonical = dict(mapping)
        self._by_venue = {
            spec.inst_id: (canon, spec) for canon, spec in mapping.items()
        }

    def to_venue(self, canonical: str) -> str:
        """Canonical symbol -> OKX instId."""
        try:
            return self._by_canonical[canonical].inst_id
        except KeyError:
            raise StartupRefusalError(
                f"no instrument mapping for {canonical!r}"
            ) from None

    def to_canonical(self, inst_id: str) -> str:
        """OKX instId -> canonical symbol."""
        try:
            return self._by_venue[inst_id][0]
        except KeyError:
            raise StartupRefusalError(
                f"unknown venue instrument {inst_id!r}"
            ) from None

    def spec(self, inst_id: str) -> InstrumentSpec:
        """Spec by venue instId."""
        try:
            return self._by_venue[inst_id][1]
        except KeyError:
            raise StartupRefusalError(
                f"unknown venue instrument {inst_id!r}"
            ) from None
