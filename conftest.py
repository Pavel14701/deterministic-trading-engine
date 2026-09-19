"""Root pytest configuration.

Tags every collected test with the marker of its owning package so
``-m ai`` / ``-m ta`` work from the repo root.  The research suite lives
in ``tests/`` (package ``ai``); ``ta/`` is vendored and excluded from
the default run (one known upstream failure, see legacy/MANIFEST.md).
"""

from __future__ import annotations

import pathlib

import pytest


def pytest_collection_modifyitems(items) -> None:
    """Tag every test with the marker of its owning package."""
    root = pathlib.Path(__file__).resolve().parent
    services = {"tests": "ai", "ai": "ai", "ta": "ta", "dsl": "dsl"}
    for item in items:
        try:
            rel = pathlib.Path(str(item.path)).resolve().relative_to(root)
        except ValueError:
            continue
        for svc, marker in services.items():
            if svc in rel.parts:
                item.add_marker(getattr(pytest.mark, marker))
                break
