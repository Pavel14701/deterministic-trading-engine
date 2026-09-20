"""Universal MFE/MAE collector driven by a DSL signal config.

The collector is *not* tied to any particular entry regime.  A signal
is defined as a DSL expression (see the ``dsl`` package) evaluated
bar-by-bar against OHLCV data plus a set of causal indicators; every
bar where the expression is true becomes a candidate event, and the
collector measures the Maximum Favorable / Adverse Excursion of the
trade that would have been entered there.

Config (``MfeMaeSpec``) is a plain serializable dataclass::

    spec = MfeMaeSpec(
        signal="let rng = high - low in rng > atr(period=14) "
        "and close > sma(period=20)",
        side="long",  # "long" | "short"
        horizon=24,  # bars to walk forward after the fill
        entry="next_open",  # "next_open" | "signal_close"
        atr_period=14,  # normalization ATR (causal, signal bar)
        sl_atr_mult=1.0,  # R unit = sl_atr_mult * ATR(signal bar)
        incomplete="partial",  # "partial" | "drop" near series end
    )
    events = collect_mfe_mae(df, spec)

Execution semantics (no look-ahead by construction):

1. The signal at bar ``i`` is evaluated with a context bound to the
   bar series prefix ``[0, i]``; ``name[k]`` resolves to bar
   ``i - k``.  Indicators are causal (rolling windows never see
   ``> i``), so their full-series values equal their prefix values.
2. Fill: ``next_open`` -> entry at ``open[i + 1]``; ``signal_close``
   -> entry at ``close[i]``.
3. The excursion window starts on the first bar *after* the fill
   moment and spans at most ``horizon`` bars.  For ``next_open`` the
   fill bar itself is included (its high/low unfold after the open
   print); for ``signal_close`` it is not.
4. Normalization uses ``ATR(signal bar i)`` (house causal ATR from
   :func:`engine.features.compute_atr`): ``*_atr = *_abs / ATR`` and
   ``*_r = *_abs / (sl_atr_mult * ATR)``.  IMPORTANT: the R unit here
   is ``sl_atr_mult * ATR(signal bar)`` - a fixed ATR stop.  It is
   NOT the main stack's rule-based ``risk_unit`` (``zone:1.0``,
   ``anchor:st:0.5``, ...); ``mfe_r``/``mae_r`` from this collector
   are therefore not directly comparable to EV-R numbers from the
   stage-D pipeline.  Use ``*_atr``/``*_abs`` as features, or wire a
   rule-based risk unit through ``context_factory`` if needed.
5. ``exit="sl_hit"`` ends the excursion window at the first bar the
   stop is touched (long: ``low <= stop``, short: ``high >= stop``;
   ``stop = entry -/+ sl_atr_mult * ATR(signal bar)``).  The hit bar
   itself is included (its high may print after the intrabar stop
   fill - a slightly generous MFE, the conservative direction for
   stop-head work is to also check ``mae_r``).  ``sl_hit`` records
   whether the stop was touched inside the window in either mode.

Execution caveats: ``entry="signal_close"`` fills at the close of the
signal bar; in live trading that requires a market order in the final
moments of the bar (or an extra bar of slippage) - use it only when
that cost model is acceptable.

MFE/MAE are non-negative magnitudes (clamped at 0).  Available DSL
names: ``open`` ``high`` ``low`` ``close`` ``volume`` plus causal
``sma(period=)`` ``ema(period=)`` ``rsi(period=)`` ``atr(period=)``
(each also accepts the ``.value`` attribute), with ``[k]`` historical
offsets, ``rising``/``falling`` and ``let`` bindings supported by the
DSL itself.  Custom indicator wiring can be supplied via
``collect_mfe_mae``'s ``context_factory`` hook.

Performance note: indicators are precomputed once per parameter set
(O(N)); per-bar work is one AST interpretation.  Signal parsing and
manifest validation happen once per call, so an invalid expression
fails fast before any bar is evaluated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

import numpy as np
import polars as pl

from dsl import Context
from dsl.interpreter import Interpreter
from dsl.parser import parse
from engine.dsl_feed import (
    SeriesCache as _SeriesCache,
    make_bar_context,
)
from engine.features import compute_atr


__all__ = (
    "SIGNAL_TS",
    "MfeMaeSpec",
    "collect_mfe_mae",
    "make_bar_context",
)

_SCHEMA: dict[str, Any] = {  # pl.DataType classes (runtime schema)
    "signal_ts": pl.Int64,
    "entry_ts": pl.Int64,
    "entry_idx": pl.Int64,
    "entry_price": pl.Float64,
    "bars_measured": pl.Int64,
    "mfe_abs": pl.Float64,
    "mae_abs": pl.Float64,
    "mfe_atr": pl.Float64,
    "mae_atr": pl.Float64,
    "mfe_r": pl.Float64,
    "mae_r": pl.Float64,
    "sl_hit": pl.Boolean,
}
SIGNAL_TS = "signal_ts"  # join key for downstream feature merges


@dataclass(frozen=True)
class MfeMaeSpec:
    """DSL-configured MFE/MAE collection spec (JSON-serializable)."""

    signal: str
    side: str = "long"
    horizon: int = 24
    entry: str = "next_open"
    atr_period: int = 14
    sl_atr_mult: float = 1.0
    incomplete: str = "partial"
    exit: str = "horizon"

    def __post_init__(self) -> None:
        """Validate enum-ish fields and positive numerics eagerly."""
        if self.exit not in ("horizon", "sl_hit"):
            raise ValueError(f"exit must be horizon|sl_hit, got {self.exit!r}")
        if self.side not in ("long", "short"):
            raise ValueError(f"side must be long|short, got {self.side!r}")
        if self.entry not in ("next_open", "signal_close"):
            raise ValueError(
                f"entry must be next_open|signal_close, got {self.entry!r}"
            )
        if self.incomplete not in ("partial", "drop"):
            raise ValueError(
                f"incomplete must be partial|drop, got {self.incomplete!r}"
            )
        if self.horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {self.horizon}")
        if self.sl_atr_mult <= 0:
            raise ValueError(
                f"sl_atr_mult must be > 0, got {self.sl_atr_mult}"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (round-trips via ``from_dict``)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MfeMaeSpec":
        """Rebuild a spec from :meth:`to_dict` output."""
        return cls(**d)


def collect_mfe_mae(
    df: pl.DataFrame,
    spec: MfeMaeSpec,
    context_factory: Callable[[_SeriesCache, int], Context] | None = None,
) -> pl.DataFrame:
    """Collect MFE/MAE events for every bar where the DSL signal fires.

    Args:
        df: bar DataFrame; requires ``ts, open, high, low, close``
            (``volume`` optional, accessed only if the signal uses it).
        spec: collection spec (see :class:`MfeMaeSpec`).
        context_factory: optional ``(cache, bar_idx) -> Context`` hook
            for custom indicator wiring; defaults to
            :func:`make_bar_context`.

    Returns:
        One row per event with columns ``signal_ts, entry_ts,
        entry_idx, entry_price, bars_measured, mfe_abs, mae_abs,
        mfe_atr, mae_atr, mfe_r, mae_r`` sorted by signal time.  Empty
        (but correctly typed) if the signal never fires.

    Raises:
        ParseError: if ``spec.signal`` does not parse.
        DSLError: if the signal references unknown indicators or reads
            before the series start during evaluation.

    """
    if "ts" not in df.columns:
        raise ValueError("df missing required column: ts")
    ast = parse(spec.signal)  # fail fast on a malformed config
    cache = _SeriesCache(df)
    make_ctx = context_factory or make_bar_context
    n = df.height
    ts = df["ts"].to_numpy().astype(np.int64)
    atr_ref = np.asarray(
        compute_atr(df, period=spec.atr_period), dtype=np.float64
    )
    r_unit = spec.sl_atr_mult
    full_window_end = n - 1

    rows: list[dict[str, Any]] = []
    for i in range(n):
        if spec.entry == "next_open" and i + 1 >= n:
            break  # no bar left to fill in
        ctx = make_ctx(cache, i)
        if not Interpreter(ctx).visit(ast):
            continue
        if spec.entry == "next_open":
            entry_idx = i + 1
            entry_price = float(cache.arrays["open"][entry_idx])
            walk_start = entry_idx  # fill-bar range unfolds after the open
        else:
            entry_idx, entry_price = i, float(cache.arrays["close"][i])
            walk_start = i + 1  # nothing after the close within bar i
        walk_end = min(walk_start + spec.horizon - 1, full_window_end)
        if spec.incomplete == "drop" and (
            walk_start + spec.horizon - 1 > full_window_end
        ):
            continue
        a = float(atr_ref[i])
        if spec.side == "long":
            stop = entry_price - r_unit * a
        else:
            stop = entry_price + r_unit * a
        mfe = mae = 0.0
        sl_hit = False
        bars_measured = 0
        for j in range(walk_start, walk_end + 1):
            bars_measured += 1
            hi = float(cache.arrays["high"][j])
            lo = float(cache.arrays["low"][j])
            if spec.side == "long":
                mfe = max(mfe, hi - entry_price)
                mae = max(mae, entry_price - lo)
                touched = lo <= stop
            else:
                mfe = max(mfe, entry_price - lo)
                mae = max(mae, hi - entry_price)
                touched = hi >= stop
            if touched:
                sl_hit = True
                if spec.exit == "sl_hit":
                    break  # window ends at the stop-touch bar (included)
        rows.append(
            {
                "signal_ts": int(ts[i]),
                "entry_ts": int(ts[entry_idx]),
                "entry_idx": int(entry_idx),
                "entry_price": entry_price,
                "bars_measured": bars_measured,
                "mfe_abs": mfe,
                "mae_abs": mae,
                "mfe_atr": mfe / a,
                "mae_atr": mae / a,
                "mfe_r": mfe / (r_unit * a),
                "mae_r": mae / (r_unit * a),
                "sl_hit": sl_hit,
            }
        )

    return pl.DataFrame(rows, schema=_SCHEMA).sort("signal_ts")
