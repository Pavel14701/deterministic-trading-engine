"""Per-event feature matrix from a JSON-configurable DSL spec.

Where :mod:`engine.mfe_mae` *discovers* events (bars where a DSL
signal fires), this module *describes* them: a ``FeatureSpec`` is an
ordered list of named DSL expressions evaluated at each event bar,
producing the feature rows a downstream ranker/model consumes.

Config (``FeatureSpec``) is a plain serializable dataclass::

    spec = FeatureSpec(
        features=(
            FeatureDef(name="mom3", expr="close[3] / atr(period=14)"),
            FeatureDef(name="above_sma", expr="close > sma(period=20)"),
            FeatureDef(name="rng", expr="let r = high - low in r / close"),
        )
    )
    feats = collect_features(df, spec, event_idx=[10, 42, 43])

Semantics (same contract as :mod:`engine.mfe_mae` - no look-ahead by
construction):

1. Every expression is evaluated with a context bound to the event
   bar ``i`` (prefix ``[0, i]``); ``name[k]`` resolves to bar
   ``i - k`` and pre-start reads yield NaN (warm-up) - never an error,
   never a future value.  Indicators are causal, so a feature value
   depends only on bars ``<= i``: truncating the frame after the last
   event cannot change any row (prefix invariance - covered by tests).
2. Numeric (feature-style) evaluation: arithmetic, indicator and
   historical expressions keep their numeric value (warm-up NaN
   propagates), while comparison/logical expressions become
   1.0/0.0.  Custom indicator wiring plugs in through
   ``context_factory`` exactly like ``collect_mfe_mae``.
3. Fail fast: names/expressions are validated at spec construction,
   expressions are parsed before any evaluation, and event indices
   are checked (sorted, unique, in range) up front.

Higher-timeframe features use :func:`engine.mtf.asof_join_features`,
which attaches HTF columns under a strict ``known_ts <= ts`` rule (a
resampled bar is visible only once it has fully closed).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

import numpy as np
import polars as pl

from dsl import Context
from dsl.interpreter import Interpreter
from dsl.parser import parse
from engine.dsl_feed import SeriesCache, make_bar_context


__all__ = ("FeatureDef", "FeatureSpec", "collect_features")

_RESERVED_NAMES = frozenset({"event_idx", "event_ts"})


@dataclass(frozen=True)
class FeatureDef:
    """One named feature: a DSL expression evaluated at the event bar."""

    name: str
    expr: str

    def __post_init__(self) -> None:
        """Fail fast on a bad name or a malformed expression."""
        if not self.name.isidentifier() or self.name in _RESERVED_NAMES:
            raise ValueError(
                "feature name must be a valid identifier outside "
                f"{sorted(_RESERVED_NAMES)}, got {self.name!r}"
            )
        parse(self.expr)


@dataclass(frozen=True)
class FeatureSpec:
    """Ordered set of :class:`FeatureDef` (JSON-serializable)."""

    features: tuple[FeatureDef, ...]

    def __post_init__(self) -> None:
        """Fail fast on an empty or duplicated feature set."""
        if not self.features:
            raise ValueError("FeatureSpec needs at least one feature")
        names = [f.name for f in self.features]
        if len(set(names)) != len(names):
            dups = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate feature names: {dups}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (round-trips via ``from_dict``)."""
        return {"features": [asdict(f) for f in self.features]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeatureSpec":
        """Rebuild a spec from :meth:`to_dict` output."""
        return cls(features=tuple(FeatureDef(**fd) for fd in d["features"]))


def collect_features(
    df: pl.DataFrame,
    spec: FeatureSpec,
    event_idx: Any,
    context_factory: Callable[[SeriesCache, int], Context] | None = None,
) -> pl.DataFrame:
    """Evaluate every spec feature at every event bar.

    Args:
        df: Canonical bar frame (needs ``ts, open, high, low, close``;
            ``volume`` optional, accessed only if a feature uses it).
        spec: feature spec (see :class:`FeatureSpec`).
        event_idx: bar indices to describe; must be sorted, unique and
            within the frame.
        context_factory: optional ``(cache, bar_idx) -> Context`` hook
            for custom indicator wiring; defaults to
            :func:`engine.dsl_feed.make_bar_context`.

    Returns:
        One row per event: ``event_idx, event_ts`` plus one Float64
        column per feature, sorted by ``event_idx``.  Empty (but
        correctly typed) for empty ``event_idx``.

    Raises:
        ValueError: if ``event_idx`` is unsorted, duplicated or out
            of range.
        ParseError: if a feature expression does not parse.
        DSLError: if an expression references unknown indicators or
            invalid parameters during evaluation.

    """
    if "ts" not in df.columns:
        raise ValueError("df missing required column: ts")
    ev = np.asarray(event_idx, dtype=np.int64)
    n = df.height
    if ev.size and (np.any(np.diff(ev) <= 0) or ev[0] < 0 or ev[-1] >= n):
        raise ValueError(
            "event_idx must be strictly increasing, unique and within "
            f"[0, {n}); got {ev.tolist()}"
        )
    asts = [(f, parse(f.expr)) for f in spec.features]
    cache = SeriesCache(df)
    make_ctx = context_factory or make_bar_context
    ts = df["ts"].to_numpy().astype(np.int64)
    rows: list[dict[str, Any]] = []
    for i in ev:
        interp = Interpreter(make_ctx(cache, int(i)))
        row: dict[str, Any] = {"event_idx": int(i), "event_ts": int(ts[i])}
        for fdef, ast in asts:
            row[fdef.name] = interp.visit_numeric(ast)
        rows.append(row)
    schema: dict[str, Any] = {
        "event_idx": pl.Int64,
        "event_ts": pl.Int64,
        **{f.name: pl.Float64 for f in spec.features},
    }
    return pl.DataFrame(rows, schema=schema)
