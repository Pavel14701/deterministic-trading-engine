"""Build the MTF entry-candidate dataset (stage A.3/A.4/A.5).

Base timeframe is 1h (or 4h).  Entry candidates come from six structural
families (``ai/src/candidates.py``).  For every candidate we evaluate
the realised net R under the stop-rule x target panel (generator
semantics: SL-first pessimism, hold exit, costs net) under three
execution modes: market (next-open fill) and maker limits at the zone
edge / zone mid (pessimistic buffer fill, expiry).

Features per candidate: base context (ATR%, zone geometry, distances to
every anchor), regime vector (SMA50 z-distance/slope, causal rolling
percentiles of ATR% and BB width), HTF context for 1d/1w (asof-known
trend sign/slope, distances to the nearest HTF zones in base-ATR units)
and LTF (15m) asof impulse/volume.

Splits (A.4): chronological train/val/test with a ``hold``-bar embargo
- no trade crosses a boundary.  Diagnostics (A.5): EV pivot by
regime x family x stop rule printed and saved as json.

Output: ``data/mtf_dataset/<asset>_<base>.parquet`` (+ json summary).
"""

from __future__ import annotations

import argparse
import json

from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl


REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402


sys.path.insert(0, str(REPO))

from engine.candidates import collect_candidates  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.features import compute_atr  # noqa: E402
from engine.mtf import asof_rows, resample_ohlcv  # noqa: E402
from engine.mtf_dataset import (  # noqa: E402
    assign_splits,
    limit_fill,
    nearest_zone_dists,
    rolling_percentile,
    trend_state,
)
from engine.okx_dataset import (  # noqa: E402
    detect_order_blocks,
    get_source,
    resolve_assets,
)
from engine.zones import (  # noqa: E402
    build_tp_sl as _build_tp_sl,
    compute_anchors as _compute_anchors,
    paint_zone as _paint_zone,
)
from scripts.build_stop_dataset import (  # noqa: E402
    FEATURE_ANCHORS,
    STOP_PANEL,
    TARGET_PANEL,
    _excursions,
    _simulate_outcome,
)


EXECUTIONS = ("market", "limit:edge", "limit:mid")
LTF_BAR = "15m"


def _auto_hold(base: str) -> int:
    """Default max-hold in base bars (about 2 days)."""
    return 48 if base == "1h" else 12


def _anchors_nan_safe(df: pl.DataFrame) -> dict[str, np.ndarray]:
    """``_compute_anchors`` with a NaN-safe AVSL/AVSR fallback.

    On resampled (non-1m) frames the AVSL/AVSR adjusted series carries
    warm-up NaNs and the talib SMA path poisons the whole output with
    them.  When that happens, rebuild both levels with the numba SMA
    (``nan_policy='ffill'``), mirroring ``avsl_numpy``/``avsr_numpy``.
    """
    anchors = _compute_anchors(df)
    if np.isfinite(anchors["avsl"]).any():
        return anchors
    from ta.src.custom.avs_base import (
        _avs_base,
        _compute_len_v,
        _compute_vpcc,
        _price_v_rolling,
    )
    from ta.src.overlap.sma import sma_ind

    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()
    vpc, vpr, _vm, vpci, dev = _avs_base(close, volume, 52, 134, 1.0, False)
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    for name, src_price, sign in (("avsl", low, -1.0), ("avsr", high, 1.0)):
        price_v = _price_v_rolling(src_price, vpr, len_v, vpcc)
        adjusted = src_price + sign * (price_v - dev)
        anchors[name] = np.asarray(
            sma_ind(adjusted, 134, use_talib=False, nan_policy="ffill"),
            dtype=np.float64,
        )
    return anchors


def _htf_zone_ts(htf_obs: list, htf: pl.DataFrame) -> list[tuple[object, int]]:
    """Pair each HTF order block with the ts when its zone became known."""
    ts_col = htf["ts"].to_numpy()
    pairs: list[tuple[object, int]] = []
    for ob in htf_obs:
        idx = min(max(ob.confirm_idx, 0), len(ts_col) - 1)
        pairs.append((ob, int(ts_col[idx])))
    return pairs


