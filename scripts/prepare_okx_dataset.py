"""Prepare an EntryExitTransformer training dataset from live OKX data.

Pipeline (run from the repo root):

    uv run python scripts/run_pipeline.py \
        --assets BTC-USDT ETH-USDT SOL-USDT DOGE-USDT \
        --bars 1m 5m 15m 1H --years 1 --out data/okx

Steps per asset:
  1. fetch candle history for every timeframe (via the marketdata
     source registry: OKX by default, T-Invest with --source or
     per-asset "src:inst" prefixes; public REST, parquet-cached
     REST, no keys; raw frames cached as parquet);
  2. detect supply/demand order blocks on **every** timeframe
     (swing + displacement heuristic) - all block fields are kept
     (type, zone bounds, strength, structure label, trend, height/ATR,
     confirm/retest bars, timeframe);
  3. compute **all registered ta indicators** (84 bindings) on the
     base (lowest) timeframe; higher timeframes contribute their full
     per-bar OB feature set, mapped onto the base grid **causally**
     (a base bar only sees the last *closed* HTF bar);
  4. compute TP/SL (ATR-based, previous-bar ATR - no look-ahead) and
     action/outcome labels (ai.src.features, strategy simulation with
     costs);
  5. normalise price-domain columns per asset (divide by the asset's
     median close over the first 500 bars - causal per-asset constant);
  6. chronological split into train/val/test (70/15/15 with a
     ``seq_len``-bar gap between segments; the val/test segment files
     carry a ``seq_len``-bar context prefix whose labels are set to the
     ignore index -100).

Outputs (under ``--out``):
  train/{features,labels,order_blocks}.parquet, val/{...}, test/{...},
  meta.json

Order blocks are written **per split segment** (with indices rebased into
that segment's frame); the union of the three files is the complete OB
set, each block kept with every detected field (type, zone bounds,
strength, structure label, trend, confirm/break/retest bars, height/ATR,
source timeframe).

This module exposes the preparation steps for reuse; see
``scripts/run_pipeline.py`` for the single-command entry point.
"""

from __future__ import annotations

import argparse
import json
import sys

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ai.src.config import AIConfig, risk_kwargs  # noqa: E402
from ai.src.datatypes import OrderBlock  # noqa: E402
from ai.src.features import (  # noqa: E402
    compute_atr,
    compute_ob_features,
    compute_tp_sl,
    generate_labels_from_strategy,
)
from marketdata.common import (  # noqa: E402
    CandleSource,
    get_source,
    known_sources,
)
from marketdata.okx_source import OkxSource  # noqa: E402,F401
from marketdata.tinvest_source import TInvestSource  # noqa: E402,F401
from ta.src.provider import (  # noqa: E402
    BINDINGS,
    OutputSpec,
    TaProvider,
)


DIST_CAP = 10.0  # cap for distance features (in ATR units)
HTF_WARMUP_BARS = 300  # extra HTF bars before the base start (warm-up)


