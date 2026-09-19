"""Build the stop-selection dataset (stage 0.7).

Reference strategy (wide ATR stop, 2R target) generates OB entries per
side.  For **every** entry we then evaluate the realised R-multiple under
a *panel* of candidate stop rules (ATR multiples, structural zone stops,
indicator anchors: AVSL/AVSR/HiLo/Supertrend/Bollinger) x target
multiples, mirroring the label-generator execution semantics
(next-open fill with slippage, SL-first pessimism, hold exit at close,
costs net).

The output is one row per (entry, stop_rule, target) with entry features
(distances to every anchor in ATR units, ATR%, OB structure/trend, side)
and the realised R.  A model trained on this table learns *which stop
level survives to the target for which entry context* - per-entry
stop/target selection instead of one fixed multiplier.

Output: ``data/stop_dataset/<asset>.parquet`` (+ json summary).
"""

from __future__ import annotations

import argparse
import json

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402


sys.path.insert(0, str(REPO))

from ai.config import load_config  # noqa: E402
from ai.features import (  # noqa: E402
    compute_atr,
    generate_labels_from_strategy,
)
from scripts.prepare_okx_dataset import (  # noqa: E402
    detect_order_blocks,
    get_source,
    resolve_assets,
)
from scripts.zones import (  # noqa: E402
    build_tp_sl,
    compute_anchors,
    paint_zone,
)


REFERENCE_STOP = "atr:27"
REFERENCE_TARGET = 2.0

STOP_PANEL = [
    "atr:14",
    "atr:27",
    "atr:54",
    "zone:0.5",
    "zone:1.0",
    "anchor:avsl:0.5",
    "anchor:avsr:0.5",
    "anchor:hilo:0.5",
    "anchor:st:0.5",
    "anchor:bb:0.5",
    "anchor:bb:1.0",
]
TARGET_PANEL = [2.0, 3.0]

FEATURE_ANCHORS = [
    "avsl",
    "avsr",
    "hilo_l",
    "hilo_s",
    "st",
    "bb_l",
    "bb_u",
]


def _simulate_outcome(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fill_idx: int,
    entry_price: float,
    direction: str,
    sl: float,
    tp: float,
    max_hold: int,
    commission_pct: float,
    slippage_pct: float,
) -> tuple[float | None, int, str | None, float]:
    """Net R-multiple + exit bar for one trade (generator semantics)."""
    sign = 1.0 if direction == "long" else -1.0
    risk_unit = abs(entry_price - sl)
    if risk_unit <= 0 or not np.isfinite(risk_unit):
        return None
    n = len(close)
    cost_in_r = (
        2 * commission_pct * entry_price + slippage_pct * entry_price
    ) / risk_unit
    for held, j in enumerate(range(fill_idx, n)):
        hit_sl = low[j] <= sl if direction == "long" else high[j] >= sl
        hit_tp = high[j] >= tp if direction == "long" else low[j] <= tp
        time_exit = max_hold > 0 and held >= max_hold
        if hit_sl:  # pessimistic: SL before TP within the same bar
            exit_price = sl * (1 - sign * slippage_pct)
            return (
                sign * (exit_price - entry_price) / risk_unit - cost_in_r,
                j,
                "sl",
                exit_price,
            )
        if hit_tp:  # limit fill, no exit slippage
            return sign * (tp - entry_price) / risk_unit - cost_in_r, j, "tp", tp
        if time_exit:
            exit_price = close[j] * (1 - sign * slippage_pct)
            return (
                sign * (exit_price - entry_price) / risk_unit - cost_in_r,
                j,
                "time",
                exit_price,
            )
    return None, -1, None, np.nan  # data ended with an open trade


def _excursions(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fill_idx: int,
    entry_price: float,
    direction: str,
    sl: float,
    max_hold: int,
    atr: float,
) -> tuple[float, float, float, float]:
    """TP-free path stats: max favorable / adverse excursion before SL.

    Walks forward until the stop is hit (that bar's extremes excluded -
    they are unreachable once the stop fills) or max_hold bars elapse.
    Returns (mfe_atr, mae_atr, mfe_r, mae_r): excursion normalized by
    ATR at entry and by the risk unit.  These are the regression
    targets/features for the adaptive-TP head (D.5).
    """
    sign = 1.0 if direction == "long" else -1.0
    risk = abs(entry_price - sl)
    if risk <= 0 or not np.isfinite(risk) or atr <= 0:
        return np.nan, np.nan, np.nan, np.nan
    n = len(close)
    fav = adv = 0.0
    for j in range(fill_idx, min(n, fill_idx + max_hold)):
        if (low[j] <= sl) if sign > 0 else (high[j] >= sl):
            break
        hi = high[j] if sign > 0 else low[j]
        lo = low[j] if sign > 0 else high[j]
        fav = max(fav, sign * (hi - entry_price))
        adv = max(adv, sign * (entry_price - lo))
    return fav / atr, adv / atr, fav / risk, adv / risk


