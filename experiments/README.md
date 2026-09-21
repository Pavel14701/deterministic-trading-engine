# Experiments catalog

Every experiment is a runnable library module:

```bash
uv run python -m experiments.<name> [args]
```

Results land in `runs/` (JSON/log artifacts); every verdict is recorded
in **STATUS.md** with a pre-registration where applicable. This file is
the INDEX; STATUS.md is the evidence trail. Negative results are kept
on purpose — a closed track stays closed per its pre-registration
(no re-tuning, revival requires a NEW prereg).

Status legend:

- 🟢 **ACTIVE** — track alive; params frozen by prereg, result pending
- ⚪ **INFRA** — data loader / builder, no gates, safe to re-run (all
  caches are resumable page-caches)
- 🟡 **SURVIVOR** — passed its gates; the one live trading track
- ⚫ **CLOSED** — gate(s) failed per prereg; verdict final
- 🏛️ **HISTORICAL** — ran before the D.13g simulator fix (gap-through-
  stop artifact); its positive numbers are INVALIDATED. Kept for
  protocol archaeology. Do not quote artifacts from this group.

## 1. Data loaders & dataset builders ⚪

| module | what it produces | notes |
|---|---|---|
| `load_okx` | `data/okx21/raw_{SYM}-USDT_{TF}.parquet` — OKX OHLCV, 34 assets, 15m/1H/4H/1D | resumable, depth grows run over run |
| `load_yf` | `data/yf/` — Yahoo fallback in the okx21 schema | 15m→60d, 1h→730d limits |
| `load_binance` | `data/binance/kl_*` (1H klines **with taker_buy_volume**, ~6.8y) and `data/binance/oi_*` (OI, **merge-append**: run ≥1×/30d to accumulate) | the TTF v1 / ProSP v2 feature source; OI accumulation track |
| `engine.infra.marketdata.okx_fetch` | fetcher lib: `fetch_candles`, `fetch_funding_history` | OKX funding API serves only ~94d (verified) |
| `engine.infra.marketdata.binance_fetch` | fetcher lib: `fetch_klines`, `fetch_oi_history` | Binance OI endpoint hard-capped at 30d (verified) |
| `engine.datasets.okx` | multi-TF research dataset from live OKX | `python -m engine.datasets.okx` |
| `engine.datasets.mtf` | MTF entry-candidate dataset (stage A.3–A.5): 6 structural families × stop-rule panel | `python -m engine.datasets.mtf` |
| `engine.datasets.stops` | stop-selection dataset (stage 0.7): every OB entry × 11 stop rules × targets | `python -m engine.datasets.stops` |

## 2. Live tracks 🟢🟡

| module | status | question / state |
|---|---|---|
| `funding_carry_v3` | 🟡 **PASS all gates** (STATUS 2026-09-20) | per-asset hold-until-sign-flip carry, Binance 3y. 28/29 assets Sharpe_NW≥1, portfolio 5.19, maxDD 0.55%. Declared decay by fold: +13.5% → +3.75% → +1.45% ann (crowding). Params FROZEN. Next: OKX 96d tradability re-validation + execution design prereg |
| *(pending)* TTF v1 | 🟢 preregistered, module NOT yet written | taker-flow divergence (Binance klines, 6 majors, gates T-G1..G4) — prereg: STATUS 2026-09-21 |
| *(pending)* ProSP v2 | 🟢 preregistered, module NOT yet written | tail-probability portfolio (LGBM + isotonic, flow/funding features, gates P-G1..P-G3) — prereg: STATUS 2026-09-21 |
| *(pending)* Order flow | 🟢 design spec only, no code (STATUS 2026-09-20) | aggressor-signed trade delta, OFI, needs WS collector; not started until explicitly green-lit |

## 3. Carry & probability tracks ⚫

| module | verdict | what it decided |
|---|---|---|
| `funding_carry` | ⚫ REJECTED | v1 daily cross-sectional rotation: carry +1.59bp/d vs costs 10.5bp/d → net −32.6% ann. 96d OKX panel too thin |
| `funding_carry_v2` | ⚫ FAIL primary gate | weekly rotation collapses gross 1.6→0.68bp/d — **cross-sectional funding extremes mean-revert within days**. Maker cut is 1.5× not 5× (spot leg dominates). Secondary gate (per-asset slow carry) → became v3 |
| `barrier_prob` | ⚫ FAIL all gates | P(TP-first) NOT predictable from price/vol/structure features: model Brier 0.21747 > baseline 0.21688; measured P = 0.329 vs Brownian 0.333 (theory confirmed = no drift edge). v2 direction: flow/positioning features (→ ProSP v2) |

