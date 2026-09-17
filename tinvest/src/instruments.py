"""Instrument resolution for the T-Invest API.

The pipeline accepts instruments as FIGI, bare ticker, or
``TICKER@CLASS_CODE`` (e.g. ``SBER@MOEX``, ``SI@FORTS``).  Anything that
is not a FIGI is resolved through ``FindInstrument``; results are cached
in a JSON file so repeated pipeline runs do not re-query.
"""

from __future__ import annotations

import json
import re

from pathlib import Path

from tinvest.src.fetch import api_post


_FIGI_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def parse_instrument(inst: str) -> dict[str, str]:
    """Split an instrument spec into its parts.

    Args:
        inst: FIGI (e.g. ``BBG004730N88``), bare ticker
            (``SBER``), or ``TICKER@CLASS`` (``SBER@MOEX``).

    Returns:
        A dict with ``spec`` (the input as given) plus, when known,
        ``ticker`` and ``class_code``.

    """
    spec = inst.strip()
    if _FIGI_RE.match(spec):
        return {"spec": spec, "figi": spec}
    if "@" in spec:
        ticker, class_code = spec.split("@", 1)
        return {"spec": spec, "ticker": ticker, "class_code": class_code}
    return {"spec": spec, "ticker": spec}


def resolve_instrument(
    inst: str, token: str | None, cache_path: Path | None = None
) -> str:
    """Resolve an instrument spec to a FIGI.

    Args:
        inst: FIGI, bare ticker, or ``TICKER@CLASS``.
        token: T-Invest API token (``None`` falls back to the
            ``T_INVEST_TOKEN`` environment variable).
        cache_path: Optional JSON file used to memoise resolutions.

    Returns:
        The FIGI of the instrument (first FindInstrument match).

    Raises:
        RuntimeError: If the instrument cannot be resolved or the
            query is ambiguous with a class code mismatch.

    """
    parts = parse_instrument(inst)
    figi = parts.get("figi")
    if figi:
        return figi

    cache: dict[str, str] = {}
    if cache_path is not None and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if parts["spec"] in cache:
            return cache[parts["spec"]]

    body: dict[str, str] = {"query": parts["ticker"]}
    if "class_code" in parts:
        body["classCode"] = parts["class_code"]
    resp = api_post(
        "tinkoff.public.invest.api.contract.v1.InstrumentsService/"
        "FindInstrument",
        body=body,
        token=token,
    )
    instruments = resp.get("instruments") or []
    if not instruments:
        raise RuntimeError(f"T-Invest: instrument not found: {inst!r}")
    resolved = str(instruments[0]["figi"])

    if cache_path is not None:
        cache[parts["spec"]] = resolved
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return resolved
