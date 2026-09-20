"""DSL-search stage 0: label statistics per candidate indicator config.

Rebuilds strategy labels on warm raw candle caches for a grid of
indicator-parameter and/or risk-parameter overrides — no model, no
features, minutes per grid.  Surviving candidates (healthy entry rate,
non-random win rate) advance to stage 1 (LightGBM proxy, gate on
acc/F1) and only then to short/full transformer runs.

Examples:
  # list bindings available for --indicator
  uv run python scripts/dsl_stage0.py --list

  # AVSL fast/slow inversion hypothesis (long<short ~134/52) + ATR grid
  uv run python scripts/dsl_stage0.py --indicator avsl \
      --param fast=52,134 slow=26,52,134 \
      --risk atr_period=7,14 tp_atr_multiplier=1.5,2.0 \
      --bars 1m 15m --years 2.5 --data data/okx21 \
      --out runs/dsl/stage0.json

Output: per-candidate, per-base entry rate, long/short balance, win
rate, average realised R — printed and saved.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ai.src.config import load_config, risk_kwargs  # noqa: E402
from marketdata.common import get_source  # noqa: E402
from scripts.prepare_okx_dataset import (  # noqa: E402
    compute_atr,
    compute_indicator_columns,
    compute_tp_sl,
    detect_order_blocks,
    generate_labels_from_strategy,
    resolve_assets,
)


def _parse_grid(pairs: list[str]) -> dict[str, list]:
    """Parse ``k=v1,v2`` repeats into ``{k: [v1, v2]}`` (typed values)."""

    def _typed(v: str):
        for cast in (int, float):
            try:
                return cast(v)
            except ValueError:
                continue
        return v

    grid: dict[str, list] = {}
    for pair in pairs:
        key, _, vals = pair.partition("=")
        if not vals:
            raise SystemExit(f"--param/--risk entry {pair!r} needs k=v1,v2")
        grid[key.strip()] = [_typed(v) for v in vals.split(",")]
    return grid


def _label_stats(action: np.ndarray, outcome: np.ndarray) -> dict:
    entries = action >= 1
    n = int(entries.sum())
    if n == 0:
        return {"n_entries": 0}
    res = outcome[entries]
    decided = res[(res == 0) | (res == 1)]  # 2 = ignore
    return {
        "n_entries": n,
        "entry_rate": round(n / len(action), 5),
        "long_share": round(float((action[entries] == 1).mean()), 4),
        "win_rate": (
            round(float((decided == 1).mean()), 4) if len(decided) else None
        ),
        "avg_r": round(float(decided.mean()), 5) if len(decided) else None,
    }


def _run(args: argparse.Namespace) -> None:
    """Build the candidate grid, evaluate labels per candidate, save."""
    from ta.src.provider import BINDINGS

    if args.list:
        for name, b in sorted(BINDINGS.items()):
            print(f"{name}: {b.default_params}")
        return

    ind_grid = _parse_grid(args.param) if args.param else {}
    risk_grid = _parse_grid(args.risk) if args.risk else {}
    ind_keys = sorted(ind_grid)
    risk_keys = sorted(risk_grid)
    candidates: list[dict] = []
    if args.indicator:
        if args.indicator not in BINDINGS:
            raise SystemExit(
                f"unknown binding {args.indicator!r}; see --list"
            )
        for values in itertools.product(*(ind_grid[k] for k in ind_keys)):
            candidates.append(
                {
                    "indicator": args.indicator,
                    "params": dict(zip(ind_keys, values, strict=True)),
                    "risk": {},
                }
            )
    for values in itertools.product(*(risk_grid[k] for k in risk_keys)):
        candidates.append(
            {
                "indicator": None,
                "params": {},
                "risk": dict(zip(risk_keys, values, strict=True)),
            }
        )
    if not candidates:
        candidates.append({"indicator": None, "params": {}, "risk": {}})

    base_risk = load_config(risk_profile=args.profile).risk
    src = get_source(args.source)
    resolved = resolve_assets(src, args.assets, args.bars, args.years)
    bars_ms = src.BAR_MS
    base_bar = args.bars[0]
    ctx_bars = [b for b in args.bars if bars_ms[b] > bars_ms[base_bar]]

    results: list[dict] = []
    for cand in candidates:
        overrides = (
            {cand["indicator"]: cand["params"]} if cand["indicator"] else None
        )
        risk = (
            replace(base_risk, **cand["risk"]) if cand["risk"] else base_risk
        )
        row = {
            "indicator": cand["indicator"],
            "params": cand["params"],
            "risk": cand["risk"],
        }
        for _src_name, inst_id, asset_src in resolved:
            max_bars = int(asset_src.bars_per_year(base_bar) * args.years)
            df = asset_src.fetch_candles(
                inst_id,
                bar=base_bar,
                max_bars=max_bars,
                cache_dir=Path(args.data),
            )
            # warm the HTF caches too (needed later by stage 1/2)
            for htf in ctx_bars:
                asset_src.fetch_candles(
                    inst_id,
                    bar=htf,
                    max_bars=int(
                        max_bars * bars_ms[base_bar] / bars_ms[htf]
                    )
                    + 300,
                    cache_dir=Path(args.data),
                )
            df, _cols = compute_indicator_columns(
                df, param_overrides=overrides
            )
            atr = compute_atr(df, risk=risk)
            obs = detect_order_blocks(df, atr, timeframe=base_bar)
            # stage 0 ranks configs on base-TF OBs only; HTF OB features
            # are re-added at stage 1/2 when candidates survive
            tp, sl = compute_tp_sl(df, risk=risk)
            df = df.with_columns(
                pl.Series("tp", tp), pl.Series("sl", sl)
            )
            action, outcome = generate_labels_from_strategy(
                df, obs, **risk_kwargs(risk)
            )
            row[inst_id] = _label_stats(action, outcome)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"stage0 done: {len(results)} candidates -> {out}")


def main() -> None:
    """Run the stage-0 grid over warm caches and report label stats."""
    ap = argparse.ArgumentParser(description="DSL search stage 0 (labels)")
    ap.add_argument("--data", default="data/okx21", help="raw-cache dir")
    ap.add_argument(
        "--profile",
        default=None,
        help=(
            "named risk profile from configs/ai.yaml ('default' or e.g. "
            "'wide'); default follows the yaml risk_profile key"
        ),
    )
    ap.add_argument("--source", default="okx")
    ap.add_argument(
        "--assets",
        nargs="+",
        default=["BTC-USDT", "ETH-USDT", "SOL-USDT"],
        help="reference assets for label statistics",
    )
    ap.add_argument("--bars", nargs="+", default=["1m", "15m"])
    ap.add_argument("--years", type=float, default=2.5)
    ap.add_argument(
        "--indicator",
        default=None,
        help="binding name to override (see --list); omit = defaults only",
    )
    ap.add_argument(
        "--param",
        action="append",
        default=[],
        help="indicator param grid, k=v1,v2 (repeatable)",
    )
    ap.add_argument(
        "--risk",
        action="append",
        default=[],
        help="risk param grid, k=v1,v2 (repeatable)",
    )
    ap.add_argument("--out", default="runs/dsl/stage0.json")
    ap.add_argument(
        "--list", action="store_true", help="list bindings and exit"
    )
    args = ap.parse_args()
    _run(args)


if __name__ == "__main__":
    main()
