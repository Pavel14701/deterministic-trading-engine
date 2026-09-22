# -*- coding: utf-8 -*-
"""RESEARCH presets for the OB detector on the 4H grid (E8 track).

These are NOT live-trading presets.  Live presets (1m..1d in
``ta/src/custom/market_structure/configs.py``) are quality-first:
the "4h" live preset yields only 9-34 blocks/asset -- useless for
EV statistics.  Research presets trade selectivity for sample size.
NEVER use a research preset for live trading or a live preset for
EV research (STATUS, OB ENGINEERING PLAN).

Derivation (measured by ``filter_ablation.py``, runs/ob_ablation*.log):
the live "4h" preset's block killers are the market-structure
filter (x2), min_extreme_gap=8 (x2.3) and the breakout volume
condition (x2.5); the reversal threshold and the fixed lookback
window are the remaining sample-size levers.  Prominence and
zigzag_distance are no-ops for the online ZigZag; ADX is absent
from the "4h" preset entirely.

Detector LOGIC IS UNTOUCHED: repaint-free online ZigZag, look-ahead
guards (confirm_idx < break_idx) and deterministic output are
non-negotiable and still covered by the ta test suite.
"""

from __future__ import annotations

import dataclasses

from ta.src.custom.market_structure.configs import (
    OrderBlockConfig,
    get_order_block_config,
)


#: Shared research base: the live "4h" preset with the three heavy
#: quality filters removed.  Keep zone geometry (range source,
#: +0.2 ATR extension), retest logic and strength computation as-is.
RESEARCH_BASE: dict = {
    "use_market_structure_filter": False,
    "require_complete_window": False,
    "min_extreme_gap": 0,
    "breakout_volume_threshold": 0.0,
    "reversal_atr_multiple": 0.8,
}

#: R1 conservative, ~250-320 blocks/asset on the 4H grid.
R1: OrderBlockConfig = dataclasses.replace(
    get_order_block_config("4h"), **RESEARCH_BASE)

#: R2 balanced, ~570-650 blocks/asset: R1 + a zone may re-signal
#: after each new breakout (multiple retest events per zone).
R2: OrderBlockConfig = dataclasses.replace(
    R1, multiple_breakouts=True)

#: R3 aggressive, ~950-1100 blocks/asset: R2 with the fixed
#: [lookback_min, lookback_max] breakout window instead of the
#: dynamic 2*ATR window (the dynamic window shrinks in calm regimes
#: and hides blocks -- the same variable that carries the E5 lift).
R3: OrderBlockConfig = dataclasses.replace(
    R2, use_dynamic_lookback=False)

#: R4 diagnostic ONLY (structure filter cost at research settings,
#: ~100-120 blocks/asset): fails the 200-block acceptance floor by
#: design and must never back an EV test.
R4_DIAGNOSTIC: OrderBlockConfig = dataclasses.replace(
    R1, use_market_structure_filter=True)

RESEARCH_PRESETS: dict[str, OrderBlockConfig] = {
    "R1": R1,
    "R2": R2,
    "R3": R3,
    "R4_diagnostic": R4_DIAGNOSTIC,
}
