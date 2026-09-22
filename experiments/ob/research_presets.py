# -*- coding: utf-8 -*-
"""RESEARCH presets for the OB detector on the 4H grid (E8 track).

These are NOT live-trading presets.  Live presets (1m..1d in
``ta/src/custom/market_structure/configs.py``) are quality-first.
NEVER use a research preset for live trading or a live preset for
EV research (STATUS, OB ENGINEERING PLAN).

HISTORICAL NUMBERS (2026-09-22 detector audit, see
``detector_audit.md``): all block-count figures below were measured
on the PRE-AUDIT detector, whose PRIMARY behaviour was a fixed
50-bar breakout delay ("dynamic lookback" units bug) with
no zone-intact guard.  The detector has since been FIXED (causal
reversal warmup, honest breakout window, confirm-guarded structure
filter, relative liquidity tolerance, require_zone_intact=ON), so
R1-R3 now produce DIFFERENT (generally larger, fresher) block sets.
R2 is now identical to R1 (``multiple_breakouts`` was a no-op by
semantics and is ignored); R3's ``use_dynamic_lookback`` is ignored
too.  All OB research tracks remain CLOSED per the family ledger;
any revival on the fixed detector needs a NEW dated prereg plus
fresh acceptance.

Derivation of the ORIGINAL presets (measured by
``filter_ablation.py``, runs/ob_ablation*.log): the live "4h"
preset's block killers were the market-structure filter (x2),
min_extreme_gap=8 (x2.3) and the breakout volume condition (x2.5);
the reversal threshold and the fixed lookback window were the
remaining sample-size levers.  Prominence and zigzag_distance are
no-ops for the online ZigZag; ADX is absent from the "4h" preset.
"""

from __future__ import annotations

import dataclasses

from ta.src.custom.market_structure.configs import (
    OrderBlockConfig,
    get_order_block_config,
)


#: Shared research base: the live "4h" preset with the three heavy
#: quality filters removed.  Zone geometry (range source, +0.2 ATR
#: extension), retest logic and strength computation as-is.
RESEARCH_BASE: dict = {
    "use_market_structure_filter": False,
    "require_complete_window": False,
    "min_extreme_gap": 0,
    "breakout_volume_threshold": 0.0,
    "reversal_atr_multiple": 0.8,
}

#: R1 conservative.  (Historical, pre-audit: ~250-320 blocks/asset.)
R1: OrderBlockConfig = dataclasses.replace(
    get_order_block_config("4h"), **RESEARCH_BASE)

#: R2 balanced: R1 + ``multiple_breakouts``.  DEPRECATED-NOOP: the
#: flag never re-signaled a zone (both branches take the first
#: breakout) and is now ignored entirely -- R2 == R1.  Kept so the
#: frozen E8 prereg string ("preset R2") keeps resolving to the same
#: config object it was frozen with.
R2: OrderBlockConfig = dataclasses.replace(
    R1, multiple_breakouts=True)

#: R3 aggressive: R2 with ``use_dynamic_lookback=False``.  The field
#: is ignored since the detector audit (the dynamic lookback was a
#: units bug); the breakout scan now always uses the full
#: [lookback_min, lookback_max) window for every preset.
R3: OrderBlockConfig = dataclasses.replace(
    R2, use_dynamic_lookback=False)

#: R4 diagnostic ONLY (structure filter cost at research settings):
#: fails the 200-block acceptance floor by design and must never
#: back an EV test.
R4_DIAGNOSTIC: OrderBlockConfig = dataclasses.replace(
    R1, use_market_structure_filter=True)

RESEARCH_PRESETS: dict[str, OrderBlockConfig] = {
    "R1": R1,
    "R2": R2,
    "R3": R3,
    "R4_diagnostic": R4_DIAGNOSTIC,
}
