# passed — production-frozen strategies

Configurations that cleared their **full pre-registered battery**
(dates frozen before run, gates frozen before run, kill rules
binding) and are promoted here as frozen production references.
**A PASS here is a regression contract, not an invitation to tune.**

Rules of this folder:

1. One module per strategy, **self-contained** (never imports from
   `experiments/` — the evidence trail lives there, this is the
   frozen core).
2. Every module docstring carries the full provenance chain
   (STATUS.md anchors + commit hashes) and the frozen verdict
   numbers. **Any change that moves those numbers voids the PASS**
   and reopens the strategy as a NEW hypothesis (new dated prereg
   in STATUS.md).
3. Signal parameters, universe, fees, split and gates are frozen.
   Sizing/risk-overlay changes are NOT part of a passed module's
   freeze — but they too require a new prereg (see the AVSL
   history: sizing changed once, via the risk-overlay track).
4. Each module has unit tests in `engine/tests/test_passed_*.py`
   (pure functions) plus a runnable self-check that must reproduce
   the frozen numbers on the archived data.
5. Verified-forbidden changes are recorded in the module and here
   (measured, not guessed) so nobody re-tests them "just in case".

## Strategies

### `avsl_cross_s1` — AVSL-cross 4H + S1 vol-target (PASS 5/5, 2026-09-22)

The first strategy in project history with a statistically
significant gross edge, killed at fixed sizing, revived through a
pre-registered sizing-only track.

| item | value |
|---|---|
| Signal | close × AVSL(70,345) cross, 4H, normal arm |
| Stop / exit | max(\|close−line\|, 2×ATR14) · TP 5R · MTM 500 bars · stop-first |
| Universe | BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP (Binance 1H→4H) |
| Sizing | S1 vol-target: `clip(0.20/rv100, 0.25, 2.0)`, 1% equity per size unit |
| Segments | PRIMARY = first 2/3 · F3 = last 1/3 (F3 = holdout) |

**Frozen verdict numbers** (`uv run python -m engine.passed.avsl_cross_s1`
must reproduce them; evidence `runs/risk_overlay.log`):

| metric | PRIMARY | F3 | gate |
|---|---|---|---|
| Sharpe_NW (accrual, lags 500) | **+1.50** | **+2.84** | ≥ 1.0 both ✅ |
| Portfolio DD (1%/slot sized) | **22%** | **12%** | ≤ 25% both ✅ |
| Net EV per trade | +0.17R | +0.33R | ≥ 0.10R both ✅ |
| Positive-net-EV assets | 9/10 | 7/10 | ≥ 7/10 both ✅ |
| Block bootstrap CI (block 500) | excl. 0 | excl. 0 | excl. 0 both ✅ |

Significance of the underlying signal (confirm track, 2026-09-21):
NW-z **+3.31 / +3.85** (lags 500) — the edge is real, not overlap
inflation.

**Provenance:** screen prereg `bb5098b` → 4H anomaly on record →
confirm verdict `1e0e859` (5/6 PASS, DD 61% FAIL at fixed 1%/slot
sizing) → risk-overlay prereg `b6005ca` (S1–S4 frozen, risk-first)
→ **S1 selected** `e6b4b4d`. Full text: STATUS.md, sections
"AVSL-CROSS 4H", "RISK-OVERLAY TRACK".

**Measured-forbidden for successors** (do not re-test without a new
prereg; each cost a full run):

- **Concurrency caps** (max-open / max-exposure): cut DD to 21% but
  destroy the PRIMARY edge (Sharpe 0.22, EV +0.02R, CI covers 0).
  Clustered entries carry the edge; the cap amputates it.
- **ATR-percentile regime scaling alone** (×0.5/×0.25 top deciles):
  leaves DD at 57%/28% — far too loose.

**Decomposition (E1–E5, 2026-09-22 — diagnostic, config untouched):**
движок = 4H grid + wide-TP asymmetry; AVSL cross — усилитель
(+0.037R/+0.167R над matched null), только 4H (1D мёртв); режим =
low-vol + 2025+ (2023-24 на holdout мёртв); S1 = de-lever +
vol-timing (на PRIMARY погранично). Полный текст: STATUS,
«DECOMPOSITION COMPLETE». Любое изменение, вдохновлённое этой
картой (trailing, 3×ATR, режимные фильтры) = новый датированный
прег и закрытие этого модуля.

**Known limitations / honesty notes:**

- PRIMARY DD sits 3pp under the cap — PASS, but not headroom.
- EV in R is sizing-invariant; account-level growth at mean size
  0.33 is ~1/3 of the unsized variant — that is the price of the
  risk gate, and it is the point.
- Numbers are pre-live-scale: a separate live-scale prereg
  (sizing in account terms, venue, slippage, monitoring, kill
  switch) is required before any real capital. This module is a
  frozen research reference, not an execution bot.

## Status of the family

The AVSL-cross **entry family remains CLOSED** for further entry
variation (STATUS 2026-09-21). What is alive is exactly this
module: the frozen signal + frozen S1 sizing, waiting on a
live-scale prereg.
