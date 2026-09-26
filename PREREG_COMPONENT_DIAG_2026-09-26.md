# Prereg: crypto 4H — component-level predictive diagnostic

**Frozen:** 2026-09-26, commit recorded in docs/JOURNAL.md before any run.
**Status:** frozen pre-run. Scope: measurement only. No strategy change.
No modification to `engine/passed/*`. Crypto 4H universe only.

**Goal:** measure predictive content of each candidate component
**independently** — no mixing, no gating, no sizing. Each component gets
its own read-out. Only after all are measured do we decide what
(if anything) enters a strategy.

---

## 0. Why this is not "improve AVSL"

AVSL's edge is execution geometry + crypto 4H microstructure; entry edge
is small. Decomposition says +0.135R comes from exit geometry on random
entries. Tuning AVSL further is optimization on an exhausted source.

This phase adds **new measurements** — variables not in price — and
evaluates whether any of them has genuine predictive content on 4H
crypto. If none do, we close the direction and accept the promoted book
as-is. If one does, we prereg it as a **separate family**, not an AVSL
patch.

---

## 1. Universe and period (frozen)

- **Assets:** BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP (Binance).
- **Bars:** 4H, deterministic resample from 1H via
  `engine/passed/avsl_cross_s1.resample_4h` (first/max/min/last/sum).
- **Period:** full available 1H history per asset (data starts 2019-10
  .. 2020-10, ends 2026-09). The draft's "2017-08" was aspirational;
  data-deferred to what exists. Segments per asset grid:
  PRIMARY = first 2/3, F3 = last 1/3 (`SPLIT_FRAC = 2/3`, parent
  convention).
- **Target variable:** forward log return, `log(C_{t+h}/C_t)`,
  `h in {1, 3, 6, 12, 24}` 4H bars.

---

## 2. Components — each measured separately

### C1. Hurst exponent H (DFA-1)

- **Method frozen:** DFA order-1 on 4H log returns; windows
  `W in {100, 200}`; scales `s in [8, W/4]`, log-spaced, 12 scales;
  H = slope of log F(s) on log s (OLS). Not R/S, not GPH.
- **Read-outs per asset, per segment:** Spearman IC(H_W, fwd_h) and
  IC(H_W, |fwd_h|); distribution of H_W (mean/std/% >0.5/% <0.5);
  H_W at AVSL entry bars vs non-entry bars (Mann-Whitney U);
  conditional AVSL EV by H_W tertile at entry.

### C2. Funding rate (Binance perp)

- **Data:** `data/funding_binance/fbnb_<SYM>.parquet` (8h, ts ms).
  Coverage starts 2023-09 — IC on the overlap only, coverage logged;
  conditional EV tertiles only over trades with funding data.
- **Features (frozen):** `funding_raw` (current 8h rate, ffill to 4H);
  `funding_z30` = z over trailing 30d (180 4H bars, min 60 valid);
  `funding_hi30` = 1 if rate > 90th pct of trailing 30d.

### C3. Open Interest change

- **Data:** `data/binance/oi_<SYM>USDT_1h.parquet` -> 4H **last** value
  (draft said 5m; only 1h exists — deviation recorded, method unchanged).
- **Features (frozen):** `oi_chg_1 = log(OI_t/OI_{t-1})` (4H);
  `oi_chg_24 = log(OI_t/OI_{t-6})`; `oi_z30` = z of oi_chg_24 over
  trailing 30d (min 60 valid).

### C4. Liquidation volume — **SKIPPED (no data)**

No free source in repo. Per the missing-data rule: component skipped,
logged, no data purchases.

### C5. Taker volume imbalance

- **Data:** `taker_buy_volume` from Binance 1H klines; sell = total − buy;
  aggregated to 4H (sum).
- **Features (frozen):** `tbi_1 = (buy − sell)/(buy + sell)` per 4H bar;
  `tbi_6` = rolling 24h (6 bars) sum of tbi_1.

### C6. BTC lead-lag for alts

- **Feature:** `btc_ret_1` = BTC 4H return, shifted by
  `lag in {1, 2, 3}` bars; target = alt forward return at h.
  BTC itself is excluded from C6.

---

## 3. Metrics — same for every component (frozen definitions)

For each component C, asset a, horizon h, segment:

1. **IC** = full-sample Spearman rank correlation of C vs target.
   **t-stat** = Newey-West (Bartlett, lags = 3h) t-stat of the OLS
   slope of rank(target) on rank(C) (valid under h-overlap
   autocorrelation).
2. **Decile spread** = mean fwd return in top decile minus bottom
   decile of C; block bootstrap CI (block = 24 bars, B = 1000,
   seed 11).
3. **Conditional AVSL EV**: promoted-ledger trades (`collect_trades`,
   all 10 assets) split by C tertile at the entry bar; EV(net R) per
   tertile + n. Tertiles per asset over its entry bars, NaN excluded.
4. **Regime overlap** = |Spearman(C, AVSL_signal_state)|;
   `AVSL_signal_state_t = sign(close_t − AVSL_line_t)` (arm state).
5. **Time stability**: identical metrics on PRIMARY and F3.

**No thresholds, no gates.** Read-out phase; interpretation after all
components are measured.

---

## 4. Deliverables

- `runs/component_diagnostic.log` — one block per component per
  horizon (IC/t per asset, decile spread + CI, cond AVSL EV tertiles,
  overlap, stability).
- Final summary table (component / best h / best IC / t / AVSL EV
  spread / overlap / verdict).
- STATUS + JOURNAL entries with verdicts and next step (follow-up
  prereg for a component that passes section 7, or close direction).

---

## 5. Rules of this phase

- **One run per component.** No re-runs if result is weak. Re-run only
  for bug fixes, logged.
- **No mixing components.** Combination is a separate prereg.
- **No strategy modification.** Measurement against the frozen AVSL
  ledger only.
- **Missing data = skip component, log it, move on.**
- **Frozen before run.** Parameters above are not to be tuned after
  seeing any result.

---

## 6. Expected outcomes and priors

| Component | Prior for "real signal" | Reasoning |
|---|---|---|
| C1 Hurst | 15–25% | Literature: descriptive, not predictive; fat tails hurt estimation |
| C2 Funding | 35–45% | Documented positioning signal; less arbitraged on 4H |
| C3 OI change | 30–40% | Coarser than funding; likely correlated with it |
| C4 Liquidations | skipped | no free data |
| C5 Taker imbalance | 25–35% | Weak on 4H; strong intrabar |
| C6 BTC lead-lag | 30–40% | Structural; may already be implicit in AVSL |

Overlap warning: C2/C3/C4 are all positioning — pairwise correlations
logged; same signal across them counts once.

---

## 7. Follow-up criterion (held against multiple comparisons)

600 cells at alpha=0.05 -> ~30 significant by chance. No p-value
threshold is meaningful here. A component earns a follow-up prereg
only if ALL hold:

1. consistent sign across assets (not 3/10);
2. consistent sign across PRIMARY and F3;
3. monotone decile spread (not top-vs-rest only);
4. conditional AVSL EV spread > 0.15R (economically meaningful).

---

## 8. What this is not

Not a Hurst filter, not a funding overlay, not a new strategy, not a
portfolio step, not a modification of any passed module. It is a
measurement of whether non-price crypto 4H data has predictive content,
and if so — which component and at what horizon. Strategy integration
is a later prereg, on a different day, with its own discipline.
