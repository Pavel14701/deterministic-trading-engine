"""DSL strategy search (stage 0.5): rank *strategy templates*, not raw numbers.

Every candidate is a composition of explicit rules:

- **Entry rule**: order-block touch, optionally gated by the structural
  confirmation (``structure_label``) and/or the trend filter
  (``trend_direction``) - the same primitives the label generator uses.
- **Stop rule**: either volatility-based (``atr:m`` -> entry -/+ m*ATR)
  or structure-based (``zone:b`` -> behind the block zone +/- b*ATR).
- **Target rule**: ``rr:k`` -> k x the risk unit (kR take profit).
- **Holding rule**: time exit after ``--hold`` base bars.

Each candidate is evaluated with :func:`generate_labels_from_strategy` in
R-multiple mode; the score is the **mean realised R per trade net of
costs** (EV), reported per chronological split (train/val/test).
Ranking uses the *validation* EV; train/test are reported to expose
regime decay (the wide-geometry Gate-1 failure mode).

Approximation note (documented, conservative): for the structural stop
the per-bar zone level is painted first-match in block list order over a
bounded horizon, so the stop may use a slightly different (earlier,
deeper) eligible zone than the generator's own pick.  This is itself a
defensible rule ("stop behind the deepest nearby zone") and only
affects the ``zone:*`` family.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(REPO))

from ai.src.config import load_config  # noqa: E402
from ai.src.features import (  # noqa: E402
    compute_atr,
    generate_labels_from_strategy,
)
from scripts.prepare_okx_dataset import (  # noqa: E402
    detect_order_blocks,
    get_source,
    resolve_assets,
)

SPLIT_SHARES = (0.7, 0.15, 0.15)  # chronological train/val/test
PAINT_HORIZON = 2000  # bars a block stays eligible for the zone paint

# Indicator-anchored stop levels: name -> sides it is valid for.
# Support anchors (below price) stop longs, resistance anchors stop shorts;
# 'st' (supertrend) is direction-aware and valid for both (invalid
# geometries are filtered by the RR check anyway).
ANCHOR_SIDES = {
    "avsl": ("long",),      # Adaptive Volume Support Level
    "avsr": ("short",),     # Adaptive Volume Support/Resistance line
    "hilo": ("long", "short"),  # HiLo activator: long line / short line
    "st": ("long", "short"),    # supertrend trailing line
    "bb": ("long", "short"),    # Bollinger band (lower / upper)
}

BB_LENGTH = 20
BB_STD = 2.0


def _compute_anchors(df: pl.DataFrame) -> dict[str, np.ndarray]:
    """Causal per-bar anchor levels for indicator-based stops.

    All series are float64 numpy arrays aligned with ``df``; warm-up
    bars are NaN and simply produce no entries.
    """
    from ta.src.custom.avsl import avsl_numpy
    from ta.src.custom.avsr import avsr_numpy
    from ta.src.overlap.hilo import hilo_ind
    from ta.src.overlap.supertrend import supertrend_ind

    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()

    anchors: dict[str, np.ndarray] = {
        "avsl": avsl_numpy(high, low, close, volume, fast=52, slow=134),
        "avsr": avsr_numpy(high, low, close, volume, fast=52, slow=134),
    }
    _hilo, hilo_long, hilo_short = hilo_ind(high, low, close)
    anchors["hilo_l"] = hilo_long
    anchors["hilo_s"] = hilo_short
    st_line = supertrend_ind(high, low, close)[0]
    anchors["st"] = st_line
    cs = df["close"]
    mean = cs.rolling_mean(BB_LENGTH)
    std = cs.rolling_std(BB_LENGTH, ddof=0)
    anchors["bb_l"] = (mean - BB_STD * std).to_numpy()
    anchors["bb_u"] = (mean + BB_STD * std).to_numpy()
    return anchors


def _anchor_for_side(name: str, side: str) -> str | None:
    """Resolve an anchor family name to the concrete level key."""
    if name in ANCHOR_SIDES:
        if side not in ANCHOR_SIDES[name]:
            return None
        if name == "hilo":
            return "hilo_l" if side == "long" else "hilo_s"
        if name == "bb":
            return "bb_l" if side == "long" else "bb_u"
        return name
    return None


def _paint_zone(blocks: list, n: int, side: str) -> np.ndarray:
    """First-match zone level per bar for the structural stop rule.

    Iterates blocks in list order (the generator's priority) and paints
    ``[end_idx, end_idx + PAINT_HORIZON)`` with the stop-side zone edge
    (``zone_low`` for demand/long, ``zone_high`` for supply/short).
    Earlier blocks win; later blocks only fill unpainted bars.
    """
    zone = np.full(n, np.nan)
    for ob in blocks:
        is_demand = ob.block_type.lower() == "demand"
        if side == "long" and not is_demand:
            continue
        if side == "short" and is_demand:
            continue
        level = ob.zone_low if is_demand else ob.zone_high
        lo = max(ob.end_idx, 0)
        hi = min(n, lo + PAINT_HORIZON)
        if lo >= hi:
            continue
        seg = zone[lo:hi]
        mask = np.isnan(seg)
        seg[mask] = level
        zone[lo:hi] = seg
    return zone


def _build_tp_sl(
    close: np.ndarray,
    atr: np.ndarray,
    stop_rule: str,
    target_r: float,
    side: str,
    zone: np.ndarray | None,
    anchors: dict[str, np.ndarray] | None = None,
    min_risk_atr: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar TP/SL arrays for one (stop_rule, target_r) pair.

    Stop rule formats:
    - ``atr:m``  -> volatility stop, entry -/+ m*ATR;
    - ``zone:b`` -> structural stop, behind the block zone +/- b*ATR;
    - ``anchor:<name>:<b>`` -> indicator anchor level +/- b*ATR beyond.

    Bars whose risk unit is below ``min_risk_atr`` ATRs are marked
    invalid (no entry): a stop closer than that cannot survive
    round-trip costs, so the trade is not part of the strategy.
    """
    sign = 1.0 if side == "long" else -1.0
    if stop_rule.startswith("zone:"):
        buffer = float(stop_rule.split(":")[1])
        sl = zone - sign * buffer * atr
    elif stop_rule.startswith("atr:"):
        m = float(stop_rule.split(":")[1])
        sl = close - sign * m * atr
    elif stop_rule.startswith("anchor:"):
        _pfx, name, buffer_s = stop_rule.split(":")
        buffer = float(buffer_s)
        key = _anchor_for_side(name, side)
        level = anchors[key] if key else None
        if level is None:
            # anchor not valid for this side -> no trades for candidate
            sl = np.full(close.shape, np.nan)
        else:
            sl = level - sign * buffer * atr
    else:  # pragma: no cover - argparse constrains values
        raise ValueError(f"unknown stop rule {stop_rule!r}")
    risk_unit = np.abs(close - sl)
    tp = close + sign * target_r * risk_unit
    invalid = ~(
        np.isfinite(sl)
        & np.isfinite(tp)
        & (risk_unit > 0)
        & (risk_unit >= min_risk_atr * atr)
    )
    tp[invalid] = np.nan
    sl[invalid] = np.nan
    return tp, sl


def _split_stats(
    outcome: np.ndarray,
    action: np.ndarray,
    n: int,
    target_r: float,
) -> dict:
    """EV / resolution stats per chronological split (R-multiple mode)."""
    bounds = np.cumsum((0.0,) + SPLIT_SHARES)  # -> 0, .7, .85, 1.0
    pairs = [
        (int(bounds[i] * n), int(bounds[i + 1] * n)) for i in range(3)
    ]
    out: dict = {}
    entries = action == 1  # side-isolated runs: 1 = entry for this side
    for name, (lo, hi) in zip(("train", "val", "test"), pairs):
        res = outcome[lo:hi][entries[lo:hi]]
        res = res[np.isfinite(res)]
        if len(res) == 0:
            out[name] = {"n": 0, "ev_r": None}
            continue
        tp_hits = res >= 0.75 * target_r
        sl_hits = res <= -0.75
        holds = ~tp_hits & ~sl_hits
        out[name] = {
            "n": int(len(res)),
            "ev_r": round(float(res.mean()), 4),
            "tp_share": round(float(tp_hits.mean()), 3),
            "sl_share": round(float(sl_hits.mean()), 3),
            "hold_share": round(float(holds.mean()), 3),
        }
    return out


def main() -> None:
    """Run the strategy-template grid on warm caches and rank by val EV."""
    ap = argparse.ArgumentParser(
        description="DSL strategy search: entry x stop x target grid"
    )
    ap.add_argument("--data", default="data/okx21", help="raw-cache dir")
    ap.add_argument("--profile", default=None, help="risk profile name")
    ap.add_argument("--source", default="okx", help="data source")
    ap.add_argument(
        "--assets", nargs="+", default=["BTC-USDT"], help="reference assets"
    )
    ap.add_argument("--bars", default="1m", help="base timeframe")
    ap.add_argument("--years", type=float, default=2.5)
    ap.add_argument("--hold", type=int, default=480, help="max bars in trade")
    ap.add_argument(
        "--entries",
        default="plain,trend",
        help="comma list: plain | trend | structure (structure is a "
        "no-op with base-TF detect_order_blocks: all blocks carry "
        "structure_label; it matters only for HTF/DSL labels)",
    )
    ap.add_argument(
        "--stops",
        default=(
            "atr:27,avsl:0.5,avsl:1.0,avsr:0.5,avsr:1.0,"
            "hilo:0.5,st:0.5,bb:0.5,bb:1.0"
        ),
        help="comma list of stop rules: atr:m | zone:b | anchor:<name>:<b> "
        "with name in avsl,avsr,hilo,st,bb (side-aware)",
    )
    ap.add_argument(
        "--targets", default="2,3,4", help="comma list of R multiples"
    )
    ap.add_argument(
        "--min-risk-atr",
        type=float,
        default=1.0,
        help="min risk unit in ATRs (cost floor for structural stops)",
    )
    ap.add_argument("--out", default="runs/dsl/strategy_search.json")
    args = ap.parse_args()

    base_risk = load_config(risk_profile=args.profile).risk
    src = get_source(args.source)
    resolved = resolve_assets(src, args.assets, [args.bars], args.years)
    max_bars = int(src.bars_per_year(args.bars) * args.years)

    entry_variants = [e.strip() for e in args.entries.split(",")]
    stop_rules = []
    for raw in args.stops.split(","):
        rule = raw.strip()
        head = rule.split(":")[0]
        if head in ANCHOR_SIDES and rule.count(":") == 1:
            rule = f"anchor:{rule}"  # short form 'avsl:0.5'
        stop_rules.append(rule)
    target_rs = [float(t) for t in args.targets.split(",")]

    results: list[dict] = []
    for _src_name, inst_id, asset_src in resolved:
        df = asset_src.fetch_candles(
            inst_id,
            bar=args.bars,
            max_bars=max_bars,
            cache_dir=Path(args.data),
        )
        atr = compute_atr(df, risk=base_risk)
        obs = detect_order_blocks(df, atr, timeframe=args.bars)
        anchors = _compute_anchors(df)
        close = df["close"].to_numpy()
        n = df.height

        for side in ("long", "short"):
            blocks = [
                ob
                for ob in obs
                if (ob.block_type.lower() == "demand") == (side == "long")
            ]
            zone = _paint_zone(blocks, n, side)
            for entry in entry_variants:
                use_structure = "structure" in entry
                trend = None
                if "trend" in entry:
                    trend = "up" if side == "long" else "down"
                for stop_rule in stop_rules:
                    for target_r in target_rs:
                        tp, sl = _build_tp_sl(
                            close,
                            atr,
                            stop_rule,
                            target_r,
                            side,
                            zone,
                            anchors=anchors,
                            min_risk_atr=args.min_risk_atr,
                        )
                        if not np.isfinite(sl).any():
                            continue  # anchor invalid for this side
                        d = df.with_columns(
                            pl.Series("tp", tp), pl.Series("sl", sl)
                        )
                        t0 = time.time()
                        action, outcome = generate_labels_from_strategy(
                            d,
                            blocks,
                            use_r_multiple=True,
                            use_structure_filter=use_structure,
                            trend_filter=trend,
                            max_bars_hold=args.hold,
                        )
                        stats = _split_stats(outcome, action, n, target_r)
                        row = {
                            "asset": inst_id,
                            "side": side,
                            "entry": entry,
                            "stop": stop_rule,
                            "target_r": target_r,
                            "hold": args.hold,
                            "stats": stats,
                            "sec": round(time.time() - t0, 1),
                        }
                        results.append(row)
                        print(
                            json.dumps(
                                {
                                    "asset": inst_id,
                                    "side": side,
                                    "entry": entry,
                                    "stop": stop_rule,
                                    "target_r": target_r,
                                    "val_ev": stats["val"]["ev_r"],
                                    "val_n": stats["val"]["n"],
                                    "test_ev": stats["test"]["ev_r"],
                                    "train_ev": stats["train"]["ev_r"],
                                }
                            ),
                            flush=True,
                        )

    results.sort(
        key=lambda r: r["stats"]["val"]["ev_r"]
        if r["stats"]["val"]["ev_r"] is not None
        else -1e9,
        reverse=True,
    )
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"strategy search done: {len(results)} candidates -> {out}")
    print("top-10 by val EV:")
    for row in results[:10]:
        st = row["stats"]
        print(
            f"  {row['asset']} {row['side']:5s} "
            f"entry={row['entry']:16s} stop={row['stop']:9s} "
            f"tp={row['target_r']}R val_ev={st['val']['ev_r']} "
            f"test_ev={st['test']['ev_r']} train_ev={st['train']['ev_r']}"
        )


if __name__ == "__main__":
    main()