def _htf_asof_state(
    htf: pl.DataFrame,
    htf_zts: list[tuple[object, int]],
    base_ts: int,
    base_atr: float,
) -> dict[str, float]:
    """Causal HTF context for a base-TF decision at ``base_ts``.

    Uses only HTF bars whose ``known_ts <= base_ts`` (closed bars) and
    only zones confirmed no later than that moment.

    Args:
        htf: Resampled HTF frame with an ``_atr`` column.
        htf_zts: ``(order_block, known_ts)`` pairs from :func:`_htf_zone_ts`.
        base_ts: Decision timestamp (epoch ms).
        base_atr: Base-TF ATR at the entry (distance unit).

    Returns:
        ``trend`` (+1/-1/0), ``slope`` (SMA slope in base ATRs) and
        ``d_below``/``d_above`` (distances to the nearest known HTF
        zone, in base ATRs).

    """
    out = {"trend": 0.0, "slope": 0.0, "d_below": np.nan, "d_above": np.nan}
    known = asof_rows(htf, base_ts)
    if known.is_empty():
        return out
    close = known["close"].to_numpy()
    atr_arr = known["_atr"].to_numpy()
    _z, slope, sign = trend_state(close, atr_arr)
    out["trend"] = float(sign[-1])
    out["slope"] = float(slope[-1]) if np.isfinite(slope[-1]) else 0.0
    zones = [
        (ob.zone_low, ob.zone_high) for ob, kts in htf_zts if kts <= base_ts
    ]
    below, above = nearest_zone_dists(zones, float(close[-1]))
    denom = base_atr if np.isfinite(base_atr) and base_atr > 0 else 1.0
    out["d_below"] = below / denom if np.isfinite(below) else np.nan
    out["d_above"] = above / denom if np.isfinite(above) else np.nan
    return out


def _ltf_asof_features(
    ltf_known_ts: npt.NDArray[np.int64],
    ltf_close: npt.NDArray[np.float64],
    ltf_vol: npt.NDArray[np.float64],
    base_ts: int,
    base_atr: float,
    impulse_bars: int = 6,
    vol_window: int = 50,
) -> tuple[float, float]:
    """LTF (15m) impulse and volume z-score asof a base-TF decision."""
    pos = int(np.searchsorted(ltf_known_ts, base_ts, side="right")) - 1
    if pos < impulse_bars:
        return np.nan, np.nan
    impulse = (ltf_close[pos] - ltf_close[pos - impulse_bars]) / base_atr
    seg = ltf_vol[max(0, pos - vol_window + 1) : pos + 1]
    mean = float(seg.mean())
    std = float(seg.std())
    vol_z = (ltf_vol[pos] - mean) / std if std > 0 else 0.0
    return float(impulse), float(vol_z)


