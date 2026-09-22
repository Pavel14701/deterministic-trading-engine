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

`ta/tests/tests_custom/test_market_structure.py`: 46 existing + 5 new
regression tests (causal reversal threshold, breakout window scan,
zone-intact guard, structure-filter confirm guard, price-scale
invariance of the relative liquidity tolerance).  Full suite:
410 passed, 6 skipped.  ruff clean, mypy clean.