## 4. Entry-signal families ⚫ (all: gross edge ≈ 0 net of costs)

| module | verdict | what it decided |
|---|---|---|
| `avsl_baseline` | ⚫ | AVSL×SMA cross, BTC 15m, pre-registered: EV negative; pocket did not replicate on holdout |
| `avsl_price_cross` | ⚫ | price×AVSL cross, normal + reverse arms: 1-2/4 assets positive only |
| `avsl_trailing` | ⚫ | 3 trailing-stop variants: none beat the static benchmark |
| `donchian_breakout` | ⚫ FAIL | 4H DC breakout, 6 majors: recov gate 16/34 < 17 → **Donchian family closed entirely** |
| `quattro_donchian` | ⚫ FAIL | DC20+SMA200+1.2ATR+2.75ATR trail: G3 recov 2/6, pooled PF 1.05. Declared post-hoc one-shot, no tuning |

## 5. Order-Block rework (D.15, ta pipeline) ⚫

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

## 6. Champion-stack panel experiments 🏛️ (HISTORICAL — pre-D.13g sim fix)

All of these ran on the pre-fix simulator / panel whose labels booked
gap-through-stop entries as ~+1R wins (8–12% of rows) and wrong-side
stops as instant wins (8.7%). The chain produced the +0.44R / +466R
headline numbers that were later RETIRED (STATUS, D.13g). The protocol
designs (WF folds, embargo, nested CV, admission semantics) remain the
repo standard; the artifacts do not.

| module | question it answered (historical verdict) |
|---|---|
| `walk_forward_ab` | per-asset (A) vs multi-asset LGBM (B) under WF 8×56d — B won 6/8 → champion head |
| `matrix_2x2` | 2×2 data×model decomposition — TRF rejected causally (D−B bootstrap [−0.507,−0.188]) |
| `nested_cv` | hyperparameter selection bias — measured −2.2% discount |
| `admission_policies` | FCFS vs REPLACE-low slot admission — REPLACE-low +28% EV (mechanism insight survives; the EV level does not) |
| `portfolio` | block-bootstrap DD on the WF trade stream — daily aggregation ~30% optimistic |
| `robustness` | block-length sensitivity, event-vs-daily DD, capped-out trade distribution |
| `execution_costs` | pessimistic cost model: slip ×2, gap G×ATR — the pess/optimistic spread convention |
| `maker_entry` | maker-or-skip vs market — REJECTED: total adverse selection, lift −0.41R (conclusion stands) |
| `cost_cap` | cost-aware row cap + AVSL-off — cap is a DD lever, not free EV |
| `ranker_only` | free ranker gate vs rule-table gate |
| `ranking_baselines` | cost-aware stop-rule ranking head (LambdaRank over 11-rule panel) |
| `feature_family` | DSL feature family A/B vs hand-built features |
| `joint_rank` | joint (stop rule × TP target) ranking — REJECTED |
| `adaptive_tp` | MFE/MAE head → adaptive TP: regime-TP rejected (noise); adaptive TP = same EV, ~½ DD |
| `ablation` / `ablation_diag` | OB/AVSL detector ablation — **detectors carry no edge, geometry did** (and the geometry edge was the artifact) |
| `regime_diag` | causal regime trigger for weak folds — none found; recorded to stop a wrong stop-floor |

## 7. Current-panel diagnostics ⚫

| module | verdict | what it decided |
|---|---|---|
| `ensemble_ab` | ⚫ | LGBM+CatBoost+logreg ensemble grid on the REBUILT panel: whole grid negative ("dead pool") → keep LightGBM-only; ensemble package stays as infra |

## Conventions for new experiments

1. **Pre-register before running**: rules, params, gates, eval windows —
   into STATUS.md (see TTF v1 / ProSP v2 for the format). A parameter
   touched after the first run kills the track.
2. **Gates on PRIMARY windows only**; report fold-by-fold decay — it is
   the crowding signal, not a bug.
3. **Pessimistic sim first** (SL-first, slip, gap-through-stop scratch),
   gross EV before costs, composition sanity (hold, win/exit mix)
   before trusting any headline number (lesson: D.13g).
4. Negative results stay: module kept, verdict in STATUS.md, row added
   here with ⚫.

