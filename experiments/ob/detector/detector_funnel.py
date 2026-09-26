# -*- coding: utf-8 -*-
"""Per-stage funnel diagnostics for the OB detector (post-audit).

Mirrors the guard order of ``validate_block_candidates`` exactly and
counts, for one (asset, preset) pair, how many candidates survive
each stage:

    pivots -> breakout candidates -> max_extreme_age -> confirm-guard
    -> min_extreme_gap (causal) -> structure filter -> FVG
    -> zone-intact -> retest bar (entry+volume+displacement) -> confirmed

Read-only diagnostic: it never mutates detector code paths.  Run:

    uv run python -m experiments.ob.detector.detector_funnel BTC R1
    uv run python -m experiments.ob.detector.detector_funnel BTC 4h
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import sys

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import read_1h, repo_root, resample_4h
from ta.src.custom.market_structure import identify_order_blocks
from ta.src.custom.market_structure.blocks import effective_online_reversal
from ta.src.custom.market_structure.candidates import (
    generate_block_candidates,
)
from ta.src.custom.market_structure.filters import (
    check_displacement,
    check_fvg,
    check_zone_entry,
    compute_reaction,
)
from ta.src.custom.market_structure.indicators import precompute_indicators
from ta.src.custom.market_structure.online_zigzag import (
    OnlineZigZag,
    confirmed_pivot_arrays,
)
from ta.src.custom.market_structure.structure import (
    classify_market_structure,
    is_block_aligned_with_trend,
)


def _df_4h(repo, sym: str) -> pl.DataFrame:
    t4, h4, l4, c4, v4 = resample_4h(*read_1h(repo, sym))
    return pl.DataFrame({
        "date": pl.from_epoch(t4, time_unit="ms"),
        "high": h4, "low": l4, "close": c4, "volume": v4,
    })


def funnel(df: pl.DataFrame, cfg) -> dict:
    high = df["high"].to_numpy().astype(np.float64)
    low = df["low"].to_numpy().astype(np.float64)
    close = df["close"].to_numpy().astype(np.float64)
    volume = df["volume"].to_numpy().astype(np.float64)
    dates = np.asarray(df["date"].to_list())
    n = len(high)

    ind = precompute_indicators(close, high, low, close, volume, cfg)
    reversal = effective_online_reversal(cfg, ind["atr"])
    pivots = OnlineZigZag(reversal, cfg.online_reversal_pct).update_series(
        high, low)
    peaks, valleys, _conf, _nxt = confirmed_pivot_arrays(pivots)
    pivot_confirm = {p.idx: p.confirm_idx for p in pivots}
    nxt_idx = [p.idx for p in pivots[1:]] + [-1]
    pivot_next_extreme = {
        p.idx: int(k)
        for p, k in zip(pivots, nxt_idx, strict=False)
    }
    pivot_next_extreme_confirm = {
        p.idx: (pivots[k + 1].confirm_idx if k + 1 < len(pivots) else None)
        for k, p in enumerate(pivots)
    }

    candidates = generate_block_candidates(
        high, low, close, volume, dates, peaks, valleys, ind, cfg)

    peak_list = sorted(peaks.tolist())
    valley_list = sorted(valleys.tolist())
    avg_vol = ind["avg_volume"]
    zlo_arr, zhi_arr = ind["zone_low"], ind["zone_high"]

    st = {
        "pivots": len(pivots),
        "candidates": len(candidates),
        "age_reject": 0,
        "confirm_reject": 0,
        "gap_reject": 0,
        "structure_reject": 0,
        "fvg_reject": 0,
        "zone_intact_reject": 0,
        "no_retest": 0,
        "confirmed": 0,
    }
    for cand in candidates:
        idx, brk = cand["idx"], cand["break_idx"]
        is_supply = cand["block_type"] == "supply"
        if cfg.max_extreme_age > 0 and brk - idx > cfg.max_extreme_age:
            st["age_reject"] += 1
            continue
        cidx = pivot_confirm.get(idx)
        if cidx is None or cidx >= brk:
            st["confirm_reject"] += 1
            continue
        nxt = pivot_next_extreme.get(idx)
        if nxt is not None and nxt >= 0:
            nc = pivot_next_extreme_confirm.get(idx)
            if nc is not None and nc < brk:
                if nxt - idx <= cfg.min_extreme_gap:
                    st["gap_reject"] += 1
                    continue
        if cfg.use_market_structure_filter:
            rel_p = [p for p in peak_list
                     if p <= idx and pivot_confirm.get(p, idx + 1) <= idx]
            rel_v = [v for v in valley_list
                     if v <= idx and pivot_confirm.get(v, idx + 1) <= idx]
            _lab, tdir = classify_market_structure(
                rel_p, rel_v, high, low,
                lookback=cfg.structure_lookback,
                min_consecutive=cfg.min_structure_extremes,
            )
            if not is_block_aligned_with_trend(cand["block_type"], tdir):
                st["structure_reject"] += 1
                continue
        _fvg_present, cont = check_fvg(
            high, low, volume, avg_vol, brk, is_supply,
            cfg.require_fvg, cfg.fvg_tolerance,
            cfg.fvg_volume_multiplier, cfg.fvg_volume_mode,
        )
        if not cont:
            st["fvg_reject"] += 1
            continue
        zlo, zhi = zlo_arr[idx], zhi_arr[idx]
        if not (np.isfinite(zlo) and np.isfinite(zhi)):
            st["zone_intact_reject"] += 1
            continue
        end = min(brk + cfg.confirmation_window, n)
        if cfg.require_complete_window and end >= n:
            st["zone_intact_reject"] += 1
            continue
        # zone-intact: any pierce between breakout and retest window
        pierce = cfg.max_zone_penetration * (zhi - zlo)
        dead = False
        for k in range(brk + 1, min(end, n)):
            if is_supply and high[k] > zhi + pierce:
                dead = True
                break
            if not is_supply and low[k] < zlo - pierce:
                dead = True
                break
        if dead:
            st["zone_intact_reject"] += 1
            continue
        found = False
        for j in range(brk + 1, end):
            if not check_zone_entry(
                high, low, close, j, zlo, zhi, is_supply,
                cfg.max_zone_penetration, cfg.zone_entry_mode,
            ):
                continue
            if volume[j] <= avg_vol[j]:
                continue
            r_abs, r_pct = compute_reaction(close[j], zlo, zhi, is_supply)
            if not check_displacement(
                r_abs, ind["atr"][j], cfg.displacement_multiplier,
                r_pct, cfg.min_reaction_size,
            ):
                continue
            found = True
            break
        if found:
            st["confirmed"] += 1
        else:
            st["no_retest"] += 1

    # cross-check against the real pipeline
    st["pipeline_confirmed"] = identify_order_blocks(df, cfg=cfg).height
    return st


def _resolve_cfg(name: str):
    from experiments.ob.detector.research_presets import RESEARCH_PRESETS
    from ta.src.custom.market_structure.configs import (
        get_order_block_config,
    )
    if name in RESEARCH_PRESETS:
        return RESEARCH_PRESETS[name]
    return get_order_block_config(name)


def main() -> None:
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    preset = sys.argv[2] if len(sys.argv) > 2 else "R1"
    cfg = _resolve_cfg(preset)
    df = _df_4h(repo_root(), sym)
    st = funnel(df, cfg)
    cands = max(st["candidates"], 1)
    print(f"funnel {sym} preset={preset} bars={df.height}")
    print(f"  pivots            {st['pivots']:>6}")
    print(f"  candidates        {st['candidates']:>6}")
    for key in ("age_reject", "confirm_reject", "gap_reject",
                "structure_reject", "fvg_reject", "zone_intact_reject",
                "no_retest"):
        pct = 100.0 * st[key] / cands
        print(f"  {key:<18}{st[key]:>6}  ({pct:4.1f}% of candidates)")
    print(f"  confirmed         {st['confirmed']:>6}")
    print(f"  pipeline check    {st['pipeline_confirmed']:>6}  "
          f"({'MATCH' if st['pipeline_confirmed'] == st['confirmed'] else 'MISMATCH'})")


if __name__ == "__main__":
    main()