def _entry_feature_row(
    cand,  # ai.candidates.Candidate
    i: int,
    ts: int,
    open_p: npt.NDArray[np.float64],
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    atr: npt.NDArray[np.float64],
    anchors: dict[str, npt.NDArray[np.float64]],
    z50: npt.NDArray[np.float64],
    slope50: npt.NDArray[np.float64],
    vol_pct: npt.NDArray[np.float64],
    bbw_pct: npt.NDArray[np.float64],
    obs_by_id: dict[int, object],
    htf_states: list[dict[str, float]],
    ltf_feats: tuple[float, float],
) -> dict:
    """Base feature row for one candidate (shared across panel rows)."""
    sign = 1.0 if cand["side"] == "long" else -1.0
    zone_edge = (
        cand["zone_low"] if cand["side"] == "long" else cand["zone_high"]
    )
    feat: dict = {
        "entry_idx": int(i),
        "ts": ts,
        "side": cand["side"],
        "family": cand["family"],
        "block_id": int(cand["block_id"]),
        "overlap": bool(cand.get("overlap", False)),
        "atr_pct": float(atr[i] / close[i]) if close[i] > 0 else np.nan,
        "zone_height_atr": float(
            (cand["zone_high"] - cand["zone_low"]) / atr[i]
        )
        if np.isfinite(atr[i]) and atr[i] > 0
        else np.nan,
        "zone_dist_atr": float((close[i] - zone_edge) * sign / atr[i])
        if np.isfinite(atr[i]) and atr[i] > 0
        else np.nan,
        "z50": float(z50[i]) if np.isfinite(z50[i]) else np.nan,
        "slope50": float(slope50[i]) if np.isfinite(slope50[i]) else np.nan,
        "vol_pct": float(vol_pct[i]) if np.isfinite(vol_pct[i]) else np.nan,
        "bbw_pct": float(bbw_pct[i]) if np.isfinite(bbw_pct[i]) else np.nan,
        "regime_dir": (
            "up"
            if z50[i] > 0.5
            else "down"
            if z50[i] < -0.5
            else "range"
        )
        if np.isfinite(z50[i])
        else "unknown",
    }
    block = obs_by_id.get(cand["block_id"]) if cand["block_id"] >= 0 else None
    feat["ob_trend"] = (block.trend_direction or "none") if block else "none"
    feat["ob_structure"] = (block.structure_label or "none") if block else "none"
    for key in FEATURE_ANCHORS:
        lvl = anchors[key][i]
        feat[f"d_{key}"] = (
            float((close[i] - lvl) * sign / atr[i])
            if np.isfinite(lvl) and np.isfinite(atr[i]) and atr[i] > 0
            else np.nan
        )
    for h_i, st in enumerate(htf_states, start=1):
        feat[f"h{h_i}_trend"] = st["trend"]
        feat[f"h{h_i}_slope"] = st["slope"]
        feat[f"h{h_i}_below"] = st["d_below"]
        feat[f"h{h_i}_above"] = st["d_above"]
    feat["ltf_impulse"], feat["ltf_vol_z"] = ltf_feats
    return feat


def _outcome_rows(
    feat: dict,
    i: int,
    side: str,
    zone_low: float,
    zone_high: float,
    open_p: npt.NDArray[np.float64],
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    atr: npt.NDArray[np.float64],
    rule_levels: dict[
        str, tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]
    ],
    hold: int,
    commission_pct: float,
    slippage_pct: float,
    limit_buf_atr: float,
    limit_wait: int,
    min_risk_atr: float = 0.5,
) -> list[dict]:
    """Panel rows (execution x stop rule x target) for one candidate.

    Market fills at the next open with slippage; maker limits rest at
    the zone edge or mid, fill pessimistically (buffer pass-through)
    and expire after ``limit_wait`` bars.
    """
    sign = 1.0 if side == "long" else -1.0
    n = len(close)
    rows: list[dict] = []
    for exec_mode in EXECUTIONS:
        if exec_mode == "market":
            if i + 1 >= n:
                return rows
            fill_idx = i + 1
            fill = open_p[i + 1] * (1 + sign * slippage_pct)
            filled = True
        else:
            if exec_mode == "limit:edge":
                level = zone_low if side == "long" else zone_high
            else:
                level = 0.5 * (zone_low + zone_high)
            fill_idx = limit_fill(
                side,
                level,
                high,
                low,
                atr,
                i + 1,
                buf_atr=limit_buf_atr,
                max_wait=limit_wait,
            )
            fill = level
            filled = fill_idx >= 0
            if not filled:
                for rule in STOP_PANEL:
                    for target in TARGET_PANEL:
                        rows.append(
                            feat
                            | {
                                "execution": exec_mode,
                                "rule": rule,
                                "target": target,
                                "r_net": np.nan,
                                "exit_idx": -1,
                                "filled": False,
                            }
                        )
                continue
        for rule, (tp_arr, sl_arr) in rule_levels.items():
            sl_i = sl_arr[i]
            for target in TARGET_PANEL:
                base_row = feat | {
                    "execution": exec_mode,
                    "rule": rule,
                    "target": target,
                    "filled": filled,
                    "fill_price": fill,
                    "sl_price": sl_i if np.isfinite(sl_i) else np.nan,
                    "tp_price": np.nan,
                    "risk_unit": np.nan,
                    "atr_i": atr[i],
                    "exit_reason": None,
                    "mfe_atr": np.nan,
                    "mae_atr": np.nan,
                    "mfe_r": np.nan,
                    "mae_r": np.nan,
                }
                if not np.isfinite(sl_i) or fill_idx >= n:
                    base_row["r_net"] = np.nan
                    base_row["exit_idx"] = -1
                    rows.append(base_row)
                    continue
                risk_unit = abs(fill - sl_i)
                if risk_unit < min_risk_atr * atr[i]:
                    # stop sits (almost) at the fill price - e.g. a limit
                    # fill deep in the zone next to an anchor stop: the
                    # R-multiple degenerates; mark invalid instead.
                    base_row["r_net"] = np.nan
                    base_row["exit_idx"] = -1
                    rows.append(base_row)
                    continue
                tp_i = fill + sign * target * risk_unit
                base_row["tp_price"] = tp_i
                base_row["risk_unit"] = risk_unit
                (
                    base_row["mfe_atr"],
                    base_row["mae_atr"],
                    base_row["mfe_r"],
                    base_row["mae_r"],
                ) = _excursions(
                    high, low, close, fill_idx, fill, side, sl_i, hold, atr[i]
                )
                (
                    base_row["r_net"],
                    base_row["exit_idx"],
                    base_row["exit_reason"],
                    base_row["exit_price"],
                ) = _simulate_outcome(
                    high,
                    low,
                    close,
                    fill_idx,
                    fill,
                    side,
                    sl_i,
                    tp_i,
                    hold,
                    commission_pct,
                    slippage_pct,
                )
                rows.append(base_row)
    return rows


