# AVSL live-scale pilot -- operations runbook

Prereg: STATUS.md, "AVSL LIVE-SCALE PREREG (2026-09-22, FROZEN
BEFORE ANY LIVE CODE)".  This directory implements the two files
that prereg names: `parity_check.py` (the PARITY hard gate, g1)
and `pilot_tracker.py` (Phase A bookkeeping).  The frozen signal
module `engine/passed/avsl_cross_s1.py` is imported read-only and
is hash-pinned in the pilot state; ANY change to it invalidates the
pilot.

## State

`runs/live_pilot/state.json` (gitignored, single source of truth):
frozen-module sha, pilot start bucket, last closed bucket per asset,
recorded entries, skipped (brake) entries, paper trades
(provisional until their exit bar closes), events log, snapshots,
F3 reference rate, brake flag.

## Cadence

| command | when |
|---|---|
| `uv run python -m experiments.live.pilot_tracker update` | after EVERY closed 4H bar (cron: 4x daily, >= 15 min after bar close) |
| `uv run python -m experiments.live.pilot_tracker snapshot` | weekly -> paste into STATUS |
| `uv run python -m experiments.live.parity_check` | runs inside every update; standalone after any manual cache surgery |

`--no-fetch` on both: use the local cache without hitting Binance.

## Failure rules (mechanical, never discretionary)

- parity mismatch (repaint, missed entry, nondeterminism, frozen-sha
  change) -> update ABORTS and marks the state; STOP per prereg g1;
  post-mortem before resume; resume is a NEW dated prereg item.
- disaster brake: rolling 90d daily Sharpe < 0 -> brake_on (new
  entries are recorded as `skipped`, never traded); brake_off fires
  mechanically at Sharpe >= 0, but a dated STATUS note is required
  before any real resumption.
- snapshot gap > 14 days = g3 FAIL at Phase A evaluation.

## Phase A gates (evaluated at >= 90d AND >= 50 closed trades)

g1 parity: zero mismatches over the full window (state events).
g2 cost: all-in RT <= 15 bp (paper assumption 10 bp taker RT;
realized-cost tracking activates in Phase B).
g3 brake: zero bypasses, snapshots without gaps.
g4 pilot DD <= 25% (snapshot `pilot_dd`).
g5: the pilot does NOT judge EV significance (n=50 underpowered
by design).

## Paper conventions (declared in the tracker docstring)

Fills at the frozen module's entry convention (cross-bar close),
taker 10 bp RT; a 4H bucket is closed when a later bucket exists
in the cache; trades with an open exit bar stay PROVISIONAL and
are re-priced on later updates; sizing = `s1_sizes` at the entry
bar; accrual mirrors the frozen `evaluate()` (net spread over
hold+1 bars).

## What this is NOT

No order routing, no keys, no real capital (Phase B is a separate
gated step).  The pilot never edits the signal config; any config
change closes the frozen module (see its docstring).
