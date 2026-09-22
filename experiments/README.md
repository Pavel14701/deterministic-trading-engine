# Experiments catalog

Every experiment is a runnable module, grouped by track:

```bash
uv run python -m experiments.<track>.<name> [args]
```

| track | contents | README |
|---|---|---|
| `loaders/` | data loaders & dataset builders (OKX / Yahoo / Binance) | [loaders/README.md](loaders/README.md) |
| `carry/` | funding-carry chain + barrier probability | [carry/README.md](carry/README.md) |
| `avsl/` | AVSL / Donchian entry-signal family | [avsl/README.md](avsl/README.md) |
| `ob/` | Order-Block rework pipeline | [ob/README.md](ob/README.md) |
| `panel/` | champion-stack panel experiments (historical) + current-panel diagnostics | [panel/README.md](panel/README.md) |

Results land in `runs/`; every verdict is recorded in **STATUS.md**
with a pre-registration where applicable. STATUS.md is the evidence
trail; the per-track READMEs are the INDEX. Negative results are kept
on purpose - a closed track stays closed per its pre-registration
(no re-tuning, revival requires a NEW prereg).

> **Read this first.** The +0.44R / +466R headline numbers that appear
> in older docs refer to the RETIRED champion stack (D.13g simulator
> artifact). The only live-defensible result in this repo is
> `carry/funding_carry_v3` - and it is PASS-with-decay (window
> closing), see below.

## Status legend

- SURVIVOR - passed its pre-registered gates; verdict **includes the
  fold-by-fold decay trend**, not just PASS/FAIL
- EXPECTED - pre-registered, gates frozen, module NOT yet written
- SPEC ONLY - design spec exists, NOT pre-registered, no code
- INFRA - data loader / builder, no gates, safe to re-run (all caches
  are resumable page-caches)
- CLOSED - gate(s) failed per prereg; verdict final
- HISTORICAL - ran before the D.13g simulator fix (gap-through-stop
  artifact); its positive numbers are INVALIDATED. Kept for protocol
  archaeology. Do not quote artifacts from this group.

## Live & pending (crypto)

### Working (PASS)

| module | status | decay trend | evidence |
|---|---|---|---|
| `carry/funding_carry_v3` | SURVIVOR - PASS per pre-reg, **but decaying**: F1 +13.5% -> F2 +3.75% -> F3 +1.45% ann (crowding). In the current regime the residual edge is below the risk-free rate - treat as a window that is closing, not a durable strategy. Params FROZEN; next: OKX 96d tradability re-validation + execution design prereg | F1 13.5 -> F3 1.45 %/yr | [STATUS 2026-09-21](../STATUS.md#2026-09-21--data-feasibility-audit--ttf-v1--prosp-v2-preregs--oi-accumulation) |

### Expected (pre-registered, module not written)

| track | gates | prereg | evidence |
|---|---|---|---|
| TTF v1 (taker-flow divergence, Binance klines, 6 majors) | T-G1..G4 frozen 2026-09-21 | yes | [STATUS 2026-09-21](../STATUS.md#2026-09-21--data-feasibility-audit--ttf-v1--prosp-v2-preregs--oi-accumulation) |
| ProSP v2 (tail-probability portfolio, LGBM + isotonic, flow/funding features) | P-G1..P-G3 frozen 2026-09-21 | yes | [STATUS 2026-09-21](../STATUS.md#2026-09-21--data-feasibility-audit--ttf-v1--prosp-v2-preregs--oi-accumulation) |

### Spec only (not pre-registered, no code)

| track | state | evidence |
|---|---|---|
| Order flow (aggressor-signed trade delta, OFI, needs WS collector) | design spec only, pending explicit user go - do NOT start without a prereg | [STATUS: ORDER FLOW -- DESIGN SPEC](../STATUS.md#order-flow--design-spec-no-code-pending-user-go) |

## Market switch (not started)

If the crypto tracks die (carry window closed, TTF/ProSP fail their
gates), the fallback universe is equities / forex / commodities
(funding-like carry analogues: dividend capture, FX forward basis,
roll yield). Status: **nothing started, no data, no prereg.** Priority
rises only when the crypto verdicts land. Any work here starts with a
prereg in STATUS.md, same conventions.

## Conventions for new experiments

1. **Pre-register before running**: rules, params, gates, eval windows -
   into STATUS.md (see TTF v1 / ProSP v2 for the format). A parameter
   touched after the first run kills the track.
2. **Gates on PRIMARY windows only**; report fold-by-fold decay - it is
   the crowding signal, not a bug. Decay is part of the verdict: a PASS
   with steep decay is a closing window, not an asset.
3. **Pessimistic sim first** (SL-first, slip, gap-through-stop scratch),
   gross EV before costs, composition sanity (hold, win/exit mix)
   before trusting any headline number (lesson: D.13g).
4. Negative results stay: module kept, verdict in STATUS.md, row added
   to the track README with a CLOSED mark.
5. New module goes into an existing track folder (or opens a new one
   with its own README); keep this index row-linked.
6. Every live/expected row here carries a STATUS.md anchor - if the
   anchor is missing, the row is not done.