def main() -> None:
    """Build the MTF candidate dataset on a warm 1m cache."""
    ap = argparse.ArgumentParser(
        description="stage A.3: MTF entry-candidate dataset"
    )
    ap.add_argument("--data", default="data/okx", help="raw-cache dir")
    ap.add_argument("--source", default="okx")
    ap.add_argument("--assets", nargs="+", default=["BTC-USDT"])
    ap.add_argument("--base", default="1h", choices=["1h", "4h"])
    ap.add_argument("--years", type=float, default=1.5)
    ap.add_argument("--hold", type=int, default=0, help="0 = auto (48/12)")
    ap.add_argument("--min-risk-atr", type=float, default=0.5)
    ap.add_argument("--limit-buf-atr", type=float, default=0.1)
    ap.add_argument("--limit-wait", type=int, default=5)
    ap.add_argument("--out", default="data/mtf_dataset")
    args = ap.parse_args()

    risk = load_config(risk_profile="wide").risk
    src = get_source(args.source)
    resolved = resolve_assets(src, args.assets, ["1m"], args.years)
    hold = args.hold or _auto_hold(args.base)
    htf_bars = ["4h", "1d"] if args.base == "1h" else ["1d", "1w"]

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for _name, inst_id, asset_src in resolved:
        df1m = asset_src.fetch_candles(
            inst_id,
            bar="1m",
            max_bars=int(src.bars_per_year("1m") * args.years),
            cache_dir=Path(args.data),
        )
        ltf = resample_ohlcv(df1m, LTF_BAR)
        base = resample_ohlcv(df1m, args.base)
        htf_frames = []
        for h in htf_bars:
            f = resample_ohlcv(df1m, h)
            f = f.with_columns(pl.Series("_atr", compute_atr(f, risk=risk)))
            htf_frames.append(f)

        atr = compute_atr(base, risk=risk)
        obs = detect_order_blocks(base, atr, timeframe=args.base)
        anchors = _anchors_nan_safe(base)
        cands = collect_candidates(
            base, obs, atr, avsl=anchors["avsl"], avsr=anchors["avsr"]
        )

        open_p = base["open"].to_numpy()
        high = base["high"].to_numpy()
        low = base["low"].to_numpy()
        close = base["close"].to_numpy()
        ts = base["ts"].to_numpy()
        n = len(base)
        z50, slope50, _sign = trend_state(close, atr)
        atr_pct = np.where(close > 0, atr / close, np.nan)
        vol_pct = rolling_percentile(atr_pct, window=500)
        bbw = (anchors["bb_u"] - anchors["bb_l"]) / close
        bbw_pct = rolling_percentile(bbw, window=500)
        obs_by_id = {ob.id: ob for ob in obs}

        ltf_known_ts = ltf["known_ts"].to_numpy()
        ltf_close = ltf["close"].to_numpy()
        ltf_vol = ltf["volume"].to_numpy()
        htf_zts = [
            _htf_zone_ts(
                detect_order_blocks(f, f["_atr"].to_numpy(), timeframe=h), f
            )
            for h, f in zip(htf_bars, htf_frames)
        ]

        rows: list[dict] = []
        for side in ("long", "short"):
            sub = cands.filter(pl.col("side") == side)
            if sub.is_empty():
                continue
            blocks = [
                ob
                for ob in obs
                if (ob.block_type.lower() == "demand") == (side == "long")
            ]
            zone_arr = _paint_zone(blocks, n, side)
            rule_levels = {
                rule: _build_tp_sl(
                    close,
                    atr,
                    rule,
                    2.0,
                    side,
                    zone_arr,
                    anchors=anchors,
                    min_risk_atr=args.min_risk_atr,
                )
                for rule in STOP_PANEL
            }
            for cand in sub.iter_rows(named=True):
                i = int(cand["entry_idx"])
                if i + 1 >= n or not np.isfinite(atr[i]) or atr[i] <= 0:
                    continue
                htf_states = [
                    _htf_asof_state(f, zts, int(ts[i]), atr[i])
                    for f, zts in zip(htf_frames, htf_zts)
                ]
                ltf_feats = _ltf_asof_features(
                    ltf_known_ts, ltf_close, ltf_vol, int(ts[i]), atr[i]
                )
                feat = _entry_feature_row(
                    cand,
                    i,
                    int(ts[i]),
                    open_p,
                    high,
                    low,
                    close,
                    atr,
                    anchors,
                    z50,
                    slope50,
                    vol_pct,
                    bbw_pct,
                    obs_by_id,
                    htf_states,
                    ltf_feats,
                )
                rows += _outcome_rows(
                    feat,
                    i,
                    side,
                    cand["zone_low"],
                    cand["zone_high"],
                    open_p,
                    high,
                    low,
                    close,
                    atr,
                    rule_levels,
                    hold,
                    risk.commission_pct,
                    risk.slippage_pct,
                    args.limit_buf_atr,
                    args.limit_wait,
                    min_risk_atr=args.min_risk_atr,
                )

        table = pl.DataFrame(rows)
        entry_idxs = table["entry_idx"].unique().to_numpy().astype(np.int64)
        split_map = dict(
            zip(entry_idxs.tolist(), assign_splits(entry_idxs, n, hold))
        )
        table = table.with_columns(
            pl.col("entry_idx")
            .replace_strict(split_map, default="", return_dtype=pl.Utf8)
            .alias("split")
        )

        tag = inst_id.replace("-", "")
        out_file = out_dir / f"{tag}_{args.base}.parquet"
        table.write_parquet(out_file)

        summary: dict = {
            "base": args.base,
            "hold": hold,
            "candidates": int(cands.height),
            "rows": table.height,
            "splits": table["split"].value_counts().sort("split").to_dicts(),
            "by_family": cands.group_by("family").len().sort("family").to_dicts(),
        }
        for rule in ("atr:14", "zone:1.0"):
            sub = table.filter(
                (pl.col("execution") == "market")
                & (pl.col("target") == 2.0)
                & (pl.col("rule") == rule)
                & (pl.col("split") != "")
                & pl.col("r_net").is_not_nan()
            )
            piv = (
                sub.pivot(
                    values="r_net",
                    index="family",
                    on="split",
                    aggregate_function="mean",
                )
                .with_columns(pl.exclude("family").round(3))
                .to_dicts()
            )
            summary[f"ev_by_family_split/{rule}"] = piv
            print(f"\nEV pivot (market, 2R): {rule}")
            print(pl.DataFrame(piv))
        (out_dir / f"{tag}_{args.base}.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(
            f"\n{inst_id} [{args.base}]: {summary['candidates']} candidates, "
            f"{summary['rows']} rows, hold={hold} -> {out_file}",
            flush=True,
        )


if __name__ == "__main__":
    main()





