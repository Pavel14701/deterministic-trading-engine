# Detector audit: market_structure (OB pipeline) — 2026-09-22

External review claimed ~19 structural defects in the OB detector.
Every claim was verified against the code
(`ta/src/custom/market_structure/`) before touching anything.
Verdicts below; the confirmed defects are FIXED in the same commit,
the refuted ones are documented here so the "fix everything" sweep
does not silently re-litigate them.

## CONFIRMED (fixed)

**A1 — `compute_lookback` UNITS BUG (the "fat" claim).**
The "dynamic" lookback multiplied a PRICE-valued median ATR by a
multiplier and used the result as a BAR count, clamped to
`[lookback_min, lookback_max]`.  Any asset priced above roughly
`lookback_max / multiplier` (all 10 research assets except DOGE)
always clamped to `lookback_max=50`.  "Dynamic lookback" was a
disguised constant.  It also read the FULL ATR series (look-ahead).
**FIX:** the "dynamic" concept is deprecated.  The breakout scan now
ALWAYS covers the window `[idx+lookback_min, idx+lookback_max)` bars
after the pivot; the first valid breakout wins.
`use_dynamic_lookback` / `lookback_atr_multiplier` are ignored (kept
for config compat).

**A2 — `multiple_breakouts` SEMANTICS BUG.**
The flag never produced multiple signals per zone: both branches take
the first valid breakout and stop.  `False` additionally restricted
the check to the SINGLE bar `idx+lookback` — with A1 this pinned the
breakout delay at exactly 50 bars (R1: every block broke at
pivot+50; DOGE at pivot+5).  R2's docstring ("a zone may re-signal
after each new breakout") was factually wrong.
**FIX:** folded into A1 — one honest window, first breakout wins.
The flag is ignored (kept for config compat); R2 == R1 now.

**A3 — `effective_online_reversal` LOOK-AHEAD.**
The ATR-calibrated reversal threshold =
`multiple * median(ATR over the WHOLE series)`: future volatility
leaked into the pivot detector.
**FIX:** median over the FIRST `reversal_warmup_bars` (default 500)
finite ATR values only.  Causal and live-reproducible (estimate once
at stream start, freeze).

**A4 — market-structure filter read UNCONFIRMED pivots.**
Validation used `p <= idx` by bar index, ignoring `confirm_idx`: a
pivot whose confirmation bar was after the candidate's pivot bar
could still classify the trend.  (Contrast: `check_orderflow_shift`
was already confirm-guarded.)
**FIX:** online mode now requires `pivot_confirm[p] <= idx`.
NOTE: research presets R1-R3 (and therefore E8) run with the
structure filter OFF — this leak did NOT affect E8.

**A5 — `liquidity_tolerance` was ABSOLUTE price units (default
0.001): a no-op for any asset above ~$25 (BTC: 0.000002%).**
**FIX:** relative fraction of price (0.001 = 0.1% of the pivot
price).  Default value kept, semantics now scale-free.

**A6 — NO zone-pierce guard between breakout and retest:** the zone
could be fully re-broken after the breakout and the first wick back
into it still counted as a "retest" of a dead zone.
**FIX:** new config flag `require_zone_intact` (default ON): no bar
between the breakout and the retest may pierce the zone beyond its
far edge + `max_zone_penetration * span` (same allowance as the
retest bar itself).

## REFUTED (no code change, documented)

**R1 — "avg_vol[j] includes volume[j] and thereby WEAKENS the volume
filter exactly on high-volume bars."**  Direction is wrong.  With SMA
window w and prior sum S, the pass condition
`v_j > (S+v_j)/(w+1)` ⟺ `v_j*w > S`, i.e. the bar must exceed
`S/(w-1)` — STRICTER than the shifted `S/w` by the factor `w/(w-1)`
(5% at w=20).  Inclusion makes the gate tighter, not weaker.
Left as-is.

**R2 — "confirmation_window=36 on 4H = 6 days."**  The "4h" preset
uses the default `confirmation_window=10` (~1.7 days); 36 is
5m/15m only.

**R3 — "zone_atr_multiplier=0.2 is a fixed absolute fraction, not
ATR-scaled."**  It multiplies ATR by construction
(`zone_low = low - m*ATR`).

**R4 — "check_breaker mutates a list during iteration."**  It
iterates a slice and returns a bonus; no mutation anywhere.

