# E8b ADJUDICATION — OB track closure record

**Date:** 2026-09-23
**Inputs:** E8b verdict PASS (WEAK) `95c06e2`; confirmation+sizing
run under frozen prereg `83c2b3f`, result `c274f96`
(`runs/ob_risk_overlay.log`).
**Decision:** E8b PASS (WEAK) → **FAIL (adjudicated under true
grid alignment)**. OB **CLOSED FINAL**, one-shot preserved.
**Runbook:** `experiments/ob/README.md`.

---

## 1. Adjudication logic

The E8b verdict stream metrics (Sh / DD / CI) were computed on a
portfolio stream built with **asset-local bucket indices** (legacy
convention of `retest_entry.py`, inherited by E6–E8). The 10 Binance
4H series start at buckets 109056..111302 (~374d spread), so late-
listed assets' trades were placed up to ~2246 buckets (~374 days)
too early in the stream. The prereg `83c2b3f` run recomputed the
**identical frozen frame** (same detector R2, same 9571 trades, same
S1 sizing) under **true global alignment**. This is not an E8b
re-run: same data, same signal, no new multiplicity — a
convention-free recompute of the already-issued verdict's own
inputs, adjudicated by principal decision.

Trade-set identity check: overlay run total = 5862 + 3709 = 9571 =
E8b total (6613 + 2958). Per-trade EVs agree to ~0.01R; segment
sizes differ only because the split boundary is applied to different
(local vs global) clocks.

## 2. E8b gates, legacy vs true alignment (S1-sized stream)

| Gate | Threshold | Legacy (E8b verdict) | True alignment | Verdict |
|---|---|---|---|---|
| E-a | EV > null + 0.05R | PASS (+0.165 / +0.251) | **PASS** (+0.151 / +0.255 vs 0.047±0.024 / 0.077±0.036) | PASS |
| E-b | ≥ 95th null pct | PASS (100th) | **PASS** (100th / 100th) | PASS |
| E-c | Sharpe_NW ≥ 1.0 | PASS (legacy 2.10-level) | **PASS** (+1.40 / +1.29) | PASS |
| E-d | DD ≤ 25% | PASS (6% / 17%) | **FAIL PRIMARY: 29%** (F3 23% PASS) | **FAIL** |
| E-f | boot CI > 0 | PASS | **PASS** ([+0.016,+0.058] / [+0.028,+0.154]) | PASS |

**Overall: FAIL (E-d PRIMARY).** Verdict driver is pure stream
alignment, not the signal: per-trade EV and the matched-null
percentile comparison (the revival question E8b was designed to
answer) are convention-free and PASS comfortably.

Raw (1×) arm under true alignment: DD 86% / 62% — the account-level
risk is structural, not a sizing artifact.

## 3. Root cause (measured, prereg `83c2b3f` read-outs)

1. **Short side in the PRIMARY window:** short EV −0.169R
   (n=2938, WR 18%) vs long +0.473R (n=2924, WR 27%). In F3 both
   sides are positive (+0.268 / +0.243) — the asymmetry is
   period-specific (bull window), i.e. beta exposure, not a broken
   detector.
2. **Overlapping clusters:** 9571 entries over 15251 buckets with
   horizon 500 → deep overlap; DD accrues in clusters, not single
   trades.
3. **Not a vol-regime event:** S5 (ATR-pct > 80 → ×0.5) leaves DD
   at 29% — the DD events sit in ordinary-vol periods; vol-based
   instruments cannot reach them.

Per-trade edge is real (null 100th pct both segments, 9/10 assets
positive pooled, corr with AVSL S1 only +0.13/+0.10). The
account-level risk profile is not survivable in this universe.

## 4. What survives / what dies

- **Survives (ledger facts, convention-free):** OB per-trade edge
  vs matched random geometry (100th pct); 9/10 assets positive;
  low-vol quintile monotonicity (Q1 +0.333R → Q5 +0.102R);
  diversification vs AVSL (+0.13 / +0.10); descriptive TP
  dominance of 8R (+0.235 / +0.327).
- **Dies:** OB as a deployable track under the frozen frame. No
  sizing rescue exists inside the frozen arm set (S1/S5 breach G2'
  PRIMARY at 29%; S3 toxic — 90/9571 kept, EV −0.07R/−0.22R;
  concurrency cap kills the edge exactly as it did for AVSL).

## 5. Revival tracks — BACKLOG ONLY, NOT PRE-REGISTERED

Nothing below is a prereg. Each is a **new hypothesis** with its own
multiplicity budget; if ever run, each requires a dated pre-reg in
STATUS **before code**, a new family tag (NOT the E8 family), and
the same gates G1'–G5'. Writing them here records intent space, not
commitment — do not run to "rescue" OB.

| Tag | Hypothesis | Notes / risks |
|---|---|---|
| R-OB-1 | OB long-side only (R2 demand blocks), S1 sizing | Long EV +0.473/+0.268 already measured convention-free; DD unknown (no run). Cleanest story: "demand-block edge is real, supply-block is the structural problem". |
| R-OB-2 | Full OB, vol-target 12% (vs 20%) | Correction to the forecast floating in review: **sizing does not change per-trade EV**, so G3' stays +0.151/+0.255 (not ×0.6) and Sharpe is scale-invariant — only DD scales (~29%→~17%). That means all 5 gates pass **by construction**: this is sizing-tuned-to-gates, the exact cherry-picking pattern the one-shot rule exists to prevent. Highest PASS probability, lowest evidentiary value. |
| R-OB-3 | TP 8R as PRIMARY (fresh pre-reg) | Descriptive EV is the best of the grid (+0.235/+0.327), but hit rate drops and the 8R number was read AFTER the run — it is post-hoc today; only a fresh dated pre-reg on untouched grounds legitimizes it. |

Standing rule: no revival pre-reg may be motivated or timed by a
just-observed failure mode of the closed track.

## 6. Consequences

- OB ledger: E6 → E7 → E8 → E8b PASS(WEAK) → **FAIL (adjudicated
  2026-09-23)**. OB **CLOSED FINAL**; `min_extreme_gap`/wick-entry
  policy items remain moot; no live exposure ever authorized.
- Detector fixes (pivot+50 breakout, look-ahead median) remain
  validated engineering improvements — recorded, but with no
  surviving track to serve.
- Focus returns to **AVSL**: Phase A clock (seed → first online
  `update` on the online machine), cron per
  `experiments/live/README.md`, weekly snapshots to STATUS.
