# ob — Order-Block rework pipeline (D.15, ta pipeline) — all CLOSED

Run: `uv run python -m experiments.ob.<name> [args]`

| module | verdict | what it decided |
|---|---|---|
| `ob_raw_ev` | ⚫ | first look-ahead-clean OB test (online ZigZag, confirm-guarded): raw EV ≤ 0 net of costs |
| `ob_wf_ev` | ⚫ | OB pipeline EV under the WF fold calendar: no tradable edge |
| `ob_delay_curve` | ⚫ | retest-delay buckets: no bucket passes train criterion |
| `ob_ldgrid` | ⚫ | L×delay EV surface incoherent |
| `ob_lookback13` | ⚫ | lookback ablation: 13 vs 30 — no lift → **OB-retest on 15m CLOSED per prereg** |
| `ob_lookback_grid` | ⚫ | L grid × TP grid: no coherent cell |
| `ob_holdout_assets` | ⚫ | working point does not transfer to holdout assets |
| `ob_struct_diagnostics` | ⚫ (info) | bars/ATR, AR(1) half-life diagnostics: impulse structure too short-lived at 15m |

## Research presets (SHIPPED 2026-09-22, commit b6e2158) — numbers HISTORICAL

**2026-09-22 detector audit (`detector_audit.md`):** the detector
had real defects (fixed the same day): the "dynamic lookback" was a
units bug pinning the breakout delay at pivot+50; the ATR-median
reversal threshold read the full series (look-ahead); the structure
filter read unconfirmed pivots (only in presets where it is ON);
liquidity tolerance was absolute (no-op); no zone-intact guard.
Several review claims were REFUTED (see the audit).  E8's KILL
verdict stands for the detector AS TESTED; the OB track stays
CLOSED.  Block counts below are pre-audit numbers and no longer
reproduce.

Live presets (1m..1d) are quality-first.  Pre-audit SHIPPED family
(research_presets.py): R1 conservative ~273-672, R2 balanced
~575-1146, R3 aggressive ~793-1146 blocks/asset, R4_diagnostic =
structure-filter cost (reference-only).  Acceptance was PASSED on
all 10 assets pre-audit (research_preset_check.py ->
runs/ob_research_check.log); the live-preset regression baselines
("1h"=131, "4h"=10) are STALE (post-fix smoke: "4h" 30-83
blocks/asset).  E8 ran on R2 per prereg (STATUS, commit 7105724) ->
FAIL/KILL (runs/retest_e8.log): OB-retest is 0th null percentile
on PRIMARY.
NEVER use a research preset for live trading or a live preset for
EV research.