**R5 — "`_empty_block_frame` pl.Datetime schema mismatch."**
`pl.Datetime` defaults to `Datetime("us")`, exactly what the
non-empty path builds from python datetimes.  Compatible.

## DESIGN / POLICY (confirmed as described, deliberately NOT changed)

Strategy semantics that any future prereg must choose explicitly —
not library bugs:

- **P1** `zone_entry_mode="wick"` (touch, not rejection).  A "close"
  mode and `require_closure_outside` exist but are off in ALL
  presets.
- **P2** breakout by pivot wick (`low[brk] < low[idx]`), not close.
- **P3** `max_zone_penetration=0.5` allows an overshoot of half the
  zone span beyond the far edge and still calls it a retest.
- **P4** `is_block_aligned_with_trend(None) -> True`: unknown
  structure does not filter.  Matters only when the structure filter
  is ON.
- **P5** `min_extreme_gap` is a pivot-to-next-extreme
  STRUCTURE-MATURITY gap (not an entry delay) and is applied
  causally (only when the next extreme was already confirmed at the
  breakout) — the "inconsistency" is the look-ahead-safe direction,
  by design.
- **P6** `check_displacement`: an ATR path exists
  (`displacement_multiplier`); default 0 leaves the fixed
  `min_reaction_size=0.2%` path active.
- **P7** `strength` is not used as a GATE (only recorded and consumed
  by the breaker bonus, which is off by default).

## CONSEQUENCES (read before citing any OB number)

- Every previously recorded OB number — port-check block counts,
  R1-R3 acceptance (~273-1146 blocks/asset), the ablation, the delay
  curve, and E8 itself — was measured on the OLD detector, whose
  PRIMARY behaviour was "fixed 50-bar delay + wick-touch retest".
- E8's verdict (KILL) stands AS A VERDICT ABOUT THAT DETECTOR AND
  STRATEGY AS TESTED.  The OB research track remains CLOSED.  No
  re-run of closed preregs; a revival (new detector semantics) needs
  a NEW dated prereg plus fresh acceptance on the fixed code.
- The live-preset regression baselines ("1h"=131, "4h"=10 blocks)
  are stale.  Post-fix smoke on the 4H grid ("4h" preset, first 5
  research assets): BTC 64, AVAX 83, BNB 32, DOGE 30, ETH 44 blocks.
  Regression baselines must be re-derived before any further
  live-preset work.

## TESTS

`ta/tests/tests_custom/test_market_structure.py`: batch 1 added 5 new
regression tests (causal reversal threshold, breakout window scan,
zone-intact guard, structure-filter confirm guard, price-scale
invariance of the relative liquidity tolerance) on top of the 29
tests the file already collected.  Full suite: green.  ruff clean,
mypy clean.

=====================================================================
SECOND REVIEW BATCH (same day, 2026-09-22)
=====================================================================

A second review batch arrived (17 + 5 items).  Same protocol: every
claim checked against the code.  NO new code defects were found --
the batch is either (a) already covered by the batch-1 fixes, or
(b) refuted, or (c) policy items now documented below.  One guard
test added (strictly increasing pivot indices).

ALREADY FIXED IN BATCH 1 (credited, no new work):

- "Fixed-offset breakout: `multiple_breakouts=False` + lookback=50
  checks EXACTLY the bar idx+50" -- that is A1+A2 verbatim (the
  quoted code is the OLD code); the pipeline now scans
  [idx+lookback_min, idx+lookback_max).
- "No zone re-pierce check between breakout and retest" -- A6
  (`require_zone_intact`), exactly the suggested guard.
- "`multiple_breakouts` semantics", "None-trend pass-through",
  confirmation-window default-10-on-4h, strength knobs, E8
  cross-asset lookback offsets -- A2, P4, R-2, P7 and the
  CONSEQUENCES section respectively.

REFUTED (batch 2):

R6  "`min_reaction_size=0.002` is absolute, no scale calibration
     (BTC $100 vs $0.002 on a $1 token)".  Wrong: it applies to
     `reaction_pct = reaction_abs / ref_price` (filters.py
     compute_reaction) -- a FRACTION OF PRICE.  0.002 = 0.2% on
     BTC and on the $1 token alike; the quoted $100/$0.002 numbers
     ARE the scale-free behaviour.  (Contrast with the true units
     bug A1.)  The "negative reaction_abs works by accident" add-on
     is also wrong: close beyond the zone's far edge means no
     rejection reaction, and rejecting that is the coherent
     semantic, not an accident.