def _entry_rows(
    i: int,
    side: str,
    open_p: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    anchors: dict[str, np.ndarray],
    zone: np.ndarray,
    blocks: list,
    rule_levels: dict[str, tuple[np.ndarray, np.ndarray]],
    hold: int,
    commission_pct: float,
    slippage_pct: float,
) -> list[dict]:
    """All dataset rows for one reference entry (features x rule panel)."""
    sign = 1.0 if side == "long" else -1.0
    fill_price = open_p[i + 1] * (1 + sign * slippage_pct)
    feat: dict = {
        "entry_idx": int(i),
        "side": side,
        "atr_pct": float(atr[i] / close[i]),
        "zone_dist_atr": float((close[i] - zone[i]) * sign / atr[i])
        if np.isfinite(zone[i])
        else np.nan,
    }
    for key in FEATURE_ANCHORS:
        lvl = anchors[key][i]
        feat[f"d_{key}"] = (
            float((close[i] - lvl) * sign / atr[i])
            if np.isfinite(lvl)
            else np.nan
        )
    for ob in blocks:
        if ob.end_idx <= i and (
            ob.zone_low <= high[i] <= ob.zone_high
            or ob.zone_low <= low[i] <= ob.zone_high
        ):
            feat["ob_trend"] = ob.trend_direction or "none"
            feat["ob_structure"] = ob.structure_label or "none"
            break

    rows: list[dict] = []
    for rule, (tp_arr, sl_arr) in rule_levels.items():
        sl_i = sl_arr[i]
        if not np.isfinite(sl_i):
            rows.append(
                feat | {"rule": rule, "target": np.nan, "r_net": np.nan, "exit_idx": -1}
            )
            continue
        for target in TARGET_PANEL:
            risk_unit = abs(fill_price - sl_i)
            tp_i = fill_price + sign * target * risk_unit
            r, exit_j, _reason, _exit_px = _simulate_outcome(
                high,
                low,
                close,
                i + 1,
                fill_price,
                side,
                sl_i,
                tp_i,
                hold,
                commission_pct,
                slippage_pct,
            )
            rows.append(
                feat | {"rule": rule, "target": target, "r_net": r, "exit_idx": exit_j}
            )
    return rows


def main() -> None:
    """Generate the per-entry stop-outcome panel on a warm cache."""
    ap = argparse.ArgumentParser(
        description="stage 0.7: per-entry stop-outcome dataset"
    )
    ap.add_argument("--data", default="data/okx21", help="raw-cache dir")
    ap.add_argument("--source", default="okx")
    ap.add_argument("--assets", nargs="+", default=["BTC-USDT"])
    ap.add_argument("--bars", default="1m")
    ap.add_argument("--years", type=float, default=2.5)
    ap.add_argument("--hold", type=int, default=480)
    ap.add_argument("--min-risk-atr", type=float, default=15.0)
    ap.add_argument("--out", default="data/stop_dataset")
    args = ap.parse_args()

    risk = load_config(risk_profile="wide").risk
    src = get_source(args.source)
    resolved = resolve_assets(src, args.assets, [args.bars], args.years)
    max_bars = int(src.bars_per_year(args.bars) * args.years)

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for _name, inst_id, asset_src in resolved:
        df = asset_src.fetch_candles(
            inst_id,
            bar=args.bars,
            max_bars=max_bars,
            cache_dir=Path(args.data),
        )
        atr = compute_atr(df, risk=risk)
        obs = detect_order_blocks(df, atr, timeframe=args.bars)
        anchors = compute_anchors(df)
        open_p = df["open"].to_numpy()
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()
        n = df.height
        rows: list[dict] = []
        for side in ("long", "short"):
            blocks = [
                ob
                for ob in obs
                if (ob.block_type.lower() == "demand") == (side == "long")
            ]
            zone = paint_zone(blocks, n, side)
            tp_a, sl_a = build_tp_sl(
                close,
                atr,
                REFERENCE_STOP,
                REFERENCE_TARGET,
                side,
                zone,
                anchors=anchors,
                min_risk_atr=args.min_risk_atr,
            )
            d = df.with_columns(
                pl.Series("tp", tp_a), pl.Series("sl", sl_a)
            )
            action, outcome = generate_labels_from_strategy(
                d,
                blocks,
                use_r_multiple=True,
                use_structure_filter=False,
                trend_filter=None,
                max_bars_hold=args.hold,
            )
            entries = np.where((action == 1) & np.isfinite(outcome))[0]

            rule_levels: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            for rule in STOP_PANEL:
                rule_levels[rule] = build_tp_sl(
                    close,
                    atr,
                    rule,
                    REFERENCE_TARGET,
                    side,
                    zone,
                    anchors=anchors,
                    min_risk_atr=args.min_risk_atr,
                )

            for i in entries:
                rows.extend(
                    _entry_rows(
                        i=i,
                        side=side,
                        open_p=open_p,
                        high=high,
                        low=low,
                        close=close,
                        atr=atr,
                        anchors=anchors,
                        zone=zone,
                        blocks=blocks,
                        rule_levels=rule_levels,
                        hold=args.hold,
                        commission_pct=risk.commission_pct,
                        slippage_pct=risk.slippage_pct,
                    )
                )

        table = pl.DataFrame(rows)
        out_file = out_dir / f"{inst_id.replace('-', '')}.parquet"
        table.write_parquet(out_file)
        sub = table.filter(
            (pl.col("target") == 2.0) & pl.col("r_net").is_not_nan()
        )
        summary = {
            "entries": int(table["entry_idx"].n_unique()),
            "rows": table.height,
            "rules": len(STOP_PANEL),
            "targets": TARGET_PANEL,
            "ev_by_rule_full_2R": {
                r: round(
                    float(
                        sub.filter(pl.col("rule") == r)["r_net"].mean() or 0.0
                    ),
                    4,
                )
                for r in STOP_PANEL
            },
        }
        (out_dir / f"{inst_id.replace('-', '')}.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(f"{inst_id}: {summary['rows']} rows -> {out_file}", flush=True)
        print(json.dumps(summary["ev_by_rule_full_2R"], indent=2))


if __name__ == "__main__":
    main()