def detect_order_blocks(
    df: pl.DataFrame,
    atr: np.ndarray,
    swing: int = 5,
    disp_mult: float = 1.5,
    confirm_bars: int = 5,
    timeframe: str = "1m",
) -> list[OrderBlock]:
    """Detect supply/demand order blocks without look-ahead.

    A swing high bar ``i`` whose close drops by more than
    ``disp_mult * atr[i]`` within the next ``confirm_bars`` bars forms a
    **supply** zone ``[min(open_i, close_i), high_i]``; a swing low with
    an up-displacement forms a **demand** zone.  The zone becomes known
    at the displacement bar (``confirm_idx``) - never earlier.  All
    block fields are recorded so the model receives the complete OB
    context (strength, height/ATR, retest/confirm bars, timeframe).

    Args:
        df: OHLCV frame.
        atr: Causal ATR series (same length as ``df``).
        swing: Bars on each side for the local-extremum test.
        disp_mult: Displacement threshold in ATR multiples.
        confirm_bars: Window for the displacement move.
        timeframe: Source timeframe label stored on each block.

    Returns:
        Order blocks with all integer indices set (``start_idx``,
        ``end_idx``, ``confirm_idx``, ``retest_idx``).

    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    low_arr = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    blocks: list[OrderBlock] = []
    ob_id = 0

    def _trend(i: int) -> str | None:
        # coarse trend: close vs 50-bar SMA at formation
        seg = c[max(0, i - 50) : i + 1]
        return "up" if seg[-1] >= seg.mean() else "down"

    for i in range(swing, n - swing - confirm_bars):
        for kind in ("supply", "demand"):
            if kind == "supply":
                if (
                    h[i] < h[i - swing : i].max()
                    or h[i] < h[i + 1 : i + swing + 1].max()
                ):
                    continue
                zone_lo, zone_hi = min(o[i], c[i]), h[i]
                seg = c[i : i + confirm_bars + 1]
                disp = seg.min()
                confirm_off = int(np.argmin(seg))
            else:
                if (
                    low_arr[i] > low_arr[i - swing : i].min()
                    or low_arr[i] > low_arr[i + 1 : i + swing + 1].min()
                ):
                    continue
                zone_lo, zone_hi = low_arr[i], max(o[i], c[i])
                seg = c[i : i + confirm_bars + 1]
                disp = seg.max()
                confirm_off = int(np.argmax(seg))
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            if abs(disp - c[i]) < disp_mult * atr[i]:
                continue

            retest_idx = -1
            break_idx = -1
            for j in range(i + 1, n):
                if zone_lo <= c[j] <= zone_hi and retest_idx < 0:
                    retest_idx = j
                if (kind == "supply" and c[j] > zone_hi) or (
                    kind == "demand" and c[j] < zone_lo
                ):
                    break_idx = j
                    break
            if break_idx < 0:
                break_idx = n - 1
            if retest_idx < 0:
                retest_idx = break_idx
            blocks.append(
                OrderBlock(
                    id=ob_id,
                    block_type=kind,
                    start=datetime.fromtimestamp(
                        df["ts"][i] / 1000, tz=timezone.utc
                    ),
                    break_=datetime.fromtimestamp(
                        df["ts"][break_idx] / 1000, tz=timezone.utc
                    ),
                    retest=datetime.fromtimestamp(
                        df["ts"][retest_idx] / 1000, tz=timezone.utc
                    ),
                    zone_low=float(zone_lo),
                    zone_high=float(zone_hi),
                    strength=float(abs(disp - c[i]) / atr[i]),
                    structure_label=(
                        "retested" if retest_idx < break_idx else "fresh"
                    ),
                    trend_direction=_trend(i),
                    start_idx=i,
                    end_idx=break_idx,
                    timeframe=timeframe,
                    confirm_idx=i + confirm_off,
                    retest_idx=retest_idx,
                    zone_height_atr=float((zone_hi - zone_lo) / atr[i]),
                )
            )
            ob_id += 1
    return blocks


# --------------------------------------------------------------------------- #
# Indicator columns (all registered bindings, default params)
# --------------------------------------------------------------------------- #


def compute_indicator_columns(
    df: pl.DataFrame,
) -> tuple[pl.DataFrame, list[str]]:
    """Compute every registered indicator; returns frame + column names."""
    provider = TaProvider(df)
    cols: dict[str, pl.Series] = {}
    for name in sorted(BINDINGS):
        binding = BINDINGS[name]
        try:
            arr = provider._indicator_array(binding, {})
        except Exception as exc:
            print(f"  skip {name}: {exc}")
            continue
        if arr.ndim == 1:
            for attr in binding.outputs or {"value": OutputSpec(index=0)}:
                col = f"{name}_{attr}"
                if col not in cols:
                    cols[col] = pl.Series(np.asarray(arr, dtype=np.float64))
        else:
            for attr, spec in binding.outputs.items():
                col = f"{name}_{attr}"
                if col in cols:
                    continue
                vals = np.asarray(arr[spec.index], dtype=np.float64).reshape(
                    -1
                )
                if len(vals) != len(df):
                    continue
                cols[col] = pl.Series(vals)
    ind_cols = sorted(cols)
    return df.with_columns([cols[c].alias(c) for c in ind_cols]), ind_cols


# --------------------------------------------------------------------------- #
# Per-asset normalisation
# --------------------------------------------------------------------------- #

PRICE_COLS = ("open", "high", "low", "close", "tp", "sl")


def normalise(feat: pl.DataFrame, ind_cols: list[str]) -> pl.DataFrame:
    """Scale price-domain columns by a causal per-asset constant.

    ``scale`` = median close over the first 500 bars.  Indicator columns
    whose values live in the same magnitude band as the asset's price
    are treated as price-domain; volume-like columns are scaled by their
    own early median; everything else (oscillators, ratios, OB features)
    passes through.

    Medians are computed over **finite** values only: indicator warm-up
    leaves NaN in the first bars, and a NaN median would silently disable
    scaling for the whole column (``nan`` comparisons are always False).

    """
    ref_close = float(cast(float, feat["close"][:500].median()))

    def _median(series: pl.Series) -> float:
        clean = series.drop_nulls().drop_nans()
        if clean.len() == 0:
            return 0.0
        return float(cast(float, clean.abs().median()) or 0.0)

    scale_map: dict[str, float] = {}
    log_cols: list[str] = []
    for col in feat.columns:
        if col == "ts" or col in PRICE_COLS:
            scale_map[col] = ref_close
        elif col in ind_cols:
            med = _median(feat[col])
            if med <= 0 or not np.isfinite(med):
                continue
            if med <= 50 * ref_close:
                scale_map[col] = ref_close
            else:  # volume-like magnitude
                vm = _median(feat[col][:500])
                if vm > 0 and np.isfinite(vm):
                    scale_map[col] = vm
        elif "volume" in col.lower():
            # Raw traded volume spans many orders of magnitude (coin
            # units: median ~1e2, spikes ~1e9).  A linear scale cannot
            # tame that; log1p of the volume normalised by its early
            # median maps it to a compact, model-friendly range.
            vm = _median(feat[col][:500])
            if vm > 0 and np.isfinite(vm):
                log_cols.append(col)
    out = feat.with_columns(
        [(pl.col(c) / s).alias(c) for c, s in scale_map.items() if s > 0]
    )
    if log_cols:
        out = out.with_columns(
            [pl.col(c).log1p().alias(c) for c in log_cols]
        )
    return sanitise_features(out)


def sanitise_features(feat: pl.DataFrame) -> pl.DataFrame:
    """Replace non-finite values in all float columns with 0.

    Indicator warm-up (and, for volume-like columns, division) can leave
    ``NaN``/``inf`` in a prepared feature frame.  A single non-finite
    value propagates through the network and turns the whole loss into
    ``NaN``, so prepared datasets must be finite.  ``ts`` is left intact.

    Returns:
        The frame with every non-finite float value replaced by ``0.0``.

    """
    cols: dict[str, pl.Series] = {}
    for col in feat.columns:
        if col == "ts" or not feat[col].dtype.is_float():
            continue
        arr = feat[col].to_numpy()
        if np.isfinite(arr).all():
            continue
        cols[col] = pl.Series(
            col, np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        )
    if not cols:
        return feat
    return feat.with_columns([cols[c] for c in cols])


# --------------------------------------------------------------------------- #
# Multi-timeframe features (causal HTF -> base grid mapping)
# --------------------------------------------------------------------------- #


def map_htf_ob_indices(
    hobs: list[OrderBlock],
    hts: np.ndarray,
    base_ts: np.ndarray,
    htf_ms: int,
    base_ms: int,
) -> list[OrderBlock]:
    """Rebase HTF order-block indices onto the base grid **causally**.

    An HTF bar opening at ``ts`` only *closes* at ``ts + htf_ms``: nothing
    it reveals (swing point, displacement, retest) is knowable before that
    close.  On the base grid the first bar that may use the information is
    the base bar whose close coincides with the HTF close, i.e. the base
    bar opening at ``ts + htf_ms - base_ms``.  Every HTF timestamp is
    shifted by that amount, so a base bar never sees an unfinished HTF bar.

    Blocks whose confirmation would only become known after the base range
    ends are dropped (never clamped onto the last base bar, which would be
    look-ahead).

    Args:
        hobs: Order blocks detected on the HTF frame.
        hts: HTF bar open timestamps (ms).
        base_ts: Base-timeframe bar open timestamps (ms).
        htf_ms: HTF bar duration in milliseconds.
        base_ms: Base bar duration in milliseconds.

    Returns:
        Order blocks with all indices rebased onto the base grid;
        ``end_idx == -1`` means "still active until the end of the data".

    """
    shift = htf_ms - base_ms
    n_base = len(base_ts)
    mapped: list[OrderBlock] = []

    def to_base(idx: int) -> int:
        """Map an HTF bar index to its causal base-window index (-1 = n/a)."""
        if idx < 0 or idx >= len(hts):
            return -1
        pos = int(np.searchsorted(base_ts, int(hts[idx]) + shift, side="left"))
        return -1 if pos >= n_base else pos

    for ob in hobs:
        known_htf = ob.confirm_idx if ob.confirm_idx >= 0 else ob.start_idx
        known = to_base(known_htf)
        if known < 0:
            continue  # confirmation happens after the base range ends
        start = to_base(ob.start_idx)
        if start < 0 or start > known:
            start = known  # zone formed at/before its confirmation
        retest = to_base(ob.retest_idx)
        if 0 <= retest < known:
            retest = -1  # a "retest" before confirmation is not usable
        # A zone that never breaks inside the base range is anchored to the
        # last base bar, exactly like the base-timeframe detector does with
        # `break_idx = n - 1`; it therefore stays untradeable until the end
        # of the data instead of looking permanently "active".
        if ob.end_idx < 0:
            end = n_base - 1
        else:
            end = to_base(ob.end_idx)
            if end < 0:
                end = n_base - 1
        mapped.append(
            OrderBlock(
                id=ob.id,
                block_type=ob.block_type,
                start=ob.start,
                break_=ob.break_,
                retest=ob.retest,
                zone_low=ob.zone_low,
                zone_high=ob.zone_high,
                strength=ob.strength,
                structure_label=ob.structure_label,
                trend_direction=ob.trend_direction,
                start_idx=start,
                end_idx=end,
                timeframe=ob.timeframe,
                confirm_idx=known,
                retest_idx=retest,
                zone_height_atr=ob.zone_height_atr,
            )
        )
    return mapped


# --------------------------------------------------------------------------- #
# Per-asset preparation (multi-TF) and chronological split
# --------------------------------------------------------------------------- #


def prepare_asset(
    inst_id: str,
    bars: list[str],
    max_bars: int,
    cfg: AIConfig,
    cache_dir: Path,
    source: CandleSource,
) -> tuple[pl.DataFrame, pl.DataFrame, list[OrderBlock], list[str], list[str]]:
    """Fetch, featurise and label one asset across all timeframes.

    Returns ``(features, labels, order_blocks, ind_cols, sig_cols)``.
    ``sig_cols`` covers the base-TF OB feature set plus the per-TF
    prefixed copies for every higher timeframe.

    """
    base_bar = bars[0]
    print(
        f"[{inst_id}] fetching up to {max_bars} {base_bar} bars "
        f"(+ HTF: {', '.join(bars[1:]) or 'none'}) ...",
        flush=True,
    )
    df = source.fetch_candles(
        inst_id, bar=base_bar, max_bars=max_bars, cache_dir=cache_dir
    )
    t0 = datetime.fromtimestamp(df["ts"][0] / 1000, tz=timezone.utc)
    t1 = datetime.fromtimestamp(df["ts"][-1] / 1000, tz=timezone.utc)
    span = f"{t0:%Y-%m-%d %H:%M} .. {t1:%Y-%m-%d %H:%M}"
    print(f"[{inst_id}] {df.height} bars {span}", flush=True)

    df, ind_cols = compute_indicator_columns(df)
    atr = compute_atr(df, risk=cfg.risk)
    obs = detect_order_blocks(df, atr, timeframe=base_bar)
    print(
        f"[{inst_id}] indicators: {len(ind_cols)}, OB({base_bar}): {len(obs)}",
        flush=True,
    )

    # --- base-TF OB features (full set, causal) ---
    base_feats = compute_ob_features(df, obs, atr)
    sig_cols = sorted(base_feats)
    for col in sig_cols:
        arr = np.clip(base_feats[col], 0.0, DIST_CAP)
        df = df.with_columns(pl.Series(col, arr))

    # --- higher timeframes: OB + features, mapped causally ---
    base_ts = df["ts"].to_numpy()
    for htf in bars[1:]:
        # cover the whole base span (+ warm-up) so no base bar lacks a
        # closed HTF bar; derived from the base bar count, not a default
        htf_bars = (
            int(
                np.ceil(
                    max_bars * source.BAR_MS[base_bar] / source.BAR_MS[htf]
                )
            )
            + HTF_WARMUP_BARS
        )
        hdf = source.fetch_candles(
            inst_id, bar=htf, max_bars=htf_bars, cache_dir=cache_dir
        )
        hatr = compute_atr(hdf, risk=cfg.risk)
        hobs = detect_order_blocks(hdf, hatr, timeframe=htf)
        hobs = map_htf_ob_indices(
            hobs,
            hdf["ts"].to_numpy(),
            base_ts,
            source.BAR_MS[htf],
            source.BAR_MS[base_bar],
        )
        obs.extend(hobs)
        hfeats = compute_ob_features(hdf, hobs, hatr)
        hts_close = hdf["ts"].to_numpy() + source.BAR_MS[htf]
        hframe = pl.DataFrame({"close_ts": hts_close})
        for col in sorted(hfeats):
            hframe = hframe.with_columns(
                pl.Series(f"{htf}_{col}", np.clip(hfeats[col], 0.0, DIST_CAP))
            )
        df = (
            df.sort("ts")
            .join_asof(
                hframe.sort("close_ts"),
                left_on="ts",
                right_on="close_ts",
                strategy="backward",
            )
            .drop("close_ts")
        )
        htf_cols = sorted(hframe.columns[1:])
        sig_cols.extend(htf_cols)
        covered = df.height - int(df[htf_cols[0]].null_count())
        pct = 100.0 * covered / max(df.height, 1)
        print(
            f"[{inst_id}] OB({htf}): {len(hobs)} blocks, "
            f"{hdf.height} {htf} bars, base coverage {pct:.1f}%",
            flush=True,
        )
        if pct < 99.9:
            print(
                f"[{inst_id}] WARNING: {df.height - covered} base bars "
                f"have no closed {htf} bar (HTF history too short)",
                flush=True,
            )

    tp, sl = compute_tp_sl(df, risk=cfg.risk)
    df = df.with_columns(pl.Series("tp", tp), pl.Series("sl", sl))
    action, outcome = generate_labels_from_strategy(
        df, obs, **risk_kwargs(cfg.risk)
    )
    labels = pl.DataFrame({"action": action, "outcome": outcome})
    uniq, cnt = np.unique(action, return_counts=True)
    print(
        f"[{inst_id}] action distribution: "
        f"{dict(zip(uniq.tolist(), cnt.tolist(), strict=True))}",
        flush=True,
    )
    return df, labels, obs, ind_cols, sig_cols


def split_chronological(
    feat: pl.DataFrame,
    labels: pl.DataFrame,
    obs: list[OrderBlock],
    seq_len: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> dict[str, tuple[pl.DataFrame, pl.DataFrame, list[OrderBlock], dict]]:
    """Chronological 70/15/15 split per asset, leakage-free.

    Segments are separated by a ``seq_len``-bar gap.  Each val/test
    segment file carries a ``seq_len``-bar context prefix (real features
    so windows have history) whose labels are set to the ignore index
    -100 - the context bars never contribute to the loss or metrics.
    Order blocks are rebased per segment and clipped to the file start.

    Returns a dict ``{'train'/'val'/'test': (features, labels, obs,
    info)}`` where ``info`` documents the boundaries.

    """
    n = feat.height
    gap = seq_len
    # Reserve both inter-segment gaps out of the usable budget so the
    # segments can never run past the end of the frame.  (The previous
    # arithmetic added the gap on top of the fractions, which overflowed
    # - and crashed - on short histories such as daily bars.)
    usable = n - 2 * gap
    min_segment = seq_len + 10
    if usable < 3 * min_segment:
        raise RuntimeError(
            f"not enough bars for a {seq_len}-bar model: {n} bars leave "
            f"{usable} usable after the two {gap}-bar gaps, but three "
            f"segments of at least {min_segment} bars are required. "
            "Fetch more history (--years/--max-bars) or reduce the "
            "model seq_len (configs/ai.yaml) for this timeframe."
        )
    n_train = int(usable * train_frac)
    n_val = int(usable * val_frac)
    bounds = {
        "train": (0, n_train),
        "val": (n_train + gap, n_train + gap + n_val),
        "test": (n_train + gap + n_val + gap, n),
    }

    out: dict[
        str, tuple[pl.DataFrame, pl.DataFrame, list[OrderBlock], dict]
    ] = {}
    for name, (start, end) in bounds.items():
        if end - start <= seq_len + 10:
            raise RuntimeError(
                f"segment '{name}' too small ({end - start} bars, need "
                f"> {seq_len + 10}); fetch more history (--years/--max-bars) "
                "or reduce the model seq_len for this timeframe"
            )
        ctx = 0 if name == "train" else min(seq_len, start)
        fstart = start - ctx
        seg_feat = feat[fstart:end]
        seg_labels = labels[fstart:end]
        if ctx:
            seg_labels = seg_labels.with_columns(
                pl.when(pl.arange(0, seg_labels.height) < ctx)
                .then(pl.lit(-100))
                .otherwise(pl.col("action"))
                .alias("action")
            )
        seg_obs: list[OrderBlock] = []
        for ob in obs:
            known = ob.confirm_idx if ob.confirm_idx >= 0 else ob.start_idx
            # Keep a block when it is already known by the end of the
            # segment.  A block confirmed *before* the segment (or broken
            # before it) is still tradeable inside the segment, so it must
            # not be dropped - only blocks confirmed in the future are,
            # since they would leak information into this segment.
            if known >= end:
                continue
            shift = -fstart

            def rebase(x: int, shift: int = shift) -> int:
                return -1 if x < 0 else max(0, x + shift)

            seg_obs.append(
                OrderBlock(
                    id=ob.id,
                    block_type=ob.block_type,
                    start=ob.start,
                    break_=ob.break_,
                    retest=ob.retest,
                    zone_low=ob.zone_low,
                    zone_high=ob.zone_high,
                    strength=ob.strength,
                    structure_label=ob.structure_label,
                    trend_direction=ob.trend_direction,
                    start_idx=rebase(ob.start_idx),
                    end_idx=rebase(ob.end_idx),
                    timeframe=ob.timeframe,
                    confirm_idx=rebase(ob.confirm_idx),
                    retest_idx=rebase(ob.retest_idx),
                    zone_height_atr=ob.zone_height_atr,
                )
            )
        info = {
            "label_start": start,
            "label_end": end,
            "file_start": fstart,
            "n_bars": end - fstart,
            "n_context": ctx,
            "ts_start": int(feat["ts"][fstart]),
            "ts_end": int(feat["ts"][end - 1]),
        }
        out[name] = (seg_feat, seg_labels, seg_obs, info)
    return out


def obs_to_frame(obs: list[OrderBlock]) -> pl.DataFrame:
    """Serialize order blocks (ALL fields) into a parquet-ready frame."""
    return pl.DataFrame(
        [
            {
                "id": ob.id,
                "block_type": ob.block_type,
                "start": ob.start,
                "break_": ob.break_,
                "retest": ob.retest,
                "zone_low": ob.zone_low,
                "zone_high": ob.zone_high,
                "strength": ob.strength,
                "structure_label": ob.structure_label,
                "trend_direction": ob.trend_direction,
                "start_idx": ob.start_idx,
                "end_idx": ob.end_idx,
                "timeframe": ob.timeframe,
                "confirm_idx": ob.confirm_idx,
                "retest_idx": ob.retest_idx,
                "zone_height_atr": ob.zone_height_atr,
            }
            for ob in obs
        ],
        schema_overrides={
            "structure_label": pl.Utf8,
            "trend_direction": pl.Utf8,
        },
    )


def class_distribution(labels: pl.DataFrame) -> dict[str, int]:
    """Action-class counts (excluding the ignore index -100)."""
    acts = labels["action"].to_numpy()
    acts = acts[acts >= 0]
    uniq, cnt = np.unique(acts, return_counts=True)
    return {str(int(u)): int(c) for u, c in zip(uniq, cnt, strict=True)}


@dataclass
class SegmentBucket:
    """Per-split accumulator: feature/label frames and their order blocks.

    Keeping the three lists in one typed object (instead of a nested
    ``dict[str, list[...]]``) lets ``obs`` hold ``OrderBlock`` lists
    without lying about the element type.
    """

    feat: list[pl.DataFrame] = field(default_factory=list)
    lbl: list[pl.DataFrame] = field(default_factory=list)
    obs: list[list[OrderBlock]] = field(default_factory=list)


def resolve_assets(
    default_source: CandleSource,
    specs: list[str],
    bars: list[str],
    years: float,
) -> list[tuple[str, str, CandleSource]]:
    """Resolve ``--assets`` specs into (source, instrument) pairs.

    ``--source`` supplies the default venue; an explicit ``src:inst``
    prefix (``okx:BTC-USDT``, ``tinvest:SBER@MOEX``) overrides it so a
    single dataset can mix venues.  The requested bars are validated
    against **every** resolved source (support + history depth), which
    makes an impossible request fail with a clear message instead of a
    ``KeyError`` deep inside the fetch loop.

    Args:
        default_source: Source used for assets without a prefix.
        specs: Raw ``--assets`` entries.
        bars: Requested pipeline bars (first = base).
        years: Requested history depth in years.

    Returns:
        ``(source_name, instrument, source)`` per asset, input order.

    Raises:
        ValueError: For an unknown source prefix or an asset whose
            source cannot serve one of the requested bars.

    """
    default_source.validate_bars(bars, years)
    resolved: list[tuple[str, str, CandleSource]] = []
    for spec in specs:
        prefix, sep, inst = spec.partition(":")
        if sep:
            if prefix not in known_sources():
                known = ", ".join(known_sources())
                raise ValueError(
                    f"unknown source prefix {prefix!r} in {spec!r} "
                    f"(known: {known}); write {inst!r} for the default "
                    "source or '<source>:<instrument>' to mix venues"
                )
            source = get_source(prefix)
            source.validate_bars(bars, years)
        else:
            inst, source = spec, default_source
        resolved.append((source.name, inst, source))
    return resolved


def main() -> None:
    """Run the full dataset preparation (multi-TF, year-scale, split)."""
    ap = argparse.ArgumentParser(
        description=(
            "Prepare a multi-source training dataset (OKX, T-Invest, ...)"
        )
    )
    ap.add_argument(
        "--source",
        default="okx",
        help="default candle source for assets without an explicit prefix",
    )
    ap.add_argument(
        "--assets",
        nargs="+",
        default=[
            "BTC-USDT",
            "ETH-USDT",
            "SOL-USDT",
            "DOGE-USDT",
        ],
        help=(
            "instruments; optionally prefixed with a source, e.g. "
            "tinvest:SBER@MOEX okx:BTC-USDT"
        ),
    )
    ap.add_argument(
        "--bars",
        nargs="+",
        default=["1m", "5m", "15m", "1H"],
        help="timeframes, first = base",
    )
    ap.add_argument(
        "--base",
        nargs="+",
        default=None,
        help=(
            "base grid(s) to build full datasets on (subset of --bars; "
            "default: the first --bars entry). Each base sees only the "
            "timeframes OLDER than itself as causal HTF context, so "
            "'--bars 1m 5m 15m 1H --base 1m 15m' yields a 1m dataset "
            "(5m/15m/1H context) and a 15m dataset (1H context)"
        ),
    )
    ap.add_argument(
        "--years",
        type=float,
        default=1.0,
        help="history depth in years (base timeframe bars)",
    )
    ap.add_argument(
        "--max-bars",
        type=int,
        default=None,
        help="override the bar count derived from --years",
    )
    ap.add_argument("--out", default="data/okx")
    args = ap.parse_args()

    default_source = get_source(args.source)
    # resolve each asset to its (source, instrument) pair: an explicit
    # "src:inst" prefix overrides --source, letting one dataset mix venues;
    # every requested bar is validated against every resolved source
    resolved = resolve_assets(
        default_source, args.assets, args.bars, args.years
    )

    cfg = AIConfig()
    seq_len = cfg.model.seq_len
    out = REPO / args.out
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("train", "val", "test"):
        (out / sub).mkdir(exist_ok=True)

    bars_ms = default_source.BAR_MS
    # Base grids to build full datasets on.  Every base sees the
    # timeframes *older* than itself as causal HTF context, so one
    # ladder yields one complete dataset per requested grid.
    bases = args.base or [args.bars[0]]
    unknown = [b for b in bases if b not in args.bars]
    if unknown:
        raise SystemExit(f"--base {unknown} not among --bars {args.bars}")
    multi = len(bases) > 1

    ind_cols: list[str] | None = None
    base_sig_cols: dict[str, list[str]] = {}
    per_base: dict[str, dict] = {}
    meta_assets: dict[str, dict] = {}
    grand_obs = 0
    bars_tot = {"train": 0, "val": 0, "test": 0}

    for base_bar in bases:
        ctx_bars = [b for b in args.bars if bars_ms[b] > bars_ms[base_bar]]
        ladder = [base_bar, *ctx_bars]
        print(
            f"=== base {base_bar} "
            f"(context: {', '.join(ctx_bars) or 'none'}) ===",
            flush=True,
        )
        seg_data: dict[str, SegmentBucket] = {
            "train": SegmentBucket(),
            "val": SegmentBucket(),
            "test": SegmentBucket(),
        }
        all_obs: list[OrderBlock] = []
        base_assets: dict[str, dict] = {}
        sig_cols: list[str] | None = None
        for src_name, inst_id, src in resolved:
            # per-asset bar budget: a mixed dataset derives the count from
            # each asset's own source (venues may differ in bar duration)
            max_bars = args.max_bars or int(
                src.bars_per_year(base_bar) * args.years
            )
            df, lbl, obs, icols, scols = prepare_asset(
                inst_id, ladder, max_bars, cfg, out, src
            )
            if ind_cols is None:
                ind_cols = icols
            elif icols != ind_cols:
                raise RuntimeError(f"{inst_id}: indicator columns differ")
            if sig_cols is None:
                sig_cols = scols
            elif scols != sig_cols:
                raise RuntimeError(f"{inst_id}: signal columns differ")
            df = normalise(df, icols)
            segments = split_chronological(df, lbl, obs, seq_len)
            base_assets[inst_id] = {
                "bars": df.height,
                "source": src_name,
                "segments": {},
            }
            for name, (sf, sl, sobs, info) in segments.items():
                offset = sum(f.height for f in seg_data[name].feat)
                seg_obs: list[OrderBlock] = []
                for ob in sobs:  # rebase OB indices into the joined frame
                    # Per-segment indices are already non-negative; -1 keeps
                    # its sentinel meaning ("still active" / "no retest")
                    # instead of being shifted to a bogus bar index.
                    def off(x: int, offset: int = offset) -> int:
                        return -1 if x < 0 else x + offset

                    rebased = OrderBlock(
                        id=len(all_obs),
                        block_type=ob.block_type,
                        start=ob.start,
                        break_=ob.break_,
                        retest=ob.retest,
                        zone_low=ob.zone_low,
                        zone_high=ob.zone_high,
                        strength=ob.strength,
                        structure_label=ob.structure_label,
                        trend_direction=ob.trend_direction,
                        start_idx=off(ob.start_idx),
                        end_idx=off(ob.end_idx),
                        timeframe=ob.timeframe,
                        confirm_idx=off(ob.confirm_idx),
                        retest_idx=off(ob.retest_idx),
                        zone_height_atr=ob.zone_height_atr,
                    )
                    all_obs.append(rebased)  # global (for analysis)
                    seg_obs.append(rebased)  # per-segment (for training)
                seg_data[name].feat.append(sf)
                seg_data[name].lbl.append(sl)
                seg_data[name].obs.append(seg_obs)
                info = dict(info)
                info["class_distribution"] = class_distribution(sl)
                base_assets[inst_id]["segments"][name] = info

        totals: dict[str, int] = {}
        for name in ("train", "val", "test"):
            seg_dir = out / name / base_bar if multi else out / name
            if multi:
                seg_dir.mkdir(parents=True, exist_ok=True)
            feat_df = pl.concat(seg_data[name].feat, how="vertical")
            lbl_df = pl.concat(seg_data[name].lbl, how="vertical")
            feat_df.write_parquet(seg_dir / "features.parquet")
            lbl_df.write_parquet(seg_dir / "labels.parquet")
            obs_df = obs_to_frame(
                [ob for seg in seg_data[name].obs for ob in seg]
            )
            obs_df.write_parquet(seg_dir / "order_blocks.parquet")
            totals[name] = feat_df.height
            bars_tot[name] += feat_df.height
            print(
                f"[{name}/{base_bar}] {feat_df.height} bars, "
                f"actions={class_distribution(lbl_df)}, "
                f"ob={obs_df.height}",
                flush=True,
            )
        base_sig_cols[base_bar] = sig_cols or []
        per_base[base_bar] = {
            "sig_cols": sig_cols or [],
            **{f"total_bars_{n}": totals[n] for n in totals},
            "n_order_blocks": len(all_obs),
        }
        grand_obs += len(all_obs)
        if multi:
            for inst, info in base_assets.items():
                entry = meta_assets.setdefault(
                    inst, {"source": info["source"], "bases": {}}
                )
                entry["bases"][base_bar] = {
                    "bars": info["bars"],
                    "segments": info["segments"],
                }
        else:
            meta_assets = base_assets

    # union of per-base signal columns (a smaller base lacks the
    # HTF-prefixed columns of larger-context bases); train_okx fills
    # the missing ones with neutral values
    sig_union: list[str] = []
    for b in bases:
        for col in base_sig_cols[b]:
            if col not in sig_union:
                sig_union.append(col)

    meta = {
        "assets": meta_assets,
        "bars": args.bars,
        "bases": bases,
        "years": args.years,
        "seq_len": seq_len,
        "split": {"train": 0.70, "val": 0.15, "test": 0.15, "gap": seq_len},
        "total_bars_train": bars_tot["train"],
        "total_bars_val": bars_tot["val"],
        "total_bars_test": bars_tot["test"],
        "per_base": per_base,
        "base_sig_cols": base_sig_cols,
        "n_indicators": len(ind_cols or []),
        "n_signals": len(sig_union),
        "n_order_blocks": grand_obs,
        "ind_cols": ind_cols,
        "sig_cols": sig_union,
        "price_cols": ["open", "high", "low", "close", "volume"],
        "tp_sl_cols": ["tp", "sl"],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    (out / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nDONE: OB={grand_obs} bases={bases} -> {out}")


if __name__ == "__main__":
    main()