R7  "Pivot dicts keyed by p.idx can collide (items #9/#17)" --
     impossible by construction.  OnlineZigZag confirms a pivot at
     bar c > pivot.idx and starts the next leg AT bar c, so every
     later pivot index is strictly greater than all previous ones;
     dict keys are unique.  Locked by a new test
     (test_online_pivot_indices_are_strictly_increasing).

R8  "`cluster_blocks` glues blocks in flats -- and R1-R3 run with
     cluster on".  The mechanism exists but the flag is FALSE by
     default and is not enabled ANYWHERE in the repo (grep: no
     `cluster_blocks=True`); all six live presets have it off and
     research R1-R3 inherit the "4h" preset (off).  Dormant, no
     trigger.

R9  "`OrderBlock` is not frozen; `list.copy()` is shallow so
     clustering mutations leak into the caller's list" -- no live
     path: `identify_order_blocks` passes `existing_blocks=[]` and
     `validate_block_candidates` copies it before appending only
     NEWLY created blocks; clustering runs on that private list
     after validation.  Freezing the dataclass is a future
     robustness nicety, not a bug.

R10 "`atr_period=14` is not scaled per timeframe" -- ATR period is
     in BARS by definition; the bar itself carries the timeframe
     scale, which is exactly why every threshold in the pipeline is
     ATR-multiple calibrated (and why the price-scale invariance
     test passes).

R11 "`_empty_block_frame` pl.Datetime is generic / falls apart" --
     repeat of R-5: pl.Datetime defaults to Datetime("us"), same
     as the non-empty path; both branches compatible (covered by
     the empty-frame tests).

R12 "avg_vol including volume[j] makes the filter pass exactly the
     high-volume bars it should reject" -- repeat of R-1 with a new
     conclusion.  Direction still wrong (inclusion TIGHTENS the
     lower bound).  The new part -- "huge retest volume should be
     REJECTED" -- is a two-sided volume CAP, which was never
     specified anywhere; see P9 below.

ADDITIONAL POLICY ITEMS (batch 2; confirmed as described,
deliberately unchanged):

P8  Zones are anchored to the PIVOT-bar ATR (`atr[idx]`): the zone
    is fixed at formation time and is NOT rescaled by retest-time
    volatility.  Causal and standard for OB definitions; if a
    future prereg wants volatility-following zones it must choose
    the `atr[j]/atr[idx]` scaling explicitly.

P9  The retest volume gate is ONE-SIDED (lower bound: volume[j] >
    avg_vol[j]); there is no upper cap.  "Retest on huge volume is
    bearish for the setup" is a strategy hypothesis to be prereg'd,
    not implemented.

P10 The RSI/MACD gate (dead code, off in ALL presets -- grep clean)
    requires rsi >= overbought at a SUPPLY retest, i.e. it gates on
    momentum CONTINUATION, not rejection.  Known and already
    documented in configs.py's rationale as the reason it is off;
    if ever enabled, its semantics must be chosen deliberately.

P11 `min_structure_extremes=3` (live 4h/1d presets where the
    structure filter is ON) classifies only mature trends -- late
    entries by design.  Research presets (and E8) run with the
    filter OFF.

P12 `require_complete_window=True` (4h/1d) drops candidates whose
    confirmation window crosses the end of history -- a documented,
    deliberate backtest-hygiene choice.

P13 `zone_source="range"` builds the zone from the pivot's FULL
    [low, high] (sweep wicks included); "body" and "close_band"
    modes exist but are off in all presets.  Body-based zones are a
    strategy variant a future prereg may choose; also note the
    wick-touch entry (P1) interacts with this: touching the
    wick-end of a range zone counts.

Updated TESTS line: batch 2 added one guard test (strictly
increasing pivot indices); the market_structure test file now
collects 35 tests (34 before).  FULL MONOREPO suite
(`pytest ta/tests engine/tests dsl/tests`; the root `pytest -q`
only runs engine+dsl per ``testpaths``): 2543 passed / 6 skipped,
ruff and mypy clean.

