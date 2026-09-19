"""Entry-candidate detectors for six structural families (stage A.2).

All detectors are causal: a candidate at bar ``j`` uses only bars
``<= j`` and only zones that are already known (``confirm_idx``).  Each
family emits :class:`Candidate` records with a zone that doubles as the
entry context; :func:`collect_candidates` runs every family and
deduplicates by ``(entry_idx, side)`` keeping the highest-priority
family and flagging overlaps.

"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from ai.src.datatypes import OrderBlock

#: Lower rank wins on deduplication (sweep is the most specific event).
FAMILY_PRIORITY: dict[str, int] = {
    "sweep": 0,
    "ob_retest": 1,
    "ob_touch": 2,
    "fvg": 3,
    "avsl_bounce": 4,
    "break_retest": 5,
}


@dataclass(frozen=True)
class Candidate:
    """One structural entry candidate.

    Args:
        entry_idx: Bar index of the entry decision (causal).
        side: ``"long"`` or ``"short"``.
        family: One of :data:`FAMILY_PRIORITY` keys.
        zone_low: Lower boundary of the structural zone.
        zone_high: Upper boundary of the structural zone.
        block_id: Originating order block id, ``-1`` if none.

    """

    entry_idx: int
    side: str
    family: str
    zone_low: float
    zone_high: float
    block_id: int = -1


def _zone_touches(
    df: pl.DataFrame,
    block: OrderBlock,
    atr: npt.NDArray[np.float64],
    tol_atr: float,
) -> list[int]:
    """Return bar indices where price touches a demand/supply zone.

    A demand zone dies on a close below ``zone_low``, a supply zone on
    a close above ``zone_high``.  Scanning starts after ``confirm_idx``
    so the zone is already known at every tested bar.
    """
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    close = df["close"].to_numpy()
    demand = block.block_type == "demand"
    touches: list[int] = []
    for j in range(max(block.confirm_idx + 1, 0), len(df)):
        c = close[j]
        if demand and c < block.zone_low:
            break
        if not demand and c > block.zone_high:
            break
        if demand:
            hit = block.zone_low - tol_atr * atr[j] <= low[j] <= block.zone_high
        else:
            hit = block.zone_low <= high[j] <= block.zone_high + tol_atr * atr[j]
        if hit:
            touches.append(j)
    return touches
def detect_ob_touches(
    df: pl.DataFrame,
    obs: list[OrderBlock],
    atr: npt.NDArray[np.float64],
    tol_atr: float = 0.0,
) -> list[Candidate]:
    """Family 1: first touch of each order block zone."""
    out: list[Candidate] = []
    for block in obs:
        touches = _zone_touches(df, block, atr, tol_atr)
        if touches:
            out.append(
                Candidate(
                    entry_idx=touches[0],
                    side="long" if block.block_type == "demand" else "short",
                    family="ob_touch",
                    zone_low=block.zone_low,
                    zone_high=block.zone_high,
                    block_id=block.id,
                )
            )
    return out


def detect_ob_retests(
    df: pl.DataFrame,
    obs: list[OrderBlock],
    atr: npt.NDArray[np.float64],
    tol_atr: float = 0.0,
) -> list[Candidate]:
    """Family 2: second touch of each zone (a confirmed retest)."""
    out: list[Candidate] = []
    for block in obs:
        touches = _zone_touches(df, block, atr, tol_atr)
        if len(touches) >= 2:
            out.append(
                Candidate(
                    entry_idx=touches[1],
                    side="long" if block.block_type == "demand" else "short",
                    family="ob_retest",
                    zone_low=block.zone_low,
                    zone_high=block.zone_high,
                    block_id=block.id,
                )
            )
    return out

def detect_sweeps(
    df: pl.DataFrame,
    obs: list[OrderBlock],
    atr: npt.NDArray[np.float64],
    wick_atr: float = 0.5,
) -> list[Candidate]:
    """Family 3: liquidity sweep of a zone edge with a reclaim close.

    Long: bar pierces below ``zone_low`` by at least ``wick_atr * ATR``
    and closes back above ``zone_low`` (stop-hunt reversal).  Short:
    mirrored on a supply zone.  Only the first sweep per block counts.
    """
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    close = df["close"].to_numpy()
    out: list[Candidate] = []
    for block in obs:
        demand = block.block_type == "demand"
        for j in range(max(block.confirm_idx + 1, 0), len(df)):
            depth = wick_atr * atr[j]
            if demand:
                pierced = low[j] < block.zone_low - depth
                reclaimed = close[j] > block.zone_low
            else:
                pierced = high[j] > block.zone_high + depth
                reclaimed = close[j] < block.zone_high
            if pierced and reclaimed:
                out.append(
                    Candidate(
                        entry_idx=j,
                        side="long" if demand else "short",
                        family="sweep",
                        zone_low=block.zone_low,
                        zone_high=block.zone_high,
                        block_id=block.id,
                    )
                )
                break
    return out


def detect_fvg(
    df: pl.DataFrame,
    atr: npt.NDArray[np.float64],
    min_gap_atr: float = 0.2,
    max_wait: int = 100,
) -> list[Candidate]:
    """Family 4: fair-value gaps with entry on the return into the gap.

    A bullish FVG forms at bar ``i`` when ``low[i] > high[i - 2]`` and
    the gap is at least ``min_gap_atr * ATR[i]`` wide; the candidate is
    the first later bar whose low returns into the gap (long).  Bearish
    FVGs are mirrored (short).
    """
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    n = len(df)
    out: list[Candidate] = []
    for i in range(2, n):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        bullish_gap = low[i] - high[i - 2]
        bearish_gap = low[i - 2] - high[i]
        if bullish_gap >= min_gap_atr * atr[i]:
            zone_lo, zone_hi = float(high[i - 2]), float(low[i])
            side = "long"
        elif bearish_gap >= min_gap_atr * atr[i]:
            zone_lo, zone_hi = float(high[i]), float(low[i - 2])
            side = "short"
        else:
            continue
        trigger = low if side == "long" else high
        for k in range(i + 1, min(i + 1 + max_wait, n)):
            entered = (
                trigger[k] <= zone_hi if side == "long" else trigger[k] >= zone_lo
            )
            if entered:
                out.append(
                    Candidate(
                        entry_idx=k,
                        side=side,
                        family="fvg",
                        zone_low=zone_lo,
                        zone_high=zone_hi,
                    )
                )
                break
    return out

def detect_avsl_bounce(
    df: pl.DataFrame,
    avsl: npt.NDArray[np.float64],
    avsr: npt.NDArray[np.float64],
    atr: npt.NDArray[np.float64],
    tol_atr: float = 0.3,
) -> list[Candidate]:
    """Family 5: bounce off AVSL (long) / AVSR (short) with a turn bar.

    Long at bar ``j``: the bar's range touches the AVSL level within
    ``tol_atr * ATR`` and the bar closes bullish.  Short: mirrored on
    AVSR with a bearish close.  NaN levels are skipped.
    """
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    open_ = df["open"].to_numpy()
    close = df["close"].to_numpy()
    out: list[Candidate] = []
    for j in range(len(df)):
        if not np.isfinite(atr[j]) or atr[j] <= 0:
            continue
        tol = tol_atr * atr[j]
        if (
            np.isfinite(avsl[j])
            and abs(low[j] - avsl[j]) <= tol
            and close[j] > open_[j]
        ):
            out.append(
                Candidate(
                    entry_idx=j,
                    side="long",
                    family="avsl_bounce",
                    zone_low=float(avsl[j] - tol),
                    zone_high=float(avsl[j] + tol),
                )
            )
        if (
            np.isfinite(avsr[j])
            and abs(high[j] - avsr[j]) <= tol
            and close[j] < open_[j]
        ):
            out.append(
                Candidate(
                    entry_idx=j,
                    side="short",
                    family="avsl_bounce",
                    zone_low=float(avsr[j] - tol),
                    zone_high=float(avsr[j] + tol),
                )
            )
    return out


def detect_break_retest(
    df: pl.DataFrame,
    obs: list[OrderBlock],
    max_wait: int = 200,
) -> list[Candidate]:
    """Family 6: break of a zone followed by a retest from the far side.

    A demand zone broken downward becomes resistance: the first later
    bar returning into the zone is a short candidate.  A supply zone
    broken upward is mirrored into a long candidate.  The retest must
    occur within ``max_wait`` bars after the break.
    """
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    out: list[Candidate] = []
    for block in obs:
        demand = block.block_type == "demand"
        start = max(block.confirm_idx + 1, 0)
        break_j = -1
        for j in range(start, n):
            if (demand and close[j] < block.zone_low) or (
                not demand and close[j] > block.zone_high
            ):
                break_j = j
                break
        if break_j < 0:
            continue
        for k in range(break_j + 1, min(break_j + 1 + max_wait, n)):
            # A demand zone broken down is re-entered from *below* (the
            # high rises into the zone); a supply broken up from above.
            entered = (
                high[k] >= block.zone_low if demand else low[k] <= block.zone_high
            )
            if entered:
                out.append(
                    Candidate(
                        entry_idx=k,
                        side="short" if demand else "long",
                        family="break_retest",
                        zone_low=block.zone_low,
                        zone_high=block.zone_high,
                        block_id=block.id,
                    )
                )
                break
    return out


def dedupe_candidates(cands: list[Candidate]) -> pl.DataFrame:
    """Deduplicate by ``(entry_idx, side)`` keeping the top-priority family.

    Returns a frame with columns ``entry_idx, side, family, zone_low,
    zone_high, block_id, overlap`` where ``overlap`` marks candidates
    that collided with another family at the same bar/side.
    """
    empty = pl.DataFrame(
        schema={
            "entry_idx": pl.Int64,
            "side": pl.Utf8,
            "family": pl.Utf8,
            "zone_low": pl.Float64,
            "zone_high": pl.Float64,
            "block_id": pl.Int64,
            "overlap": pl.Boolean,
        }
    )
    if not cands:
        return empty
    ranked = sorted(
        cands,
        key=lambda c: (c.entry_idx, c.side, FAMILY_PRIORITY[c.family]),
    )
    kept: list[Candidate] = []
    seen: set[tuple[int, str]] = set()
    for c in ranked:
        key = (c.entry_idx, c.side)
        if key not in seen:
            seen.add(key)
            kept.append(c)
    overlaps: list[bool] = []
    for c in kept:
        collisions = sum(
            1
            for o in ranked
            if o.entry_idx == c.entry_idx
            and o.side == c.side
            and o.family != c.family
        )
        overlaps.append(collisions > 0)
    return pl.DataFrame(
        {
            "entry_idx": [c.entry_idx for c in kept],
            "side": [c.side for c in kept],
            "family": [c.family for c in kept],
            "zone_low": [c.zone_low for c in kept],
            "zone_high": [c.zone_high for c in kept],
            "block_id": [c.block_id for c in kept],
            "overlap": overlaps,
        }
    )


def collect_candidates(
    df: pl.DataFrame,
    obs: list[OrderBlock],
    atr: npt.NDArray[np.float64],
    avsl: npt.NDArray[np.float64] | None = None,
    avsr: npt.NDArray[np.float64] | None = None,
    fvg_min_gap_atr: float = 0.2,
    sweep_wick_atr: float = 0.5,
) -> pl.DataFrame:
    """Run all six families and deduplicate.

    ``avsl``/``avsr`` default to NaN arrays (family 5 yields nothing).
    """
    n = len(df)
    if avsl is None:
        avsl = np.full(n, np.nan)
    if avsr is None:
        avsr = np.full(n, np.nan)
    cands: list[Candidate] = []
    cands += detect_ob_touches(df, obs, atr)
    cands += detect_ob_retests(df, obs, atr)
    cands += detect_sweeps(df, obs, atr, wick_atr=sweep_wick_atr)
    cands += detect_fvg(df, atr, min_gap_atr=fvg_min_gap_atr)
    cands += detect_avsl_bounce(df, avsl, avsr, atr)
    cands += detect_break_retest(df, obs)
    return dedupe_candidates(cands)

    return out

