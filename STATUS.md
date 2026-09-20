# STATUS — what is implemented vs what is needed

Single consolidated summary. Legend: ✅ done · 🔨 in progress / core done · ⬜ not started ·
⬜=spec only. Full per-task detail: `legacy/dev_docs/tz/TZ-00-roadmap.md` (archived).

## 2026-09-20 — ranker ensemble package (`engine/ensemble/`)

- `engine/ensemble/`: `base` (RankerComponent interface, ComponentConfig,
  rank_normalize), `lgbm` / `catboost` / `logreg` components, `combine`
  (EnsembleRanker: mean / weighted / rank_mean / stacking), `meta`
  (stacking meta-learner trained on past-only OOF component scores —
  no in-sample meta weights).  Determinism kit per component:
  LGBM deterministic+force_row_wise+1 thread; CatBoost thread_count=1;
  catboost is an OPTIONAL dependency (lazy import, CATBOOST_AVAILABLE).
- `protocol.train_ensemble_ranker`: ensemble twin of `train_ranker`
  (same contract — past-only train_ix, scores for all rows in input
  order), so replay/experiments switch heads by config alone.
- `experiments/ensemble_ab.py`: pre-registered grid of 6 configs
  (lgbm_only / catboost_only / logreg_only / lgbm+catboost /
  all_three / stacking) through one WF protocol + replay; metrics:
  pooled R / dd / sharpe, decile spread, top-decile EV, flips@1e-6,
  peak gate EV; `--quick` smoke mode.  Acceptance: ensemble beats the
  best single component, dd not worse — else keep LightGBM-only.
- Tests: `engine/tests/test_ensemble_*.py` (45 tests: determinism
  byte-for-byte, dtype discipline, scaler convergence, enable/disable
  vs weight=0, stacking past-only OOF, mini-WF regression, protocol
  integration) + `ens_synth.py` synthetic panel helper.  catboost
  tests skip cleanly when the lib is absent.
- catboost added to root dependencies (installed 1.2.10 locally).
- Fixed a latent restructure bug: `protocol.REPO` pointed at
  `engine/` instead of the repo root (data paths were computed from
  the pre-move location) — experiments had not been re-run since the
  move, first caught by the ensemble_ab smoke run.
- Quick smoke (last 3 folds, catboost 60 iters): lgbm_only leads
  (pess −0.020, spread +0.169); no blend beats it yet.
- FULL run verdict (8/8 folds, all configs, catboost 300 iters,
  runs/ensemble_ab.json): the whole grid is negative (dead pool —
  TZ item 8 predicted the ensemble cannot revive it).  lgbm_only:
  −0.017R (dd 12.6).  No config passes acceptance: lgbm+catboost is
  the only positive-peak-gate head (+0.001 vs −0.014) with the best
  top-decile EV (−0.002) and spread +0.131 (vs +0.062), but worse dd
  (18.1R) and mean R; stacking edges mean R (−0.014) with equal dd
  but weak spread.  DECISION (per TZ item 6): keep LightGBM-only;
  the ensemble package stays as infrastructure, lgbm+catboost 0.5/0.5
  is the only blend worth re-visiting if the pool turns positive.

## 2026-09-20 — tests co-located in engine/, CI subordinated to the layout

- `tests/` -> `engine/tests/`: the unit suite lives inside the package
  it tests (git mv, history preserved).  Depth-dependent paths updated
  (config yaml lookup, ob-pipeline sys.path bootstrap).  dsl/tests
  stays in its own package by design.
- CI now follows the layout exactly: `ruff check engine dsl` (tests are
  inside engine/), `mypy engine` covers the whole package including
  tests, `pytest` runs on `testpaths` from pyproject (engine/tests +
  dsl/tests).  The dead `[tool.mypy-engine]` section (never read by
  mypy) is gone; the strict flags now actually apply via `[tool.mypy]`
  with `ignore_errors` overrides for engine.experiments/.datasets/
  .tests (unannotated by design).
- Root `conftest.py` marker map updated (`-m engine` works on the new
  path); pytest `testpaths` and ruff test ignores generalized to
  `**/tests/**`.

## 2026-09-20 — engine restructure: subpackages, no scripts/, no ID naming

- `scripts/` removed entirely; every experiment driver is now a library
  module under `engine/experiments/` without ID prefixes (wf_ab ->
  walk_forward_ab, d13c_cost_cap -> cost_cap, d13g_ranker_only ->
  ranker_only, d14_feature_family -> feature_family, d14_funding_carry
  -> funding_carry, d13d_regime_diag -> regime_diag).  Experiment
  entry points that lived inside library modules (D.6 joint rank in
  sim, D.11 admission compare, D.12 maker grid) were extracted into
  `engine/experiments/{joint_rank,admission_policies,maker_entry}.py`.
  Artifact filenames in `runs/` for NEW runs lose the d-prefix too
  (old artifacts keep historical names, referenced below).
- `engine/` decomposed into functional subpackages:
  `infra/` (config, datatypes, io, marketdata), `features/`
  (indicators, mtf, panel, dsl_feed, spec, provider, events),
  `structure/` (zones, candidates), `sim/` (engine, maker,
  state_machine, admission), `backtest/` (protocol), `model/`
  (ranker), `metrics/` (trade: trade_curve_stats / per_trade_sharpe /
  bucketed_sharpe / pooled_stats - extracted from the ranker head and
  protocol), `datasets/` (okx, mtf, stops - the former dataset-build
  scripts).
- d-naming scrubbed from code: `ENCODING_D13` -> `ENCODING_ZEROED`,
  `ENCODING_D8B` -> `ENCODING_NATIVE`, docstrings/comments rewritten
  without D.NN experiment IDs (history stays here; archived specs moved
  to `legacy/dev_docs/`).
- Encodings renamed to names again: ENCODING_ZEROED (float32,
  NaN/inf->0) and ENCODING_NATIVE (float64, NaN kept).
- Gates: pytest 327 passed; ruff clean on engine+tests+dsl (research-
  grade zones `engine/experiments/**` and `engine/datasets/**` carry
  explicit per-file-ignores in pyproject); mypy clean on the library
  core (25 files).

## 2026-09-19 — package rename ai -> engine, scripts cleanup

- `ai/` -> `engine/` (the package is the whole research engine, not just
  models): `dte-engine` in the uv workspace, `[tool.mypy-engine]`,
  pytest marker `engine`, `configs/engine.yaml`.
- Library-grade scripts moved into the package: `zones`, `sim`
  (ex `sim_engine`), `maker` (ex `maker_entry`), `admission`,
  `okx_dataset` (ex `prepare_okx_dataset`).  Their demo pipelines
  (D.6/D.11/D.12) now run via `python -m engine.<mod>` behind
  `__main__` guards - importing the package is side-effect free.
- `scripts/` keeps experiment drivers only (wf_ab, nested_cv,
  matrix_2x2, ranking_baselines, adaptive_tp, execution_costs,
  robustness, portfolio, build_*_dataset), linted at F,E9 tier.
- CI fixed: the lint step had a malformed (nested) YAML list; pushes
  now trigger on `dev` too.  Lint/mypy retargeted to `engine/`.
- Numbers re-validated after the move: B pooled 6/8, admission
  REPLACE-low +466.0R / 2.44R DD, D.6 gated test pess +0.302, D.12
  maker lift -0.414 - all identical to the pre-refactor state.

## Implemented ✅ / core 🔨

| Module | Status | Tested/verified |
|--------|--------|-----------------|
| `ta/` indicator library | ✅ 84 indicators in DSL (TZ-03 wave 2) | 1975 tests |
| `dsl/` trading DSL | ✅ TZ-01 | 154 tests |
| `strategies/` strategy layer | ✅ TZ-02 | 25 tests |
| `backtest/` backtest | ✅ core; risk-gate ✅ TZ-04 | 34 + 12 integration |
| `risk/` risk engine | ✅ config-driven TZ-11 | 22 + 12 integration |
| `engine/` model | 🔨 core; trained on real data (OKX 7×4TF), best classifier of the baseline run — edge not yet achieved (gate not passed) | 71 tests + first backtest vs 7 baselines |
| `infer/` CLI | ✅ TZ-05 | 9 tests |
| `rag/` RAG | 🔨 core; pass@1 unmeasured | 47 tests |
| `main/` DI+bridge+REST+PG | 🔨 core; e2e on in-memory broker + SQLite | 12 REST + 10 db + e2e |
| `okx/` venue adapter (TZ-15) | ✅ core v1 + ✅ live public md (REST warm-up + WS business stream) | 39 tests (36 unit + 3 live smoke) |

**Status of the deterministic path:** complete end-to-end on **synthetic** data:
`ta → DSL → signals → Risk Engine → backtest with reject-audit`.

## Not implemented / remaining ⬜

1. **Live production backends never wired** — in-memory RabbitMQ / SQLite / mocked Ollama only;
   `docker compose up` with real RabbitMQ/PG/Qdrant/Ollama is untested.
2. **Local backtest runner in `main/`** — cmd.backtest returns "failed: no runner" stub.
3. **Model has no trading edge yet** — artifacts exist (`runs/okx7/best.pt`); the first
   real-data backtest vs 7 baselines (RF/LogReg/Ridge/MLP/LightGBM/XGBoost/random) showed
   the transformer is the best *classifier* (acc 0.719 / F1 0.710) but all models lose
   with costs; **baseline gate not passed** (keeps the live contour closed, TZ-00 §5).
   Improvement criteria + next attempts (incl. DSL indicator-config search):
   `legacy/dev_docs/ai_baseline_report.md`.
4. **pass@1 ≥ 70%** (RAG criterion) — implemented, not measured on a live LLM.
5. **OKX trading contour (TZ-15)** — public market data is live (REST + WS, verified
   against the real venue); private channels, order placement and algo SL/TP stay
   closed until the baseline gate; PG-backed `InstrumentMap` not wired.
6. Manual T-Invest run (TZ-05); aiogram bot, JWT, TLS/tokens, lag metrics (TZ-09/TZ-10).
7. **AI**: OB-encoder batching, <5 ms measurement, real-data training, SIV run.

## PLAN v2 — wide-geometry pivot (approved 2026-09-19) 🎯

Supersedes the old experiment queue. Rationale: see "Findings" below — the old
label profile (TP 2×ATR/SL 1.5×ATR) has negative expectancy net of costs on
every TF (proven by the oracle test), while the **decoupled wide geometry**
(1m OB entries, hour-scale TP/SL) shows in-sample positive expectancy.

**Named risk profiles** now live in `configs/engine.yaml`: `risk_profile: default`
reads the `risk:` block; `--risk-profile wide` (prepare/backtest/dsl_stage0)
reads `risk_wide:` (TP 108×ATR(1m) ≈ 5.9%, SL 27× ≈ 1.5%, hold 480×1m = 8h).

### Phase 1 — validate wide geometry out-of-sample. GATE 1 ⏳

```bash
# 1) build a compact wide-profile dataset for BTC from the shared raw cache
uv run python scripts/prepare_okx_dataset.py --stage worker \
  --bars 1m 15m 1H --base 1m --years 2.5 --assets BTC-USDT \
  --cache-dir data/okx21 --out data/okx21_wide --risk-profile wide
# add ETH/SOL the same way once the okx21 workers stop writing their caches,
# then merge:
uv run python scripts/prepare_okx_dataset.py --stage merge \
  --bars 1m 15m 1H --base 1m --years 2.5 --out data/okx21_wide
# 2) GATE 1: oracle backtest (labels as signals) on the last 15%
uv run python scripts/backtest.py --data data/okx21_wide \
  --model runs/okx7/best.pt --skip-transformer --oracle \
  --risk-profile wide --out runs/okx21_wide/backtest_oracle.json
```
Pass = oracle positive OOS on ≥2 assets → Phase 2. Fail = stage-0 geometry
grid (max ~10 configs), then honest "OB carries no alpha" verdict.

### Phase 2 — full dataset + training. GATE 2

When the okx21 workers finish → merge `data/okx21` (commands kept below),
rebuild the 1m layer as wide, then `train_okx.py --data data/okx21_wide`
(6L×192H, 10 epochs). Success metric: **entry-class WR OOS > breakeven** (not
accuracy). RAM contingency: drop the 1m base if OOM.

### Phase 3 — backtest matrix + threshold grid

`backtest.py --risk-profile wide` vs all baselines + oracle; `--threshold`
0.5…0.7 grid; report cost/TP per slice and per-class entry precision/recall.

### Phase 4 — DSL search (parallel)

`dsl_stage0.py --profile wide` grids (AVSL inversion, atr_period, risk
params), ranked by edge over breakeven; survivors verified with oracle OOS
before any training. Optional `dsl_stage1.py` LightGBM proxy.

### Phase 5 — only after Phases 1–4

MFE/MAE head (model places TP/SL), purged walk-forward CV, PnL-weighted
loss, maker-execution profile (0.02%/side), error analysis by regime.

### Reference: okx21 (default profile) pipeline, kept for comparison

```bash
# 1) merge staged assets -> final split files + meta.json
uv run python scripts/prepare_okx_dataset.py --stage merge \
  --bars 1m 5m 15m 30m 1H 4H 1D --base 1m 5m 15m 1H --years 2.5 --out data/okx21
# 2) train (6x192, 10 epochs)
uv run python scripts/train_okx.py --data data/okx21 --device cuda \
  --max-ob 64 --save runs/okx21/best.pt --log-dir runs/okx21/tb
# 3) backtest vs baselines (84 slices)
uv run python scripts/backtest.py --data data/okx21 --model runs/okx21/best.pt \
  --out runs/okx21/backtest.json
```

8. **TZ-12 final**: ±10% reruns, TA-Lib optional CI job.

## Remaining work order (from TZ-00 §3.2)

1. Local backtest-runner in `main/` + TZ-04 msgspec report contracts
2. TZ-07 pass@1 eval (live Ollama) + `rag_integration` marker (live Qdrant/Ollama)
3. TZ-10 finish: aiogram bot, JWT, live PG in CI
4. TZ-09 finish: live RabbitMQ, TLS/tokens, lag metrics
5. TZ-04/TZ-06 on real data: SIV run, training, baseline gate; OB batching, <5 ms —
   **first training+backtest done, gate not passed**; iterate per
   `legacy/dev_docs/ai_baseline_report.md` (thresholds, costs, horizon, DSL-config search)
6. TZ-12 final: ±10% reruns, TA-Lib CI job
7. TZ-15 finish: private WS channels + order placement (after baseline gate), algo SL/TP, PG `InstrumentMap`

## Quality gates

- Full suite: **2461 passed / 123 skipped / 0 warnings**; ruff + mypy clean
  (only accepted tech-debt: docstrings in `ta/src/overlap/mama.py`).
- **Baseline gate** (TZ-04 §4.6.1) is the project's main filter: nothing is valid without
  passing comparison vs Buy & Hold / logistic regression / RF/XGBoost.
- RAG success: **pass@1 ≥ 70%** (valid DSL ≤ 2 repair iterations).
## Findings 2026-09-19 — где на самом деле ломается edge 🔬

Decisive experiment: added `--oracle` to `scripts/backtest.py` — feeds ground-truth
labels into the simulator (perfect-model upper bound).

- **Oracle LOSES: −74.1% mean / −26.6% on 1H slices** (`runs/okx7/backtest_oracle.json`).
  ⇒ **No parity bug, no model-precision bottleneck: the label strategy itself
  (OB + TP 2×ATR / SL 1.5×ATR) has negative expectancy net of costs.**
- Cost arithmetic per TF (BTC, measured on real cache, round-trip = 0.30%):
  | TF | ATR | TP(2×ATR) | cost/TP | verdict |
  |----|-----|-----------|---------|---------|
  | 1m | 0.037% | 0.075% | **4.0×** | −100% guaranteed for ANY model |
  | 5m | 0.123% | 0.246% | **1.22×** | unwinnable (TP < costs) |
  | 15m| ~0.25% | ~0.5% | ~0.6× | marginal |
  | 1H | 0.621% | 1.242% | 0.24× | only winnable TF |
  The −89.8% vs −90.7% transformer-vs-random gap aggregates 28 slices of which
  half are mechanically unwinnable; all real signal lives on 1H/15m. Gate metrics
  should be computed on cost/TP < 1 TFs only.
- TP/SL geometry grid (stage-0, 1H, BTC/ETH/SOL): TP 3–4×ATR, SL 1.0–1.5×ATR
  (`runs/dsl/stage0_tpgrid.json`) — win rates land **at or below breakeven**
  (e.g. TP3/SL1.5 needs WR>0.405, actual 0.35–0.37). Only ETH TP4/SL1.0–1.5
  scrapes marginally above. ⇒ OB entry signal quality is the binding constraint,
  not TP/SL geometry, not the transformer.
- Note: stage-0 `avg_r` on binary outcomes equals win_rate (no R information);
  fixed `_label_stats` to exclude `outcome==2` rows.

Priority queue reshuffle:
1. **Entry-signal quality** is now the #1 target: stage-0 indicator grids
   (AVSL etc.) score label stats — look for configs with WR > breakeven, then
   verify with `--oracle` in backtest before training anything.
2. **Cost model**: 0.1%/side taker is conservative; maker/limit entries (~0.02%)
   would move breakeven WR from ~0.40 to ~0.35 at TP3/SL1.5 — decide the
   execution assumption explicitly in configs/engine.yaml `risk`.
3. Per-TF reporting: backtest report should include cost/TP per slice and
   per-class entry precision/recall (reviewer note — valid).
4. Purged walk-forward CV and PnL-weighted loss — still queued, but secondary
   to (1)–(2): no loss function fixes a negative-expectancy label.

### Wide-geometry experiment (2026-09-19, 1m BTC, 2.5y, hold <= 480x1m)

Decoupled entry TF from target size: OB entries on 1m, TP/SL at hour+ scale.
Breakeven WR = (SL + 0.3%) / (TP + SL); noise baseline = SL / (TP + SL).

| TP / SL | trades | WR | breakeven | noise | edge vs noise |
|---------|--------|------|-----------|-------|---------------|
| 0.74% / 0.37% | 12856 | 0.319 | 0.602 | 0.333 | -1.5 p.p. |
| 1.49% / 0.37% | 10295 | 0.266 | 0.362 | 0.200 | +6.6 p.p. |
| 2.20% / 0.55% | 8009 | 0.305 | 0.309 | 0.200 | +10.5 p.p. |
| **2.97% / 0.74%** | 6931 | **0.333** | **0.281** | 0.200 | **+13.3 p.p.** PASS |
| **5.94% / 1.49%** | 5663 | **0.372** | **0.240** | 0.200 | **+17.2 p.p.** PASS |

In-sample only; GATE 1 (oracle OOS) decides. Edge grows monotonically with
target size - the OB signal has slowly decaying predictive power that drowns
in 1m noise at short targets. Best configs are worth +0.3..0.7R per trade
net of costs.

### GATE 1 result (BTC, wide profile): FAIL - edge does not survive OOS :red_circle:

`runs/okx21_wide/backtest_oracle.json`: oracle (long labels as signals,
OOS last 15%) = **-74.2%**, 434 trades, WR 0.327, PF 0.464.

Root causes, in order of importance:
1. **Regime decay, not a bug**: OOS only 6/434 trades (1.4%) reach the +5.3%
   TP within 8h - the test window (May-Sep 2026) is flat/down; wide long
   targets need a trending regime. In-sample WR 0.372 (train 0.375 / val
   0.386 / test 0.327) was carried by TP hits in the 2024-25 trend plus
   near-zero hold-exits; label "WR > breakeven" is misleading when most
   trades resolve via max-hold (the breakeven formula assumed TP-sized wins).
2. **Simulator semantics artifact found & fixed**: mapping label action 2
   (short entry) to the sim's exit signal truncated ~75% of oracle trades;
   the oracle now maps long labels only. The label generator and stage-0
   never had this problem (each entry resolves via TP/SL/hold internally).
3. Consequences for the plan: (a) stage-0 must report mean R / EV per trade,
   not WR (hold-exit noise inflates WR); (b) Gate 1 verdict needs the other
   assets + short side + trend_filter variants; (c) walk-forward across
   regimes is now mandatory, not optional.

### Stage 0.5 — strategy search (rule templates, not hand-picked numbers) :white_check_mark:

`scripts/dsl_strategy_search.py` composes candidates from explicit rules -
entry (OB touch / +trend filter up-down) x stop (structural `zone:b` =
behind the block zone +/- b*ATR, or volatility `atr:m`) x target (`k`R of
risk) x hold - and scores each with `generate_labels_from_strategy` in
R-multiple mode: **mean realised R per trade net of costs (EV)**, split by
train/val/test. `--min-risk-atr` rejects entries whose stop is too close
for round-trip costs to be survivable (a cost floor expressed in ATRs).

Run `runs/dsl/strategy_search.json` (BTC-USDT 1m, 2.5y, hold 480,
min-risk-atr 15, 48 candidates / 36 with trades):

- **Every candidate is EV-negative in every split.** Best (short,
  atr:27, 2R): train -0.22 / val -0.22 / test -0.31 R per trade.
- EV ~ -0.22R == the 0.3% round-trip cost expressed in R of a 1.5%-risk
  stop. **Gross edge of the OB-touch entry family is ~zero, and it is
  stable** - the same in all regimes, which also retroactively explains
  the Gate-1 wide-geometry failure without invoking regime decay alone.
- Structural zone stops only work when the zone edge is >=15 ATR away;
  closer stops are pure cost bleed (earlier runs without the floor showed
  -2..-7R). The min-risk-atr floor is therefore a mandatory strategy
  rule, not a tunable nicety.
- Note: `use_structure_filter` is a no-op with base-TF
  `detect_order_blocks` (all blocks carry `structure_label`); it only
  becomes meaningful with HTF/DSL labels at stage 1+. Structure-variant
  rows were duplicates and were removed from the grid.

Verdict: no entry rule from this family is tradable net of 0.3% costs.
The remaining path is exactly the planned one - train the model to pick
the subset of OB entries where EV > +cost (Phase 2) - but now with
honest labels: best candidate (short, atr:27, 2R, hold 480) as the
labeling strategy, EV per trade as the ranking metric, and walk-forward
splits built in from the start.

### Stage 0.5b — indicator-anchored stops as fixed rules: worse :red_circle:

`--stops` now also accepts `anchor:<name>:<b>` rules (AVSL / AVSR /
HiLo activator / Supertrend / Bollinger bands, side-aware, computed
causally via the `ta` package). Result (`runs/dsl/strategy_search_anchors.json`,
56 candidates, BTC 1m 2.5y): every anchor family is *worse* than the
wide ATR stop - best anchor EV -0.75R (avsr) vs -0.22R (atr:27); st/hilo/bb
are -1.7..-4.7R. Anchors sit too close to price: cost-to-risk ratio kills
them. Fixed rules are the wrong tool for these levels.

### Stage 0.7 — stop-selection dataset for the model :white_check_mark:

`scripts/build_stop_dataset.py` builds `data/stop_dataset/BTCUSDT.parquet`:
every OB entry (reference strategy atr:27/2R, 6069 entries, both sides)
is evaluated under a *panel* of 11 stop rules x 2 targets with
generator-equivalent execution (next-open fill+slippage, SL-first,
hold exit, costs net). Features: per-entry distances to every anchor in
ATR units, ATR%, zone distance, OB structure/trend, side.

Key numbers (2R target, full period):
- per-rule EV: atr:27 -0.28, atr:54 -0.15, zone ~-0.19, anchors -0.76..-2.0;
- **oracle-of-choices (best rule per entry, hindsight): train +0.01 /
  val+test -0.02 EV** - the hard ceiling of per-entry stop selection.

Interpretation: a stop-selection model can realistically recover most of
the ~0.28R gap from reference to oracle (i.e. approach breakeven), but
**cannot produce positive EV on its own** - the binding constraint is the
entry signal (gross edge ~0), not the stop geometry. Therefore Phase 2
priorities: (1) entry-filtering model (which OB touches to take at all)
as the alpha source, (2) stop-selection model on top of it as a
cost-recovery layer, (3) cost reduction (maker entries) as the cheapest
+0.07..0.2R. Next: train both models on this table with chronological
splits, then Gate-2 the combo in the oracle.

## Plan v3 — MTF rebase (base TF 1h/4h, 6 candidate families)

Decision: move the base TF off 1m to 1h (primary) / 4h (variant) and
look both up (1w/1d/4h zones, trend, room-to-target) and down (15m/5m/1m
confirmation: sweeps, LTF OBs, impulse). Wide 1m geometry was an
indirect emulation of 1h stops; on 1h the cost-to-risk problem
(-0.2..0.3R) largely disappears. Entry selection stays the alpha source;
regime (trend dir/strength/vol) enters both the features and a Gate-2
requirement (EV>0 per traded regime class).

### Stage A.1 — MTF resampling :white_check_mark:

`ai/src/mtf.py`: deterministic 1m -> 5m/15m/30m/1h/4h/1d/1w via polars
`group_by_dynamic` (epoch-aligned windows). Bars are emitted only when
complete (trailing partial dropped); every row carries
`known_ts = ts + dur` and `asof_rows()` enforces causality for
consumers. Tests: `ai/tests/test_mtf_resample.py` (8 unit tests:
aggregation, incomplete tail, causality, gaps, invalid inputs).

### Stage A.2 — six entry-candidate families :white_check_mark:

`ai/src/candidates.py`: causal detectors on the base TF -
`ob_touch`, `ob_retest` (2nd zone touch), `sweep` (wick pierce
>= b*ATR + reclaim close), `fvg` (3-bar imbalance, entry on return),
`avsl_bounce` (AVSL/AVSR touch + turn bar), `break_retest` (zone break
then re-entry from the far side). `collect_candidates()` runs all six
and dedupes by (entry_idx, side) with priority sweep > ob_retest >
ob_touch > fvg > avsl_bounce > break_retest, flagging overlaps.
Tests: `ai/tests/test_candidates.py` (11 unit tests, synthetic
fixtures, causality + dedup priority).

Live smoke on real okx BTC-USDT 1m cache (379 days): 1h base ->
9093 bars, 415 OBs, **1988 candidates** (fvg 860, sweep 289, ob_retest
284, ob_touch 327, break_retest 228; overlap share 8.2%). 4h base ->
515 candidates. Volume estimate holds: ~2k/yr/asset on 1h, ~6k with
ETH+SOL - enough for the Plan-v3 model once HTF/LTF context features
and regime vectors (stage A.3) are added.

Next: A.3 `build_mtf_dataset.py` (MTF features + regime vector + stop/
TP panel per candidate + execution modes), A.4 purged walk-forward
splits, A.5 regime x family x stop-rule EV matrix.

### Stage A.3-A.5 — MTF dataset built :white_check_mark:

Cache bonus: the build walked OKX pagination to its history limit -
BTC 1m cache grew 545k -> 1.35M bars (~2.5y, back into 2023-24 cycles).

`scripts/build_mtf_dataset.py` + `ai/src/mtf_dataset.py` (pure helpers:
causal rolling percentile, purged splits with embargo, pessimistic
limit fill, nearest-zone distances, SMA trend state; 8 unit tests).
Dataset `data/mtf_dataset/BTCUSDT_1h.parquet`: **3576 candidates (all
6 families incl. avsl_bounce), 235,950 rows, 39 cols**; per candidate:
11 stop rules x 2 targets x 3 executions (market / limit:edge /
limit:mid with pessimistic buffer fill) x purged splits (train/val/
test, hold=48 embargo, 1650 rows in gaps).  Features: base context,
regime vector (SMA50 z/slope, causal rolling percentiles of ATR% and
BB width), HTF 4h/1d asof trend + zone distances in base ATRs, LTF 15m
asof impulse/volume.  Note: `_compute_anchors` AVSL/AVSR is all-NaN on
resampled frames (talib SMA poisons through warm-up NaNs) - script has
a numba `nan_policy='ffill'` rebuild (`_anchors_nan_safe`).

A.5 headline (EV pivot, market, 2R, net):
- rule `atr:14`: all families -0.15..+0.08 everywhere - dead;
- rule `zone:1.0` (stop behind zone): train **+0.17..+0.26**, val
  **+0.25..+0.38**, test **-0.07..+0.02** - every family positive in
  train+val, then regime decay in the 2026 test window (GATE-1
  artifact again, now visible in every family).

Interpretation: zone-stop geometry on 1h has real positive EV outside
the adverse regime - costs no longer bind.  The model's job is exactly
the plan's premise: regime conditioning (which regime trades which
family) + entry filtering + limit execution layer (fill rates 33-74%
by family at zone edge).  Next: B (model towers) + Gate 2 per regime.

### Stage B — model towers, first Gate-2 numbers :white_check_mark:

`ai/src/mtf_model.py` (pure helpers: reference/stop row selectors,
LightGBM feature assembly with native categoricals + NaN pass-through,
EV-threshold calibration, per-regime Gate-2 table, stop-policy EV;
7 unit tests) + `scripts/train_mtf_model.py` (LightGBM towers).
Outputs: `data/mtf_model/{entry,stop,tp}_head.txt` + `report.json`.

Gotchas found: polars NaN comparisons pass `> 1.0` filters and NaN
mean() never wins `>` - invalid rule rows (anchor on the wrong side,
zone stops on zoneless avsl_bounce candidates) must be dropped with
`is_not_nan()` before any EV math.  tp head (E[r_net] regression) is
dead: spearman ~0 on val/test - dropped as signal source.

Results (BTC 1h, purged splits, net EV per trade, market, 2R):

| config | train | val | test |
|---|---|---|---|
| fixed zone:1.0 (no model) | +0.21 (2060) | +0.30 (704) | **-0.02** (679) |
| stop-head policy (argmax rule) | +0.44 (1883) | +0.38 (648) | **+0.25** (640) |
| + entry filter (thr 0.28 on val) | +0.46 (1197) | +0.38 (475) | **+0.25** (469) |

Entry head alone: improves test from -0.02 to -0.00 and shows the
regime split (test: up +0.06 / down -0.06 / range -0.05), but does not
rescue the adverse window.  The stop head carries the signal: choosing
the stop rule per candidate turns the 2026 test window positive -
val and test agree (+0.38 / +0.25), n=640, per-trade SE ~0.055R so the
effect is ~4.5 sigma before multiple-selection caution (argmax over 11
rules per candidate inflates; the honest number needs nested CV or a
tradeable re-fit, see next stage).

Interpretation: stop-rule geometry is the alpha carrier - "where is
the structural invalidation" is predictable per candidate, and the
entry filter's job is capacity/quality (same EV, -27% trades), not
direction.  Next: tighten honestly (nested/refit policy, per-regime
rule tables), limit-execution layer on the policy subset, then Gate 2
writeup vs the +0.02R baseline bar.

### Stage B.2 — hardening: the alpha survives honest tests :white_check_mark:

Two data/eval bugs found and fixed first:
1. **limit risk collapse**: with a limit fill near an anchor stop,
   `risk_unit = |fill - sl|` degenerates and R-multiples explode
   (values like -17R).  Fix: rows with `risk_unit < 0.5*ATR` are
   marked invalid (`r_net = NaN`) at build time; dataset rebuilt.
2. **candidate key**: long and short candidates share `entry_idx` -
   all per-candidate policies now key on `(entry_idx, side)`.

Hardening results (BTC 1h, market, 2R, net EV):

| policy | train | val | test |
|---|---|---|---|
| fixed zone:1.0 | +0.20 | +0.30 | -0.02 |
| stop-head policy (LGBM) | +0.41 (2114) | +0.37 (717) | **+0.21** (716) |
| + entry filter | +0.60 (1368) | +0.42 (534) | **+0.24** (547) |
| no-ML rule table (regime x side -> rule) | +0.36 | +0.36 | **+0.23** (670) |
| random rule | -0.01 | +0.01 | -0.09 |
| oracle ceiling | +0.93 | +0.98 | +0.85 |

Paired bootstrap policy-vs-fixed on test: diff **+0.234R**, CI
[0.175, 0.292], p(diff<=0) ~ 0 (train +0.21 CI [0.18,0.23]; val +0.08
CI [0.03,0.12], p=0.002).  The effect is not an artifact of one split.

**The headline artifact is embarrassingly simple**: a lookup table
`regime_dir x side -> stop rule` fit on train-only counts (best-EV
rule with a 30-trade floor, zone fallback) matches the LGBM policy on
test (+0.23 vs +0.21) with zero ML.  The LGBM/entry-filter stack adds
mostly capacity control (-27% trades at equal/higher EV).  The rule
table chose e.g. `down|long -> anchor:st`, `up|long -> zone:0.5`,
`range|long -> zone:0.5`.

Limit execution on policy picks (test): limit:edge fill 53% /
EV|filled +0.29 / EV per signal +0.15; limit:mid fill 71% / +0.24 /
+0.17; market +0.21 per signal.  Costs do not bind - market execution
is fine; limits buy entry quality, not EV.

Gate-2 assessment vs the +0.02R bar: **PASSED with the simple rule
table + entry filter stack** (test +0.24R/trade over ~550 trades in
the adverse window, all baselines beaten, CI clear of zero).  Caveats:
single asset (BTC), single base TF (1h), regime labels from the same
causal features (no lookahead by construction), argmax-selection
inflation bounded by the table-vs-LGBM agreement.  Next: multi-asset
replication (ETH etc.), 4h base TF, then portfolio layer.

### Stage B.2.1 — reversal-safety + B.3 ML upgrades :white_check_mark:

**Reversal protection**: long/short candidates sharing a bar were
merged by every per-candidate policy (grouped on `entry_idx` alone) -
fixed in B.2 ad hoc, now institutionalised: `candidate_key(df)` in
`ai/src/mtf_model.py` is the single key builder, used everywhere in
`train_mtf_model.py`; regression tests pin long+short same-bar
separation and paired-bootstrap alignment when one side's rule set is
NaN.  Requirement recorded for the future execution layer (stage D):
explicit transition tests long->flat->short, single-signal reversal,
same-bar SL + reverse.

**Risk metrics** added: `trade_curve_stats` (t-stat, max DD in R,
profit factor) - 4 tests.  New `ml_upgrade` report section (calibrated
on val only, evaluated on test):

| variant | val EV / t / DD | test EV / t / DD | test PF |
|---|---|---|---|
| policy (baseline) | +0.37 / 15.7 / 6.2R | +0.21 / 7.3 / 15.1R | 1.95 |
| consensus gate | +0.50 / 20.4 / 3.4R | +0.46 / 14.1 / 8.0R | 5.44 |
| **consensus + sized** | **+0.55 / 21.5 / 2.6R** | **+0.51 / 15.3 / 5.3R** | **6.51** |
| sized policy (train-tertiles) | +0.43 / 18.2 / 3.6R | +0.28 / 9.7 / 9.5R | 2.46 |
| table fallback on disagreement | +0.35 / 12.4 / 17.9R | +0.21 / 7.2 / 24.0R | 2.00 |

Answer to "can ML improve": **yes** - not by replacing the table but
by (a) trading only the LGBM/table consensus (test EV x2.2 at half the
trades, DD halved, PF 5.4), and (b) confidence-based sizing (train
probability tertiles -> 0.5/0.75/1.0 trade fractions; val-selected,
test-transferred).  The two effects STACK: consensus+sized reaches
test +0.51R (2.4x policy, DD /2.8, PF 6.5).  Fallback-to-table on
disagreement does NOT help (skipping is better than hedging).  Both
val and test agree on the variant ranking: consensus+sized >
consensus > sized > policy > fallback.

Remaining research (not started): pairwise ranking objective for the
stop head (full-panel supervision), joint (rule x target) action
space.  Next: stage C - multi-asset replication (ETH + 4h base).

### Stage C (in progress) — replication :construction:

**BTC 4h base TF** (868 candidates vs 3576 on 1h; test n=174):
policy EV +0.444 vs random +0.05, table +0.11, oracle +0.84 - level
is higher (bigger R multiples per bar), but the paired policy-vs-zone
edge on test is marginal: +0.052, CI [-0.012, +0.118], p=0.059 (val
was clear: +0.167, CI [0.095, 0.247]).  Reading: at 4h the zone rule
already captures most of the value and few candidates leave little
room for pick-selection to show incremental edge - the 1h consensus
gate story does NOT yet replicate at 4h with this sample size.
Consensus gate on 4h: val-selected, test 0.466 vs policy 0.444 (n=63,
DD 0.3R - too few trades to celebrate).  Rule table itself differs
from 1h's (geometry interacts with TF) - argues for per-TF tables.

### Stage C — replication :white_check_mark:

**ETH-USDT 1h** (3384 candidates, 223k rows; test n=725): replicates
BTC 1h, stronger on every metric:

| metric (test) | BTC 1h | ETH 1h |
|---|---|---|
| policy EV | +0.211 | +0.362 |
| policy-vs-zone paired diff (CI) | +0.234 [0.175, 0.292] | **+0.300 [0.259, 0.345]**, p=0 |
| rule table EV | +0.230 | +0.283 |
| random / oracle | -0.09 / +0.85 | -0.07 / +0.86 |
| consensus EV (n) | +0.462 (319) | +0.469 (388) |
| consensus+sized EV | +0.508 | **+0.538** |

Three replication findings:

1. **The no-ML rule table is asset-invariant at 1h**: ETH's fitted
   table matches BTC's cell-for-cell (up|long=zone:0.5, range|long=
   anchor:st:0.5, down|long=anchor:st:0.5, up|short=anchor:st:0.5,
   down|short=zone:0.5, range|short=zone:1.0, unknown|=zone:1.0).
   The alpha carrier is stop-rule geometry, not asset-specific.
   (The 4h table DIFFERS from 1h - geometry is TF-specific, so per-TF
   tables are required, per-asset ones are not.)
2. **Val->test transfer of the variant ranking holds on both assets**:
   consensus+sized > consensus > policy everywhere, always
   val-selected and test-confirmed.
3. **The consensus gate is not BTC-specific**: it improves EV on ETH
   too (+0.538 vs +0.362 policy, DD comparable, ~half the trades).

**BTC 4h** (868 candidates; test n=174): policy EV +0.444 vs random
+0.05, table +0.11, oracle +0.84 - level is higher (bigger R per
bar), but the paired policy-vs-zone edge on test is marginal: +0.052,
CI [-0.012, +0.118], p=0.059 (val was clear: +0.167, [0.095, 0.247]).
Reading: at 4h the zone rule already captures most of the value and
few candidates leave little room for pick-selection; the consensus
gate direction is consistent (test 0.466 vs 0.444) but n=63 is too
small to call.  4h stays a secondary TF.

Stage C verdict: **strategy generalizes across assets at 1h**.  The
core artifact is per-TF: rule table (8 cells) + consensus gate +
confidence sizing, all calibratable on train/val alone.  Remaining:
pairwise ranking stop head, (rule x target) action space, portfolio
layer with the long->flat->short state machine tests (stage D).

### Stage D.2 — EntryExitTransformer A/B :x: (rejected, cheaply)

Question: does the repo's existing EntryExitTransformer (dual encoder
time-series + order blocks, ai/src/transformer.py) add signal as a
third voice in the consensus gate?  Protocol: retrain it on MTF rules
(not its legacy per-bar action labels) - windows of 64 1h bars ending
at each candidate's decision bar, normalised OHLCV+ATR+side channels,
target = "best stop rule wins" (best market r_net > 0), same purged
splits; probability p_trf then gates the consensus subset with a
val-calibrated threshold; two-sample bootstrap of gated-vs-dropped EV.

Files: scripts/build_transformer_dataset.py,
scripts/train_entryexit_mtf.py (small config: 2 layers, hidden 64 -
only ~2.1k train windows), scripts/eval_trf_ab.py.

Results (BTC 1h): model quality - train AUC 0.60, val AUC 0.40 (below
coin flip), test AUC 0.57.  Gate effect - val: gated EV +0.498 vs
dropped +0.495, diff +0.004, CI [-0.10, +0.11] (no separation; val
grid flat over all thresholds).  Test: gated +0.577 (n=161, DD 2.2R)
vs dropped +0.345, diff +0.232, CI [0.11, 0.36] - looks great, but
**val did not predict it**, so by our own protocol (val decides,
test confirms) this is period-specific noise, not a validated edge.
Taking it would be selection on test.

Verdict: **transformer voice rejected**.  Confirms the earlier read:
at ~3.5k candidates the flat MTF features already carry the context,
and a sequence encoder has nothing reliable to add.  The experiment
cost ~1 hour and the infrastructure (window builder aligned to MTF
candidates) is reusable for the ranking stop head.  Kept for the
record; not wired into the production stack.

### Findings synthesis — where the alpha actually lives

Correction of an earlier simplification ("LGBM predicts stops and
takes"): **only the stop head predicts anything.**  The tp head is
dead (spearman ~0); the entry head barely moves test EV (-0.0215 ->
-0.0103, n 677 -> 513 - it is capacity control, not alpha).  The
legacy OKX result (transformer best classifier, acc 0.719 vs 0.703)
was won on a mechanically untradeable dataset (cost/TP ~ 4x on 1m) -
a classification win worth nothing.

| layer | alpha carrier | role |
|---|---|---|
| candidate search | rule-based (OB, sweep, FVG, AVSL...) | finds entries |
| **stop choice** | **LGBM stop head + rule table** | the alpha: -0.02 -> +0.21 test |
| entry filter | LGBM entry head | capacity control (-0.02 -> -0.01) |
| position size | consensus gate + confidence sizing | +0.21 -> +0.51 test |
| take-profits | nobody | tp head dead; TP fixed at 2R |
| transformer | nobody | rejected (val AUC 0.40) |

The alpha is in the **problem formulation** - predicting stop-rule
geometry per candidate, not entry or take-profit timing.  The
transformer lost not because "transformers are worse" but because on
3.5k examples with the same tabular features a sequence encoder has
nothing to learn, while trees extract the signal.  Its realistic path
back: the ranking task (11 rules x 3560 candidates ~ 39k pairs) or
10-30x more data.

#### D.2 roadmap — four legitimate uses of the rejected artifact

Not "replace LGBM" but "do something else".  Return only with a new
hypothesis; "try a smaller learning rate" is not a hypothesis.

1. **Ranking head** (HIGH; after nested CV, state machine,
   walk-forward): predict the best stop rule out of 11 per candidate
   - 3560 x 11 ~ 39k pairwise pairs vs 3.5k classification examples;
   comparative objective (RankNet/LambdaRank), tabular features.
   Success criterion: beats LGBM stop head on test.  Win ->
   rehabilitated as an extra voice; lose -> topic closed for good.
2. **Attention diagnostics** (MEDIUM; anytime, cheap): inspect what
   the trained encoder attends to before the decision bar.  A
   concentrated pattern (e.g. last 3-5 bars) -> hypothesis features
   for LGBM; flat attention -> no temporal structure, trees right.
   Success: a new feature that improves LGBM val EV.
3. **Warm-start** (LOW): encoder weights as init for future tasks on
   the same OHLCV windows (volatility, MFE/MAE, regime).
4. **Reference implementation / README** (LOW): an honest
   build->train->A/B->reject example on numeric data.

Forbidden: returning it to prod as-is, hyperparameter fishing, using
it as a "second opinion" in the consensus gate (tested in D.2),
presenting it as an achievement.

### Stage D.1 — pure state machine :white_check_mark:

Spec (ai/src/state_machine.py, documented in module docstring):
signal at bar d fills at d+1; one slot; while in position ALL new
signals skipped (reverse ignored by default); same-bar exit+signal
skipped (SL-first pessimism); cooldown blocks N bars after exit;
same-bar signals resolved by stop-head priority; exit_idx now stored
per dataset row (builder patched, candidate counts unchanged byte-
for-byte: BTC 3576/235950, ETH 3384/223344).

Tests: 7 transition tests (SL close, reverse ignored / allowed,
same-bar SL+reverse, cooldown, priority, isolated-equivalence).

Replay on BTC 1h consensus picks (cooldown=0, reverse off):

| split | isolated | machine | EV gap | DD |
|---|---|---|---|---|
| val | +0.496 (n=385) | +0.542 (n=154) | **+9.3%** | 3.4 -> 3.0R |
| test | +0.462 (n=319) | +0.454 (n=149) | **-1.8%** | 8.0 -> 5.7R |

Reading: the isolation illusion costs only ~2% EV on test (and helps
on val), because consensus picks are sparse (~half the trades get
skipped for occupancy but the machine's priority-by-confidence
filters replace them with nothing bad).  DD improves in both splits.
The feared 20-40% EV loss does NOT materialise at 1h consensus
frequency.  Next: D.3 execution semantics (pessimistic fill), then
D.2 portfolio layer (BTC+ETH, correlation limits, kill-switch).

### Stage D.3 — execution semantics :warning: (diagnosed: pessimistic criterion failed, root cause identified)

Pre-D.3 checks: skipped trades have LOWER stop-head confidence than
taken on all splits (p 0.830/0.779 train, 0.831/0.763 val, 0.809/0.807
test) - occupancy is a quality filter, not random loss; train replay
gap +3.0% (not +10%) => the val +9.3% is small-n noise, honest gap
~0 +/- 0.05R; priority is calibrated on train, no circularity.

D.3 dataset: builder now stores per-trade execution details (fill/sl/
tp prices, risk_unit, atr, exit_reason/price).  Pessimistic cost model
on state-machine trades: entry slip x2, SL exit slip x2 (SL is a
market order), gap-through-stop buffer 0.25xATR (base) / 0.5xATR
(stress); TP stays a free limit fill.

| split | optimistic | pess_base | pess_stress |
|---|---|---|---|
| val | +0.542 | +0.279 (ratio 0.51) | +0.153 (0.28) |
| test | +0.454 | **+0.150 (ratio 0.33)** | +0.016 (0.03) |

**Criterion EV_pess/EV_opt >= 0.75 FAILED** (0.33 base).  Root cause:
tight stops.  Consensus picks run risk_unit ~0.4-0.5% of price, so
every fixed % of price is ~0.25R; the generator ALREADY charges
~0.5-0.6R of costs per trade (0.25% of price), and doubling slippage
adds another ~0.25-0.3R.  The strategy is not execution-fragile
because of bad fills - it is fragile because its edge (~1R gross) is
only ~2x its cost base.

Consequences and levers (in order):
1. realistic live is likely BETWEEN optimistic and pess_base (0.05%
   entry slip on a 0.01%-spread perp is already conservative; gaps of
   0.25 ATR/hit are rare) -> live-EV estimate ~ +0.15..+0.45R/trade;
2. the structural fix is WIDER stops: cost in R scales as
   price_cost/risk_unit - ranking head should be cost-aware (prefer
   zone:1.0/atr stops over zone:0.5 when EV-net is close);
3. maker entries (limit:edge) cut the entry cost but fill ~50-70% -
   revisit only after D.2;
4. D.2 portfolio decisions must use pess_base numbers as planning
   baseline: test +0.150R/trade is the defended number, not +0.454.

### Stage D.6 - joint (stop rule x TP target) ranking :x: REJECTED

Ranked all (rule, target) pairs - targets 2R/3R in the panel - by
pess R (same protocol as D.4).  joint+gate: test pess +0.302
(D.5 baseline +0.490), ungated +0.078; val/test divergence too.
Conclusion: TP must come from the MFE path model (D.5), not from the
ranking objective - terminal R is too noisy a label for target
choice and the ranker overfits it.  Priority-4 reserve is NOT in
joint ranking; D.4 ranker (stops) + D.5 adaptive TP (MFE) remains
the stack.  Planning number unchanged: test pess +0.490R.

D.6b retry (label/objective/regularization): strong-reg LambdaRank
+0.319, regression +0.119 - both below D.5 baseline; r_reach label
(min(mfe,target)) degenerate without per-group normalization (n=1).
Joint ranking rejected on 3 configurations; remaining lever would be
group-normalized reach labels, low expected value - parked.

### Stage D.5 - MFE/MAE head, adaptive TP, regime rule (done, mixed)

Builder now stores TP-free path stats per row (mfe/mae in ATR and R,
before SL hit; _excursions in build_stop_dataset).  LGBM regressor
predicts MFE (R) from entry-time features only (val RMSE 1.18R).
TP scenarios re-simulated on raw 1m->1h bars (resample_ohlcv; sanity
vs stored r_net: mean |diff| = 0.009R), ranker+gate picks, D.3-style
pessimistic costs (no gap term here - comparisons are internal):

| TP rule | val pess | test pess | test n | test DD |
|---|---|---|---|---|
| fixed 2R (baseline) | +0.677 | +0.579 | 106 | 2.9R |
| regime 3R/1R | +0.676 | +0.571 | 108 | 2.9R |
| adaptive k=0.8, RR 1/3..1 | +0.644 | +0.588 | 114 | 1.4R |
| adaptive scalp RR 1/5..1/3 | +0.623 | +0.542 | 116 | 1.4R |

UPDATE (gap term unified with D.3/D.4 + bootstrap CI): fixed 2R test
pess +0.474 CI[+0.390,+0.547] ratio 0.68; adaptive k=0.8 RR 1/3..1
+0.490 CI[+0.427,+0.540] DD 1.4R vs 3.4R; diff CI [-0.113,+0.082] ->
EV statistically indistinguishable, DD win stands.  Unified planning
number (ranker+gate, gap incl., adaptive TP): test pess +0.490R.
Verdicts: (1) regime-conditioned TP REJECTED (noise-level change);
(2) adaptive TP holds EV while cutting DD ~2x and adding trades -
the RR 1/3..1 config is the best risk-adjusted choice; user-spec
scalp RR 1/5..1/3 trades most with -6% EV, useful for frequency.
(3) MFE is predictable enough to TIME exits, not to add EV - same
pattern as the stop head.  Pending: fair transformer fight (same tabular features and cost/rank
protocol - the original comparison was handicapped); n=106-116 means
only DD differences are interpretable, EV diffs need CI (done above).
Next priorities: fair transformer fight -> cost-aware ranking for
stops (adaptive TP is already the cost-aware exit layer) -> D.2.

### Stage D.4 — cost-aware ranking head :white_check_mark: (criterion PASSED)

LambdaRank LGBM (300 trees, groups = candidates) over the 11-rule
panel (32787 rows); label = pess_base R from D.3 (planning metric by
construction); features = stop-head set + risk_pct + cost_R.
Replay (state machine, BTC 1h):

| head (gate) | val pess | test pess | test ratio | test n | test DD |
|---|---|---|---|---|---|
| stop-head + table (D.3) | +0.279 | +0.150 | 0.33 | 149 | 12.6R |
| ranker, no gate | +0.258 | +0.227 | 0.66 | 86 | 2.3R |
| **ranker + table gate** | **+0.275** | **+0.332** | **0.68** | 80 | **1.1R** |

Criterion (test pess > +0.25R, ratio > 0.5): PASSED (+0.332, 0.68).
Planning number up **+122%** vs D.3 baseline (+0.150 -> +0.332), DD
12.6R -> 1.1R, trades -46% (0.6 -> 0.3/week on BTC alone -> D.2
portfolio layer is now mandatory for frequency, not optional).
Caveats: single asset, single seed, no nested CV yet - treat as
hypothesis confirmed on val+test, not as final. Script:
scripts/d4_ranking.py.

D.3 -> D.4 dependency confirmed: ranking the SAME rules by pess R
flips the pick toward wider stops and repairs the pessimistic ratio.

**D.3 -> ranking dependency:** tight stops (risk_unit ~0.4-0.5%) burn
~0.3R/trade in costs.  Structural fix - cost-aware ranking:
cost_in_R = price_cost / risk_unit(i, j); prefer wider stops at
close EV-net.  This is a NEW hypothesis with a measurable criterion
(test pess_base EV > +0.25R, ratio > 0.5), not hyperparameter
fishing.  Ranking runs BEFORE / in parallel with D.2: it determines
whether the portfolio layer is worth building at all.  Planning
number to present: +0.150R (pess_base), never +0.454 (optimistic).
Realistic live target after ranking + D.2 + nested CV + walk-forward:
+0.10..0.20R/trade.


**Attention diagnostic run** (scripts/attention_diagnostics.py, val+
test windows, layer-0 self-attention, heads averaged, query = decision
bar): entropy 5.98 vs 6.00 max bits - attention is essentially
UNIFORM.  Top offsets are the oldest bars (-49..-60, a positional
artifact), mass on the last 5 bars is 0.062 vs 0.078 uniform
expectation.  No concentration near the decision bar => no learnable
local temporal structure for features.  Two readings, both
conclusion-preserving: (a) the window carries nothing the flat
features don't; (b) a model that failed to learn (val AUC 0.40) can't
show structure either way.  Item 2 result: no new LGBM features
mined; the sequence-vs-table question is settled for this data size.















### Repo restructure (2026-09-19)

After D.12 the repo was rebuilt around the live research pipeline:
- **Archived to `legacy/`** (documented in `legacy/MANIFEST.md`, nothing deleted):
  the former monorepo packages (dsl, strategies, infer, rag, risk, backtest,
  main, tinvest, contracts, migrations, docker/alembic infra), 13 legacy/
  superseded scripts (train_*, eval_*, dsl_*, d6b, d7, replay, run_pipeline,
  attention_diagnostics, build_transformer_dataset), 8 dead ai modules
  (bundle, contracts, dataset, device, losses, metrics, quickstart, training)
  and their test files.
- **Flattened**: `ai/src/*` -> `ai/*` (one layer less); `marketdata/` folded
  into `ai/marketdata/`; okx fetch revived as `ai/marketdata/okx_fetch.py`
  (it is on the live data path).
- **Renamed scripts** (d-prefixes dropped, artifacts keep historical names):
  d3->execution_costs, d4->ranking_baselines, d5->adaptive_tp,
  d6->sim_engine, d8->matrix_2x2, d8b->wf_ab, d9->portfolio, d9b->robustness,
  d10->nested_cv, d11->admission, d12->maker_entry. Stop-rule engine
  extracted from the archived dsl_strategy_search into `scripts/zones.py`.
- **Root now**: ai/ scripts/ tests/ ta/ dsl/ (minimal subset for ta)
  legacy/ data/ runs/ dev_docs/ + meta files. 15 dirs -> 9.
- **Config**: uv workspace members [ai, ta]; pytest testpaths=[tests];
  mypy strict on ai; CI lint = strict (ai, tests, dsl) + F-class (scripts).
- **Tests**: live suite pruned to 93 kept + 27 new unit tests for the core
  (sim_engine cost model, maker_entry fee/geometry, zones stop rules) =
  118 passed / 2 skipped. Full smoke after restructure: wf_ab.py
  reproduces A +0.401 / B +0.450 / 2891 signals exactly.
- Found and fixed along the way: missing numpy.typing import in
  ai/candidates.py (F821), orphan dead code after return in
  ai/candidates.py, missing niquests dep declaration (ai/pyproject).

### Repo restructure v2 (2026-09-19, same day)

Post-restructure audit pass:
- **`configs/ai.yaml` restored** — it had been dropped during v1 (the
  configs/ dir was inspected for *.py only). It is required by
  `load_config(risk_profile=...)` in build_mtf_dataset / build_stop_dataset /
  prepare_okx_dataset; without it the builders crash. Back in place from
  git history, verified `load_config(risk_profile='wide')` works.
- **Transformer fully archived**: `ai/transformer.py` ->
  `legacy/ai/transformer.py` (matrix_2x2 has its own inline TRF, so the
  module had zero live importers); tests/test_transformer.py and the two
  transformer-reference tests in test_ob_pipeline.py ->
  `legacy/tests_ai/`; `ai/docs/` (old transformer-system docs) ->
  `legacy/ai_docs/`; transformer-only conftest fixtures
  (sample_batch / model_params / sample_action_outcome_labels /
  sample_parquet_files) removed; tensorboard + torch-directml/onnx extras
  dropped from ai deps (torch stays: matrix_2x2 uses it).
- **Dead locals removed**: unused `sign` in the pess-helpers of
  sim_engine / ranking_baselines / adaptive_tp / execution_costs;
  unused `seq_len`/`cache`/`cfg` in prepare_okx_dataset's split-stage;
  stale T-Invest mentions dropped from prepare_okx_dataset docstrings.
- **`dsl/` restored in full**: v1 had replaced the original dte-dsl
  package with a hand-made 5-file subset; the full package (engine,
  providers, docs, own suite of 26 tests) is live again at `dsl/`,
  workspace member, tests in the default run and CI. Ghost `pandas`
  dependency declared explicitly (root + ai pyprojects).
- **Validation**: 266 passed / 6 skipped (112 research + 154 dsl,
  6 transformer tests left with the module), mypy strict clean,
  ruff clean incl. F/E9 on scripts;
  smokes byte-identical: wf_ab A +0.401 / B +0.450 / 2891 signals,
  REPLACE-low +466.0R / 2.44R, maker lift -0.414.

### NEXT

1. **Data expansion** (more assets incl. low-liquidity alts, longer history
   per asset, 15m bars; LGBM only): the data path
   (prepare_okx_dataset -> build_mtf_dataset/build_stop_dataset) is the
   thing to scale; watch the candidate yield on illiquid names.
2. **Live execution layer**: OKX adapter implementing the REPLACE
   admission rule (D.11) + state machine, market entries; paper trading
   first. The archived `legacy/packages/okx/` design (ws/executor/signing,
   tested) is the starting point.

### Stage D.7 - FAIR transformer fight :x: (fourth rejection, now fair)

All four equalizers applied (scripts/d7_trf_fair.py): same 33+3
features broadcast over a 64-bar window (raw OHLCV channels kept),
same pess-R label, RankNet over candidate groups (LambdaRank
protocol), same gate + unified d6 simulator, fixed TP for both heads.  Arch:
2 encoder layers, 4 attention heads per layer, d_model 64, FFN 256,
dropout 0.1, mean+last pooling, ~110k params.
Training protocol (upgraded after review): warm-up 2 + cosine decay,
weight decay 1e-4, EARLY STOPPING patience 5 on val ranknet loss,
best-checkpoint restore, max 50 epochs.  Curve (runs/d7/loss_curve.json):
best val 0.6791 at epoch 4, stop at 9; train loss kept declining
(52.2 -> 50.1) while val oscillated up -> mild overfit after epoch 4.
The earlier fixed 8-epoch run was slightly past optimum, same regime.
Results at best checkpoint: val pairwise AUROC 0.558 (crit > 0.55:
nominally passed, still chance+eps; was 0.40 handicapped - fairing
lifted discrimination, ceiling did not move).  Replay: TRF test pess
-0.134R (n=28, ratio 3.11) vs LGBM +0.349 (n=80, ratio 0.70);
bootstrap LGBM-TRF diff CI [+0.234, +0.786] - excludes zero, LGBM
decisively better.  Alive requires ALL criteria; EV fails hard.  Attention-entropy diagnostic
technically broken (SDPA backend returns no weights -> NaN) - moot:
the EV criterion already failed hard.  Pre-registered 70/30 forecast
confirmed: 4th structural rejection, now with a full training curve.
Sequence context adds nothing on top of tabular features at this data
scale.  PRE-REGISTERED (not run): scale-up to 4 layers / 128 dim /
8 heads at n=3574 candidates will yield EV <= 0 (440k params on 3574
examples = 8 examples/param -> overfit); revisit only at 30k+
candidates (ETH+SOL, 15m base).  Transformer roadmap stays parked.

### Stage D.8 — 2x2: per-asset vs multi-asset x LGBM vs TRF :white_check_mark: (causal decomposition)

Motivated by the confound in "multi-asset": model and data volume change
together unless isolated.  Matrix (scripts/d8_2x2.py, runs/d8.log):
A = per-asset LGBM, B = multi-asset LGBM (+asset_id), C = per-asset
FairTrf (d7 recipe), D = multi-asset FairTrf (asset code in tab vec).
Data: BTC 3,574 + ETH 3,384 + SOL 3,663 = 10,621 candidates (97,492
rows; ETH rebuilt to current schema, SOL built fresh).  Same pess-R
label, per-asset gate, unified sim, state machine.

| cell | BTC | ETH | SOL | POOLED |
|------|-----|-----|-----|--------|
| A | +0.254 | +0.211 | +0.398 | +0.296 (n=226, dd 2.9R) |
| B | +0.298 | +0.406 | +0.518 | +0.411 (n=248, dd 3.0R) |
| C | -0.151 | +0.315 | -0.603 (n=2) | +0.072 (n=46, dd 5.7R) |
| D | -0.052 | +0.121 | +0.333 (n=5) | +0.067 (n=73, dd 6.7R) |

Isolation (bootstrap 1000, pooled): **D-B = [-0.507, -0.188]** (model
effect strongly against TRF); **D-C = [-0.248, +0.237]** (data effect =
ZERO: x3.5 data moved TRF not at all, while the same data lifted LGBM
+0.296 -> +0.411).  Causal decomposition: the bottleneck is the model's
inductive bias on tabular geometry features, not data volume.  Verdict:
transformers rejected for THIS task/features/n; revival paths are new
feature classes (order flow, microstructure) or task-specific
architectures (attention between events, not bars) - both research, not
scale-up.  Scale-up stays dead even at 30k+ with the same features
(D-C=0 already showed this at 10k).  Pre-registration formally stands,
expectations lowered accordingly.

Practical yield: **cell B** - multi-asset LGBM beats per-asset on every
asset (BTC +0.254->+0.298, ETH +0.211->+0.406, SOL +0.398->+0.518):
pooling gives trees cross-asset statistics on stop GEOMETRY (universal),
not direction (asset-specific) - consistent with "trading geometry, not
direction".  Caveat: B-A measured on one split; trade-level bootstrap
understates regime variance -> B is a baseline CANDIDATE until
walk-forward confirmation (D.8b).

### Stage D.8b — walk-forward A vs B :white_check_mark: (upgrade confirmed, 6/8)

Pre-registered decision rule: B>A pooled in 6+/8 folds -> accept, 4-5
ambiguous, <=3 -> artifact.  Design (scripts/d8b_wf_ab.py,
runs/d8b/wf_folds.json): 8 folds x 56 days over Mar 2025 - Sep 2026,
expanding train, 7-day embargo, gate refit per fold on fold-train,
state machine slots reset at fold boundaries (path-dependence
approximation).

| fold | start | A | B | winner |
|------|-------|---|---|--------|
| f0 | 2025-07-07 | +0.602 (n171) | +0.521 (n158) | A |
| f1 | 2025-09-01 | +0.480 | +0.543 | B |
| f2 | 2025-10-27 | +0.176 | +0.376 | B |
| f3 | 2025-12-22 | +0.428 | +0.494 | B |
| f4 | 2026-02-16 | +0.329 | +0.447 | B |
| f5 | 2026-04-13 | +0.385 | +0.336 | A |
| f6 | 2026-06-08 | +0.310 | +0.369 | B |
| f7 | 2026-08-03 | +0.314 | +0.399 | B |

**B wins 6/8 pooled** (threshold met).  WF totals: B +0.450R (n=1040,
dd 3.2R) vs A +0.401R (n=980, dd 3.9R).  Per-asset fold wins:
BTC 7/8, ETH 6/8, SOL 5/8 - the edge is broad, not one-regime (the two
A-folds are early-train f0 and chop f5, and even there B never
collapsed).  A-B diff is regime-dependent: fold-level diffs range
-0.08..+0.20, so quote B conservatively as +0.40-0.45R, not +0.411.
DECISION: multi-asset LGBM (B) accepted as the ranking head of the
champion stack; portfolio math (D.2) should use WF-B numbers
(+0.450R pooled pess, dd 3.2R), never the optimistic single-split ones.

### Stage D.2b — portfolio layer (BTC+ETH+SOL) :white_check_mark: (p95 DD 2.6% << 30% flag ok)

Inputs: WF-B per-trade series (runs/d8b/wf_trades.parquet, 1040 trades,
Jul 2025 - Sep 2026; scripts/d9_portfolio.py).

Correlations, two lenses (scripts/d9_portfolio.py):
- PRICE daily-log-return corr: BTC-ETH +0.86, BTC-SOL +0.83, ETH-SOL
  +0.87 -> ONE cluster (>0.8 threshold).  Cluster limit = max 2
  concurrent positions in the whole crypto book.
- STRATEGY daily-P&L corr: +0.08..+0.23 -> low.  Third independent
  confirmation of "trading geometry, not direction": co-held positions
  lose money at different times because stop geometry, not direction,
  dominates outcomes.

Concurrency caps on real history (total 4 / cluster 2, entry-time sim):
capped accepts 826/1040 (214 rejected by cluster-2 limit), EV +467.6R
-> +364.1R, maxDD 2.9R -> 1.9R.  The cluster cap binds (one crypto
cluster), so effective concurrent-position limit is 2; EV cost of the
safer profile is ~22%.

Bootstrap (stationary block, 1000 sims, 10-day blocks, 1R = 1% equity):
maxDD p50=1.7R p95=2.6R p99=3.2R -> **p95 = 2.6% << 30% flag: OK** with
wide margin.  Kill-switch (DD-triggered pause): at K=4R/14d NEVER fires
(p99=3.2R below trigger) - armed but idle, correct as a safety net; at
K=2R it fires but tail DD does not improve (p99 3.3R) while costing
5.5% EV -> kill-switch NOT recommended as a return-enhancing overlay,
keep K=4R as disaster-only backstop.

Caveats (pre-registered follow-ups):
(1) WF A vs B context: D.8b fold table - B wins 6/8 pooled (BTC 7/8,
ETH 6/8, SOL 5/8), but the gap SHRANK from +0.115R (single split) to
+0.049R under walk-forward.  B upgrade stands on breadth (6/8), not on
margin; treat B-A as +0.05R honest, not +0.115R.
(2)-(4) resolved by runs/d9b_robustness.json (scripts/d9b_robustness.py):
- Block sensitivity 10/20/30/60d: p95 DD FALLS with block length
  (2.60 -> 2.23 -> 1.99 -> 1.79R) - short blocks are the CONSERVATIVE
  end here (more independent resamples, choppier paths), tail not
  understated.  10d numbers stand.
- Daily vs trade-event equity DD: daily 1.72R vs event 2.44R -> daily
  aggregation IS ~30% optimistic (exceeded the 20% threshold).  Quote
  portfolio DD from the event curve: real maxDD ~2.4R capped (~3R
  uncapped); bootstrap p95 quoted on daily basis should be read as
  ~3-3.5R event-equivalent - still << 30% flag.
- Capped-out trades (214): mean r_pess +0.484 vs accepted +0.441 ->
  rejected are NOT worse: capping is pure capacity loss, not a quality
  filter.  Reject rate drifts 16% -> 24% over time (candidate density
  grows); if live capacity becomes binding, consider EV-ranking-based
  admission instead of first-come.
DECISION: portfolio = BTC+ETH+SOL one cluster, max 2 concurrent
positions, 1R = 1% equity, kill-switch armed at 4R drawdown.  Planning
numbers: EV +364R/14.4mo capped (or +468R uncapped), p95 DD 2.6%.

### Stage D.10 — nested CV on the B head :white_check_mark: (discount -2.2%)

Closes the hyperparameter selection bias (scripts/d10_nested_cv.py,
runs/d10_nested.json).  Outer = the 8 WF folds; inner = last 25% of
fold-train by time (3d gap), grid of 6 LGBM configs
(n_est {150,400} x leaves {7,15,31}) selected by inner-val NDCG;
final fit on full fold-train, replay protocol identical to D.8b.
Result: NESTED +0.436R (n=1016) vs FIXED +0.427R (n=1026) ->
selection-bias discount **-2.2%** (expected -20-30% did NOT
materialize: the fixed params ne300/lv15 were chosen conservatively
back in D.4 on BTC only and never re-tuned on this data, so there was
nothing to overfit).  Config choice is stable-ish (ne150 x7, plus
capacity picks in high-volume folds).  EXTERNAL QUOTE: +0.44R pess per
trade, ~57 trades/mo capped, p95 portfolio DD ~3% equity (event-basis).
Planning numbers are now bias-corrected on both axes (protocol:
walk-forward; selection: nested CV).

### Stage D.11 — rank-based portfolio admission :white_check_mark: (+28% EV, DD flat)

Fixes the FCFS slot-mechanics alpha loss found in D.2b
(scripts/d11_admission.py, runs/d11_admission.json; trade stream now
exports model scores - d8b patch, WF numbers reproduced exactly).
Same 1040-trade stream, cap = 2 concurrent:

| policy | n | EV | mean | maxDD(event) |
|--------|---|----|----|--------------|
| FCFS (old) | 826 | +364.1R | +0.441 | 2.44R |
| REPLACE-low (replaced contribute 0) | 1010 | +466.0R | +0.461 | 2.44R |
| REPLACE-high (replaced keep full r_pess) | 1010 | +461.6R | +0.457 | 3.44R |

EV gain vs FCFS: **+102R (+28%)**, far above the +0.02-0.04R estimate.
Why so large: displaced worst-score trades realize NEGATIVE mean
r_pess - REPLACE-low (count them 0) actually beats REPLACE-high (give
them back their losses).  DD unchanged at 2.44R in the planning (low)
variant.  Live rule: when all slots busy and a new signal's score
exceeds the worst OPEN position's score, close the worst and take the
new one; planning numbers use REPLACE-low (mid-flight close assumed to
give back everything).  DAILY PLANNING: +466R / 14.4mo (~32R/mo),
maxDD 2.44R event-basis (~2.4% eq @1R=1%), p95 bootstrap << 30%.

Cluster limit re-check at 4h outcome resolution: corr +0.02..+0.07 -
strategy outcomes decorrelated at fine granularity too, cluster cap 2
stands (not too tight, not too loose).

### Stage D.12 — maker-entry revisit :x: (REJECTED - total adverse selection)

Pre-registered potential +0.05-0.10R; measured instead: STRONGLY
NEGATIVE (scripts/d12_maker.py, runs/d12_maker.json).  Setup: limit at
fill-delta*ATR into the zone, wait W bars, outcome recomputed from the
ACTUAL fill price via a maker variant of the unified sim (entry fee
reduced to 30% of taker, same slip/gap penalties).  Grid delta {0,
0.1, 0.25, 0.5} x wait {1, 4, 12}h on all 2,891 gated WF-B signals.
Baseline market-always: +0.380R per signal.
Results: fill rate 18-40%; given fill, mean pess R is ~-0.04R at EVERY
delta (even delta=0, where the limit matches the old market price).
EV/signal (maker-or-skip) = -0.03..-0.07R vs +0.38R market -> lift
-0.41R.  MECHANISM: fills happen exactly when price trades through the
level - i.e. when the zone fails; adverse selection eats the fee
saving (worth only ~0.07-0.14R) many times over.  This was the last
cheap-cost hypothesis: the 0.25R market-cost assumption is not a
conservative placeholder, it is already favorable.  Execution edge
must come from elsewhere (REPLACE admission already banked +28%).

### Stage D.13 — OB/AVSL ablation :x: (DETECTORS CARRY NO EDGE - geometry does)

The pre-registered ablation splitting the +0.44R stack edge into
detector vs non-detector parts (scripts/ablation.py, runs/ablation*.json).
Four panel variants, identical builder and WF-B protocol (8x56d folds,
7d embargo, lambdarank, rule-table gate, cap state machine):
  A  real OB zones + AVSL (control; reproduces the published baseline)
  B  placebo OB zones + AVSL  (placebo = same side/height/confirm time,
     level shifted outward by U(0.25,3.0) x ATR(confirm); causal)
  C  real OB zones, AVSL off  (avsl/avsr NaN end-to-end: no
     avsl_bounce family, d_avsl features NaN, anchor:avsl* rules dead)
  D  placebo OB zones, AVSL off (detector-free stack)
Control check: variant A panel reproduces the production panel exactly
(235,950 rows BTC, identical market/2R counts) and scores +0.427R
pooled (n=1026, dd 4.3R) vs published +0.44 - harness calibrated.

Results (test pess R, n, maxDD event):
| variant | s1 | s2 | s3 |
|---------|----|----|----|
| A (real OB+AVSL)   | +0.427 (1026, 4.3R) | - | - |
| B (placebo+AVSL)   | +0.452 (1031, 3.2R) | +0.448 (997, 2.6R) | +0.477 (1089, 3.7R) |
| C (real OB, no AVSL)| +0.476 (1281, 4.8R) | - | - |
| D (placebo, no AVSL)| +0.539 (1490, 2.6R) | +0.541 (1430, 3.4R) | +0.531 (1459, 2.1R) |

Verdict (REVISED after D.13b diagnostics - see below): the first-pass
reading "detectors carry no edge" was TOO WIDE.  Decomposition:

1. COST GEOMETRY IS THE DOMINANT MECHANISM.  Within EVERY variant,
   EV is strongly monotone in stop width: quintile of risk_unit/ATR
   q0 (narrowest, cost_R 0.29) has ev -0.14 (A) / -0.09 (D), q2
   (cost_R 0.05) has +0.09 (A) / +0.05 (D).  Narrow stops die of
   round-trip cost drag (the D.3 mechanism), mechanically.  Placebo's
   outward shift widens risk_unit (17.4 -> 19.1 ATR) and cuts mean
   cost_R (0.099 -> 0.084) purely geometrically.
2. AT MATCHED GEOMETRY REAL OB WINS.  Among affordable rows
   (cost_R <= 0.05, ~54-60% of panel): A +0.0640 > B +0.0579 >
   C +0.0571 > D +0.0493.  The real-OB candidate stream is BETTER
   than placebo where costs are survivable.  The OB entry-timing/
   level signal exists; it is positive, not the +0.10..0.15R hoped
   for, but not zero and not negative.
3. THE D>A GAP IS A MIX EFFECT, NOT SELECTION: placebo shrinks the
   toxic tail (cost_R > 0.15: 21.6% of A rows contributing -0.036R/
   trade vs 17.2% contributing -0.024R for D).  "Random zones beat
   OB" is false; "random zones have fewer unaffordable entries" is
   true and mechanical.
4. AVSL IS ROBUSTLY HARMFUL (the one clean architectural finding):
   D - B = +0.08..0.09R in every seed; C > A at panel level; the
   avsl anchor stop rules were already the worst in stage 0.5b.
5. Fold robustness: D - A > 0 in 7/8, 6/8, 7/8, 7/8, 6/8 folds
   (seeds 1-5) but one regime fold contributes +0.28..0.37 of the
   pooled +0.09..0.11R; without it the gap is ~+0.05..0.07R.
   B - A is 5/8, 5/8, 5/8, 6/8, 3/8 folds - the "placebo OB better
   than real OB" first impression was NOT fold-robust; it was the
   AVSL/mix effect.

Pre-registration results table (test pess R, n, maxDD event; 5
placebo seeds for B/D - D > A in 5/5, B > A in 5/5, D > B in 5/5):
| variant | s1 | s2 | s3 | s4 | s5 |
|---------|----|----|----|----|----|
| A (real OB+AVSL)    | +0.427 (1026, 4.3R) | - | - | - | - |
| B (placebo+AVSL)    | +0.452 (1031, 3.2R) | +0.448 (997, 2.6R) | +0.477 (1089, 3.7R) | +0.453 (1019, 3.2R) | +0.432 (967, 2.1R) |
| C (real OB, no AVSL)| +0.476 (1281, 4.8R) | - | - | - | - |
| D (placebo, no AVSL)| +0.539 (1490, 2.6R) | +0.541 (1430, 3.4R) | +0.531 (1459, 2.1R) | +0.521 (1391, 1.9R) | +0.531 (1497, 2.5R) |

Caveats: 3 majors, 1h, 1.5y, one regime sample; placebo inherits real
zone timing/height/side (ablates LEVEL selection, not candidate
timing); diagnostics at panel level (no gate) + WF folds (gated).

Actions: (1) DO NOT go detector-free - real OB beats placebo at
matched cost geometry; (2) kill the toxic tail with an explicit
cost-aware rule (cap cost_R ~0.15 or min risk_unit in ATRs - the
mechanical -0.14R ev of q0 is pure cost drag); (3) drop avsl_bounce
and the anchor:avsl*/avsr* stop rules (robust +0.05..0.09R, the only
clean architectural finding); (4) re-run the ablation after data
expansion (15m, more assets) before freezing conclusions; (5) keep
detector tuning frozen - the affordable-segment OB edge (+0.064 vs
+0.049 placebo) is real but small; capacity/robustness work first.

### Stage D.13c — cost-cap grid + AVSL-off on the WF protocol :white_check_mark: (AVSL-off confirmed; cap is a dd lever, not free EV)

Measured the two D.13 actions on the gated WF-B protocol
(scripts/d13c_cost_cap.py, runs/d13c_cost_cap.json), no rebuild -
the cap filters (candidate, rule) rows with cost_R = 0.0025*fill /
risk_unit above the cap, which is deployable live (risk_unit is
known at signal time):

| config | test pess | n | maxDD |
|--------|-----------|-----|-------|
| A (control) | +0.427 | 1026 | 4.3R |
| A + cap 0.15 | +0.378 | 780 | 4.4R |
| A + cap 0.10 | +0.393 | 656 | **2.8R** |
| C = no AVSL | +0.476 | 1281 | 4.8R |
| C + cap 0.15 | **+0.502** | 970 | 3.6R |
| C + cap 0.10 | +0.454 | 718 | 3.0R |

Findings: (1) AVSL-off CONFIRMED on the gated protocol: +0.049R and
+25% trades - ship it (drop avsl_bounce + anchor:avsl*/avsr* rules).
(2) The cap is NOT free EV on the full stack: on A every cap LOWERS
mean (the gate loses rule options that were net-positive picks on
train) while cap 0.10 cuts dd 4.3 -> 2.8R; on C, cap 0.15 adds
+0.026R and cuts dd 4.8 -> 3.6R.  Best cell: C + cap 0.15 = +0.502,
dd 3.6R = +0.075R over control with -16% dd.  (3) The D.13 regime
fold is identified: fold 2025-10-27..12-22 (A +0.282 vs D +0.639)
and 2026-04-13..06-08 (A +0.239 vs D +0.502) - A's weak regimes; in
strong folds A >= D.  Wide-stop geometry matters most exactly where
the real stack degrades - a regime-aware stop-floor is the natural
next lever, not a global architecture change.

### Stage D.13d — regime trigger search: production vector does NOT separate the weak folds :x: (negative result, recorded to stop a wrong stop-floor)

Question before building a regime-aware stop-floor: is there a causal
signal that distinguishes f2 (2025-10-27..12-22) / f5 (2026-04-13)
from f1 (2025-09-01), with useful lead time?
scripts/d13d_regime_diag.py, runs/d13d_regime_diag.json.

Answer: NO at fold granularity.  The production regime vector
(z50/slope50 from SMA50, vol_pct = ATR% percentile, bbw_pct = BB-width
percentile, trailing 500 bars - all causal) has near-identical fold
means everywhere: |z50| 2.02-2.14 in ALL folds, vol_pct 0.41-0.55,
range% 13-20.  Candidate triggers have ZERO specificity - coverage of
vol_pct>=0.7: f1 33% vs f2 28% (flagging the GOOD fold more than the
bad one); |z50|<=0.5: 13-20% uniform; bbw_pct>=0.7: 24-36% uniform.

Latency is NOT the problem: f2 opens with a visible vol episode
(day 3-7 vol_pct 0.63-0.83 vs fold mean ~0.5) and f5 with a |z50|
collapse (day 3-7 |z| 0.5-1.1 vs fold mean ~2.0) - the detector sees
both within days.  The problem is that these episodes are not unique
to weak folds: f1 day 7 also shows ETH |z|=0.67, and vol spikes occur
in every fold.

Conclusions: (1) the weak-fold damage is NOT a slow regime the vector
can catch at fold/feature-mean level - it is episodic, trade-level
interaction (which candidates fire during intrabar-vol spikes against
narrow stops); (2) a stop-floor gated on z50/vol_pct/bbw_pct triggers
would burn EV in f1 without protecting f2/f5 - DO NOT build it on
these triggers; (3) next diagnostic must be trade-episode level: dump
per-trade (entry ts, r_pess, cost_R) for A and D, bucket by week, and
correlate weekly pess R with intra-week vol episodes - find what the
surviving trades in f2/f5 looked like vs the casualties.

New production baseline (accepted, from D.13c): C + cost_R cap 0.15 =
+0.502R, n=970, dd 3.0R (chronological).  Order matters: AVSL-off
FIRST, cap second - the cap loses EV on the full stack.

### Stage D.13e — metrics audit: "Sharpe 14" was the t-stat; dd was computed on a non-chronological curve :white_check_mark: (formulas now tested; performance LEVEL still suspicious)

Full pass over the metric plumbing (user flagged Sharpe = 14):

1. There is NO Sharpe anywhere in the codebase.  The 14 was
   ``trade_curve_stats["t_stat"]`` = mean/std*sqrt(n) - a SIGNIFICANCE
   statistic (mean in units of standard errors), not a Sharpe.  For
   C|cap=0.15: mean 0.502, per-trade std 0.46R, n=970 -> t = 14.2.
   Worse, the t-stat itself is inflated by dependence: pooling 3
   correlated assets multiplies it ~sqrt(3) with zero new information
   (now proven by test).  Naive t on the C cells reads up to 38.
2. Honest Sharpe, now computed and tested
   (``per_trade_sharpe`` = mean/std per trade;
   ``bucketed_sharpe`` = weekly R-sum Sharpe * sqrt(52), which absorbs
   intra-week overlap and cross-asset pooling): per-trade 0.72-1.08,
   annualized 5.7-16.5 across the grid; baseline C|cap=0.15:
   per-trade 1.08, annualized 12.3.
3. REAL BUG fixed in d13c: max_dd_r was computed on a PSEUDO-curve
   (trades concatenated per asset then per fold - not chronological),
   which overstated dd.  Corrected chronological dd, all cells:
   A|None 2.4R (was 4.3), C|None 3.7R (was 4.8), C|cap0.15 3.0R (was
   3.6), C|cap0.1 2.1R (was 3.0).  Consequence: earlier dd-based
   statements were partly artifacts - A's control dd is actually the
   LOWEST of the A cells; the cap no longer "cuts dd on A".  Mean
   ranking is unchanged: C|cap=0.15 remains the best cell (+0.502).
4. Formulas are now pinned by tests (118 passing): t-stat exact form,
   dd order-dependence, t inflation under pooling, per-trade Sharpe
   known values, bucketed Sharpe vs hand-computed weekly sums,
   unsorted-timestamp invariance, degenerate inputs.

OPEN CONCERN (the number, not the plumbing): even the honest
annualized Sharpe of ~10-16 is economically implausible for an hourly
strategy and per-trade Sharpe >1 is a classic look-ahead smell.  The
metric FORMULAS are verified; the suspicious part is upstream - the
r_net stored in the ablation panels (mean -0.027, std 0.858 over 24k
raw rows is sane, so the inflation appears at SELECTION time: the
gate picks rows whose outcomes cluster tightly).  Before any
production decision on the baseline level: audit the ablation panel
r_net computation for look-ahead (fill price vs decision bar, exit
indexing) and check the win/timeout/SL mix of the SELECTED trades.






### Stage D.13f — look-ahead audit of the gate + permutation-anomaly root cause :white_check_mark:

**Part 1 — REAL LEAK found and fixed.**  The rule table in all three
protocols (`ablation.py`, `wf_ab.py`, `d13c_cost_cap.py`) was fitted on
`~is_test` rows, i.e. on folds that are in the FUTURE relative to the
test fold.  Fixed: train mask is now strictly past-only
(`ts < fold_start - 7d embargo`).  With the honest table the grid
collapses: A|None +0.096R, C|cap=0.15 **+0.118R** (n=954, dd 6.1R;
was +0.427/+0.502R).  ALL prior stage-D numbers are RETIRED.

**Part 2 — permutation anomaly ROOT-CAUSED: the control was
mis-specified, there is NO residual leakage.**

Symptom: with `PERMUTE=42` (table fitted on shuffled `r_net`) test EV
stayed at +0.27..+0.36R, far above the honest +0.118.

Diagnosis (`scripts/_diag_perm_trace.py`, since removed, numbers below):
1. `fit_rule_table` really consumes the permuted `r_net` - the table is
   blind.  But the LGBMRanker was NOT permuted: it kept training on
   TRUE past `r_pess` labels.  The control therefore ablated only the
   table, not the ranker.
2. On the picks (max-`s` rule row per candidate, rule==table-rule,
   test folds) the per-rule EV is dramatically above the panel
   baseline: e.g. `zone:0.5` is -0.088R pess over ALL test panel rows
   but +0.68R (n=48) among ranker-top picks; `anchor:st:0.5` +0.58..+0.95
   on picks.  The ranker has genuine out-of-sample candidate-selection
   skill (entry-time features only - audited).
3. Pre-state-machine EV of permuted-table picks: +0.146R (n=808);
   post-SM +0.242R.  That is the ranker's skill flowing through a blind
   table - not leakage.
4. Full-pipeline permutation (ranker labels AND table labels shuffled):
   EV collapses to +0.064 pre-SM / **+0.069R** post-SM (n=441), which is
   statistically indistinguishable from the panel base rate over the
   same fold windows (**+0.010R**, n=46k; diff ~2 sigma, and post-SM
   trades are correlated so effective n is smaller).
5. Metric consistency check on identical picks: fresh `sim()` pess
   outcome vs panel `r_pess` differ by only +0.01R - the replay is not
   measuring a friendlier outcome than the panel.

Side finding RETRACTED in D.13g (see below) - it was based on the
phantom +0.118R number.

Bottom line SUPERSEDED by D.13g: the "+0.118R" honest number could not
be reproduced by any artifact (no commit, no json) and was WRONG; see
D.13g.


### Stage D.13g - gap-through-stop sim bug: the stage-D edge was 100% artifact :warning: RETIRE

**Correction to D.13f first.**  Two claims in the D.13f write-up were
wrong and are retracted:
1. "Honest grid collapses to A|None +0.096 / C|cap=0.15 +0.118" - no
   artifact backs this.  The saved d13c json (past-only mask) gives
   +0.437/+0.524, identical to the pre-fix run reproduced by d13g: the
   table leak was IMMATERIAL because the fitted table is fold-stable.
   There never was a "collapse".
2. "The informed table is worse than a noise table" - false; measured
   properly (D.13g, pre-sim-fix) the table gate +0.524 beats free
   +0.260.

**The real bug (found via the D.13e composition check).**  `sim()`
fills entries at `open[i+1]` and recomputes risk from that fill.  When
the entry bar OPENS beyond the stop (gap through stop), the trade was
booked as ~+1R (exit at `sl_price` on the far side of the gapped
fill) - but live the stop order fires immediately at market: a SCRATCH
(~0 net of costs).  Prevalence: 8-12% of ALL panel rows, ~+1R phantom
each.

Evidence (runs/d13g2.log, pre-fix): even in C|cap=0.15, hold<=1 trades
were 42% of trades, mean +0.72R, EV share ~1.1 - i.e. essentially ALL
of the cell's EV.  Win 82% with 69% "sl" exits, median hold 0 bars.
This also explains why the full-pipeline permutation only fell to
+0.07 instead of the +0.01 base rate: the artifact is STRUCTURAL, not
informational, so label permutation cannot remove it.

**Fix.**  `sim()` now detects the gap-through-stop entry and books an
immediate market scratch in units of `risk_ref` (intended
`risk_unit`; new optional parameter, all protocol callers updated).
Pinned by 3 new tests in tests/test_sim_engine.py (275 pass).

**Corrected grid (runs/d13g_ranker_only.json, fixed sim): EVERY cell
is negative.**  table/free: A|None -0.161/-0.135, A|0.15 -0.086/-0.095,
C|None -0.172/-0.134, C|0.15 -0.105/-0.066, C|0.1 -0.063/-0.064,
C|0.075 -0.048/-0.054.  Table-vs-free differences are now noise-level.

**VERDICT: stage-D approach is RETIRED.**  There is no edge - the
strategy loses ~0.05..0.17R per trade after honest costs in every
configuration.  The whole D-stage chain (+0.35..+0.52R, Sharpe ~12)
was the gap artifact; the ranker's genuine within-candidate rule skill
was real but ranked entries whose honest net EV is negative.  No
tuning, live testing, or downstream work on the stage-D gate as-is;
any restart needs a new entry hypothesis with positive net-of-cost
panel EV as a precondition.

### D.13g addendum - wrong-side stops: the poison was ALSO in the panel labels

The review pushed on the scratch booking; the data went deeper.
Empirical checks on the C panel (BTC):
- `fill_price = open(e+1)*(1+slip)` (confirmed; the earlier 0% match
  was a too-tight rtol against the slippage factor).
- **8.7% of rows have the stop on the WRONG side of the fill**
  (long with sl ABOVE fill): zone:0.5 (614), zone:1.0 (585),
  anchor:st:0.5 (325).  These are rows where the entry gapped through
  the stop level before the fill.  The builder's `_simulate_outcome`
  saw "stop level touched" and booked them as INSTANT WINS:
  r_net mean +0.935, 100% exit_reason=sl.  The ranker then trained on
  +0.94R labels and hunted these rows (42% of picks in some cells).
- Execution semantics: entry and the instant stop fire at the SAME
  gapped open, so the honest live outcome is a scratch (~-costs), not
  a win - and also not a "-1.5R": there is no position held through
  the gap, the fill and the stop execution coincide (the proposed
  "gap 0.25 ATR => r=-1.25R" criterion assumes a pre-gap entry price
  that market-at-next-open execution does not provide).

Fixes:
1. `sim()` gap-through-stop -> immediate scratch in `risk_ref` units
   (previous commit).
2. Both dataset builders (`build_mtf_dataset.py`,
   `build_stop_dataset.py`) now mark wrong-side-stop rows invalid
   (r_net=nan) - panel rebuild still TODO; interim load-time filter
   added to d13g/d13c (identical effect for this bug: all other rows'
   labels are computed with valid geometry).

Final honest numbers, fixed sim + wrong-side filter
(runs/d13g_ranker_only.json):

    cell          table    free
    A|cap=None   -0.028   -0.057
    A|cap=0.15   -0.028   -0.049
    A|cap=0.1    -0.108   -0.056
    A|cap=0.075  -0.053   -0.074
    C|cap=None   -0.062   -0.075
    C|cap=0.15   -0.043   -0.039
    C|cap=0.1    -0.084   -0.050
    C|cap=0.075  -0.077   -0.032

Permutation control on the fixed pipeline (d13c PERMUTE=42):
A|None -0.032, C|None -0.041, C|0.15 -0.049 - now indistinguishable
from the honest cells and from zero.  The control finally behaves:
no structural artifact left.  Composition is sane (hold med 47,
time-dominated, win 0.4-0.5).

VERDICT UNCHANGED but now airtight: stage-D EV = -0.03..-0.11R ~=
-costs in every configuration; no edge; RETIRED.  TODO: full panel
rebuild with the builder guard, then re-run D.8+ experiments before
trusting any historical number.

## D.14: funding carry feasibility check (post-D new hypothesis)

Delta-neutral carry screen (`scripts/d14_funding_carry.py`,
`runs/d14_funding_carry.json`): short perps with positive funding /
long with negative (spot leg hedges price risk; PnL = collected
funding).  29 OKX USDT perps, daily funding = sum of 3 settlements,
signal = trailing 3-day mean, daily top-3/bottom-3 equal weight,
0.3% round-trip cost per new position (perp taker 2x + spot leg).

New infra: `fetch_funding_history()` in `engine/marketdata/okx_fetch.py`
(OKX /public/funding-rate-history; NOTE: needs SWAP instIds, returns
dict rows, and only serves ~3 months of history).

Result (Jun 15 - Sep 15 2026, 96 days):

    gross_daily_mean_bp        1.61   (+5.9%/yr)
    gross_daily_sharpe         27.5   (hit rate 0.97 - carry persists)
    avg_daily_cost_bp         10.48   (2.1 new positions/day x 0.3% / 6)
    net_annualized            -0.324
    net_daily_sharpe          -30.3

Reading: the funding edge is real and highly persistent, but tiny
(1.6 bp/day) while a daily-rebalanced top-3 book pays 10.5 bp/day in
turnover costs.  Breakeven needs ~1 week average holding at taker
costs (0.3% / 7d = 4.3 bp/day still > gross) - the steady-carry
version does NOT pass the net-of-cost pre-condition on this window.

Caveats: 96 days only (OKX history limit), a calm low-funding regime,
29 assets, taker costs.  An event-driven variant (enter only on
funding spikes > hurdle, hold until normalization) is untested and
is a different strategy.  Steady funding carry: NO-GO for now.


## Panel rebuild closed; interim filters removed; mfe/mae collector

Full panel rebuild with the builder wrong-side guard is DONE.
Re-run on clean panels, no load-time filtering:

  - ablation: A -0.038, B -0.081, C -0.112, D -0.063 (all negative;
    placebo stack B/D worse than real A/C - poison was in the labels,
    not the detectors).  runs/ablation.json
  - d13g grid identical to the interim-filtered run to the digit,
    same per-cell n (640/634/627/615/627/620/618/601); hold<=1 n=0.
  - d13c re-run OK.

=> interim wrong-side filters removed from d13g/d13c (dead code;
   single source of truth = builder guard).  Stage-D verdict
   UNCHANGED and now grounded entirely in rebuilt panels.

New infra: engine/mfe_mae.py - universal DSL-configured MFE/MAE
collector (signal = any dsl expression evaluated bar-by-bar on a
prefix-bound context; causal by construction; prefix-invariance
tested).  Outputs abs/atr/R excursions per event.  R unit here is
sl_atr_mult * ATR(signal bar), NOT the main stack's rule risk_unit.
modes: entry=next_open|signal_close, exit=horizon|sl_hit (window
ends at stop-touch, hit bar included, sl_hit flag always recorded).
19 tests in tests/test_mfe_mae.py.

## Protocol extracted to engine (scripts slimmed down)

New engine/protocol.py owns the WF-B mechanics that lived
(copy-pasted) in wf_ab / ablation / d13c / d13g: protocol-panel
loading (reference filter + cost_R + cap + r_pess), fold calendar
(8x56d, 7d embargo), lambdarank train_ranker (past-only groups,
seed 7), multi-asset assemble_ranker_data, gated replay (top-s per
candidate, optional rule-table gate, sim + state machine),
pooled_stats.  Scripts keep only grids + reporting (d13g 272->135
lines, d13c 273->155).

CRITICAL lesson from the regression runs (all four scripts re-run
and compared byte-for-byte against pre-refactor JSONs):

  - LightGBM binning is encoding-sensitive.  The D.13 family feeds
    float32 zero-filled NaNs; wf_ab (D.8b) fed a pandas DataFrame -
    which silently upcasts to float64 and keeps NaN natively.
    Training wf_ab on the D.13 encoding flipped exactly 2 of 24
    ranker fits (fold-5-A BTC, fold-6-B) with visibly different
    trade counts (nB 20 vs 46).  assemble_ranker_data therefore has
    explicit fill_nonfinite / x_dtype params, and each experiment
    family's encoding is pinned in its script.
  - Original-code determinism verified: wf_ab run twice from git
    HEAD reproduced its JSON byte-for-byte, so any diff = real.

Final state: d13g/d13c/ablation/wf_ab outputs identical to
pre-refactor (ablation run with --reuse: only elapsed_s and
build=None differ, evaluation identical).  13 tests in
tests/test_protocol.py (folds, embargo boundaries, ranker
determinism + row-permutation invariance, replay gate/state
machine, loader filter/cost/pess, encoding variants).

## Encoding pinned; rel/seed diagnostics

Encoding presets ENCODING_D13 / ENCODING_D8B are now module
constants in protocol.py (single source of truth; wf_ab passes
ENCODING_D8B by reference, D.13 scripts take the default).  Never
inline fill_nonfinite/x_dtype literals.

Diagnostics on real panels (runs/probe_rel_seeds.log):

  - rel = clip(round((r_pess+2)*2), 0, 12): 73.7% of 282k rows in
    [2,6] (|y| <= 1R); ZERO rows at rel >= 10 - the cap never
    binds, no LambdaRank tail instability.  Formula kept as-is.
  - random_state is INERT here: seeds 1/2/3/42 vs 7 give
    max|d score| = 0.0 exactly (feature_fraction=bagging=1.0 -> no
    sampled randomness).  Therefore every run-to-run flip can only
    come from the feed encoding - confirmed again (D13 vs D8B:
    max|d| = 2.075 same fold, same seed).
  - Known limitation, deliberately kept: D.13 encoding maps
    warm-up/MTF NaN features to 0.0 ("missing" == "zero"), which is
    semantically lossy but is the encoding every D.13 verdict was
    produced with - changing it would invalidate all comparisons.
    NaN-native is available via ENCODING_D8B for future families.

## FeatureSpec DSL + MTF as-of adapter

- engine/dsl_feed.py: shared bar-DSL plumbing (SeriesCache,
  make_bar_context, BAR_DSL_MANIFEST) extracted verbatim from
  mfe_mae.py; mfe_mae re-exports - one indicator implementation and
  one causality contract for all bar-level DSL consumers.
- engine/feature_spec.py: FeatureDef/FeatureSpec (JSON-serializable)
  + collect_features(df, spec, event_idx) -> per-event Float64
  matrix.  Numeric feature-style evaluation via the new
  Interpreter.visit_numeric (arithmetic/historical keep numeric
  value, warm-up NaN propagates; comparison/logical -> 1.0/0.0).
  Causal by construction: prefix invariance and future-mutation
  invariance are pinned by tests.  Fail fast: names/exprs validated
  at spec construction, event_idx must be sorted/unique/in-range.
- engine/mtf.py asof_join_features(): HTF columns into a base frame
  under strict known_ts <= ts (closed bars only), optional age_col
  (staleness is a legitimate known-at-decision-time input).
  NOTE: resample_ohlcv buckets align to the epoch - MTF tests must
  use a grid-aligned base ts (T0Q in tests).

## Audit: visit() semantics, backward compat, warm-up

- visit() audit: exactly two production consumers of the BOOLEAN
  signal interpreter - engine/mfe_mae.py (signal) and
  dsl/evaluate.py evaluate_dsl.  Both are bool-by-contract; no
  consumer expects numbers from visit().  Numeric path is
  Interpreter.visit_numeric (feature_spec only).
- backward compat: no production module imports engine.mfe_mae
  (only its own tests); d13c/d13g/wf_ab unaffected by the
  dsl_feed extraction.
- dsl_feed: make_bar_context split into make_bar_provider (provider)
  + make_bar_context (Context wrapper) so hybrid contexts can
  combine bar DSL with extra column providers.
- warm-up pinned: close[3]/close[5] at idx 0 -> NaN, NaN comparison
  -> 0.0 flag; boolean feature cols are Float64 (schema asserted).
- asof_join_features staleness policy documented: adapter never
  filters stale HTF bars; freshness caps belong to FeatureSpec /
  event filtering, explicit and testable.

## FeatureProvider (engine/feature_provider.py)

ColumnProvider + HybridContextFactory: expose bar-aligned feature
columns (e.g. asof_join_features output) to DSL expressions via the
context_factory hook of collect_features / collect_mfe_mae.
Causal guards: col[k] -> row bar_idx-k; pre-row-0 reads are NaN;
negative offsets and out-of-range reads raise; row alignment
(height + ts equality) enforced once on first call; collisions with
bar-DSL indicator names rejected at construction.  Causality of
column VALUES is the producer's contract (known_ts <= ts for MTF).
End-to-end smoke: 1m bars -> 1h resample -> asof join -> DSL features
(htf_gap numeric, in_hrange/stale flags) verified live.
NOTE: DSL numeric literals do not support underscores (3600000, not
3_600_000).

## D.14: feature-family A/B (scripts/d14_feature_family.py)

Same panel rows / fold calendar / pess labels as the D.13 protocol;
only the ranker feature matrix changes.  Four arms, ranker-only free
gate, 8x56d folds, 3 assets, main panel:

  d13|enc=d13  pess=-0.057 (dd 41.0R)  decile spread +0.708  [baseline]
  d13|enc=d8b  pess=-0.062 (dd 43.6R)  spread +0.682
  d14|enc=d8b  pess=-0.293 (dd 285.1R) spread -0.051  [no signal alone]
  combo|enc=d8b pess=-0.038 (dd 26.0R) spread +0.697  [best]

Findings:
- encoding effect isolated and small (d13: -0.057 vs -0.062 under
  d8b) - families stay on their pinned encodings.
- D.14 family alone (13 scale-free bar-DSL + 4h-asof features, no
  side/zone/structure context) does NOT rank: flat decile ladder.
  Side-neutral market-state features are necessary but not
  sufficient; D.13's power comes from zone/side/structure features.
- combo: D.14 columns add ~+0.024R pess over d13|d8b and cut max DD
  43.6 -> 26.0R; top decile -0.04 vs -0.05 (conditional EV edge).
  Direction worth pursuing, not yet decision-grade.

Notes: D14 spec renames atr_pct -> atr_pct24 (D.13 build_features
already emits atr_pct; duplicate column labels crash pandas concat).
NaN share of D14 matrix is 0.000 - event bars sit past warm-up.
Saved: runs/d14_feature_family.json, runs/d14_feature_family.log.
Env: repo ruff currently fails on pre-existing pyproject RUF067
selector (unrelated); pytest 327 passed.

## D.15: honest order-block rework (ta pipeline) + raw EV

Semantic bug fixes in ta/src/custom/market_structure (engine okx.py
untouched - engine panel uses its own detect_order_blocks):

- Zone = source pivot bar range [low, high] + zone_atr_multiplier*ATR
  extension (zone_source: range|body|close_band, default range;
  close_band = legacy close +/- m*ATR).  Old default was a
  close +/- 1 ATR band, not an order block.
- Wick entry symmetry: supply tested by high[j], demand by low[j]
  (was inverted for supply).  Penetration guard now meaningful.
- check_orderflow_shift made causal: past window (idx, j] only,
  confirm-guarded pivots, ValueError when online ZigZag is off
  (offline pivots + shift filter = look-ahead leak).
- min_extreme_gap filter now confirm-guarded: rejects only when the
  next extreme was confirmed before the breakout bar.
- reversal_atr_multiple (k * median ATR, default preset k=2.5)
  replaces per-TF online_reversal_pct constants (reversal/ATR ratio
  decayed 4.05 -> 0.67 ATR across TFs in the old presets).
- Presets recalibrated: ADX filter off, RSI confirmation off,
  cluster_blocks off (1m-1h), confirmation_window 36 on 5m/15m
  (retest-delay p90 ~ 35), zone_atr_multiplier 0.2,
  use_online_extremes default True (honest by default).
- multiple_breakouts=True on 5m/15m, lookback_max=30: semantic bug -
  with multiple_breakouts=False the "break" was tested at exactly one
  bar (lookback after pivot), i.e. all candidates had a constant
  break delay (5 on 5m, 20 on 15m) and lookback_max was a no-op clamp,
  not a search window.  Natural first-break delay: med 8, p90 28.

Raw EV (in-sample, BTC-USDT only, 35070/9360 bars 15m/5m, taker 5bp
both legs, entry at retest close, stop beyond zone edge + 0.25 ATR,
TP in R, horizon 48 bars, conservative within-bar ambiguity):

  15m: blocks 567, gross EV +0.019/+0.044/+0.031 R at TP 1/3/6R
       (net -0.16/-0.13/-0.15R); win 47/16/3.5%
  5m:  blocks 1559, gross EV -0.045/+0.026/+0.034 R (net ~-0.25R)

Preliminary positive gross, pending walk-forward.  Do NOT read as
"OB works": single asset, in-sample, gross only.  Note: pre-fix runs
on the fixed-delay semantics showed 15m/6R +0.140R gross - mostly an
artifact of the constant break delay, not an OB edge.

Known anomaly (diagnostic for WF train folds, not an in-sample loop):
validated blocks skew to late breaks (pivot age med 32 vs natural
first-break med 8).  Hypothesis: early breaks are impulses (zone
consumed), OB retest works on post-consolidation reversals.  To be
checked via EV vs (break_idx - idx) on train folds.

WF (runs/ob_wf_ev.log, engine/experiments/ob_wf_ev.py): 7x56d folds
(history
holds 6.5 such windows; embargo 7d; causal prefix detection, ATR
median on prefix; fixed params - nothing fitted, folds measure
stability only).  Gross EV per fold (blocks per fold 39-100):

  fold     0      1      2      3      4      5      6   pos  mean
  1R   +0.001 +0.001 +0.013 +0.011 +0.026 -0.111 +0.103  6/7 +0.006
  3R   -0.053 +0.007 +0.091 +0.026 +0.082 +0.134 -0.024  5/7 +0.038
  6R   +0.141 -0.020 +0.187 -0.069 +0.062 -0.002 -0.101  3/7 +0.028

Verdict vs the pre-registered criteria (6/8+ -> maker; 4-5/8 ->
boundary, dig delay/age; <4/8 -> close): BOUNDARY.  1R is stable but
EV ~ 0; 3R positive in 5/7 with the best pooled gross; 6R pooled
positive but only 3/7 folds.  Gross is far below the ~0.16-0.18R
taker round trip everywhere - any continuation requires maker entry.

Age anomaly RESOLVED, no selection effect: validated ages span
[30, 60) with min=p10=30 - exactly the dynamic lookback (30 on 15m).
In candidates.py the break search starts at bar i = idx + lookback:
lookback is the pivot CONFIRMATION lag (causality - an online zigzag
pivot is not knowable earlier), so every tradable break is >= lookback
by construction.  The "natural med 8" distribution is offline and
untradeable.  Hypothesis 3 ("OB works on reversals, not impulses") is
not testable as posed; the real knob is the confirmation depth
(lookback) - a train-fold tuning question, after WF, not a bug.

Retest delay did not shift: break->retest med 5, p90 23 - cw=36 now
covers p90 with margin (in-sample p90 was censored at the window).

Train-fold diagnostics, step 1 - delay curve (runs/ob_delay_curve.log,
engine/experiments/ob_delay_curve.py; pre-registered buckets, TPs
{3,4}R; train = folds 0-3 + 7d embargo, test = folds 4-6 held out;
gross R, taker NOT included):

  delay      TRAIN n  EV3R/win      EV4R/win | TEST n  EV3R/win     EV4R/win
  [0,5)          157  -0.012/31.8%  -0.016/29.9% |  93  -0.115/32.3%  -0.101/32.3%
  [5,10)          60  +0.229/40.0%  +0.425/40.0% |  31  +0.242/35.5%  +0.198/32.3%
  [10,20)         73  +0.028/38.4%  -0.066/35.6% |  31  +0.123/32.3%  +0.252/32.3%
  [20,36)         64  -0.104/31.2%  -0.178/29.7% |  24  +0.211/50.0%  +0.058/50.0%
  pooled         354  +0.020/34.5%  +0.019/32.8% | 179  +0.032/35.2%  +0.033/34.6%

The [5,10) bucket passes the +0.03R criterion on BOTH TPs on train
AND confirms on held-out test at both TPs (+0.24/+0.20).  Fast-retest
zones (5-10 bars after break) carry the whole edge; immediate retests
(<5, the same impulse returning) and stale ones (20+) are a drag.
Caveats: test n=31 -> per-trade std gives SE ~0.27R (t ~ 1.5 pooled
n=91); 8 cells were scanned on train - the [5,10)x4R +0.425 cell is
inflated by selection, trust the cross-segment consistency instead.
Gross target (+0.10R) reached by the cut alone: delay in [5,10) -
proceed to lookback calibration and TP grid, then maker model.

Steps 2-3 - lookback grid + TP grid (runs/ob_lookback_grid.log,
engine/experiments/ob_lookback_grid.py; delay-cut [5,10) fixed;
static lookback via use_dynamic_lookback=False; train decides):

  L   TRAIN n  EV3R   EV4R   EV5R | TEST n  EV3R   EV4R   EV5R
  15      75  +0.102 +0.124 +0.126 |  37  +0.330 +0.438 +0.476
  20      70  +0.049 -0.023 -0.021 |  33  +0.493 +0.281 +0.341
  25      69  +0.058 +0.080 +0.071 |  36  +0.218 +0.064 +0.091
  30      60  +0.229 +0.425 +0.451 |  31  +0.242 +0.198 +0.230
  35      65  -0.070 -0.009 -0.097 |  20  +0.206 +0.283 +0.332
  40      68  +0.043 -0.007 -0.001 |  27  +0.329 +0.255 +0.254

Verdict: L=30 (the current dynamic preset clamps to exactly this) is
the train argmax - preset unchanged.  Train L-surface is jagged
(L=35 negative), i.e. weak identifiability; test column is noisy
(n=20-37) and NOT used for the decision.

TP surface at L=30, delay [5,10) saturates (extended run, gross):

  TP      3R     4R     5R     6R     8R
  TRAIN +0.229 +0.425 +0.451 +0.478 +0.495   win 40/40/38/38/38%
  TEST  +0.242 +0.198 +0.230 +0.262 +0.327   win 35/32/32/32/32%

Pooled train+test (n=91) at 4R: +0.35R, at 6R: +0.40R gross ->
~+0.19..+0.25R net after taker round trip.  SE ~0.17R (t ~ 2-2.5).
Working point: delay in [5,10), lookback 30, TP 4-6R, horizon 48.

Warning: selections are stacking (4 delay buckets x 6 lookbacks x
6+5 TPs scanned on train) - the working-point EV is upward biased;
folds 4-6 are burned for this config family.  Next: maker entry
model on the working point, then fresh-data validation on another
asset (15m AVAX/BNB) as the real holdout.

Holdout verdict - the pocket does NOT replicate (runs/
ob_holdout_assets.log, engine/experiments/ob_holdout_assets.py;
fixed point delay [5,10), L=30 static, TP {4,6}R, gross, zero
tuning on holdout):

  PRIMARY   n     EV4R/win    EV6R/win   delay med
  AVAX      197  +0.024/29%  -0.038/28%     6
  BNB       109  -0.177/27%  -0.191/26%     7
  SOL       237  -0.069/28%  -0.120/27%     6
  ETH       275  +0.178/36%  +0.139/34%     7
  SECONDARY (bonus, same fixed point)
  DOGE      217  +0.270/39%  +0.265/38%     7
  LINK      100  +0.044/32%  -0.008/31%     6
  LTC       229  -0.155/31%  -0.135/30%     6
  NEAR      191  -0.119/28%  -0.096/27%     7
  XRP        85  +0.105/34%  +0.186/34%     7

Pre-registered criterion: >=3/4 primary gross>0 -> maker; <=1 ->
close.  Result: 1-2/4 (clearly positive only ETH; AVAX ~0; BNB/SOL
negative).  All 9 assets pooled per-trade: 4R ~ +0.02R, 6R ~ +0.00R
- zero, below taker.  Delay med 6-7 replicates the BTC mechanism
timing but carries no edge outside BTC.  The BTC +0.35R working
point was selection-inflated + asset-specific.

DECISION: close the OB directional track per the pre-registered
rule.  No maker study (would model net on inflated gross).  Pivot:
funding carry.  Negative result is clean: pipeline semantics now
causal, the fast-retest mechanism timing is real and replicates,
the profitability does not.

Reopened (scoped): "OB geometry is BTC-specific" hypothesis.
Phase 0 structural diagnostics (runs/ob_struct_diag.log,
engine/experiments/ob_struct_diagnostics.py), 10 assets x 15m:

  asset  bars/ATR hl_ar1 hl_acf pv_lag p50/90 ret_p90 rng/ATR vol_ir gap  EV4R
  BTC      2.51  0.479   1    2 / 9    27     0.87  13.2  ~0  +0.348
  ETH      2.64  0.442   1    2 / 9    26     0.86  13.3  ~0  +0.178
  SOL      2.50  0.402   1    2 / 8    24     0.89  10.2  ~0  -0.069
  BNB      2.45  0.413   1    1 / 8    24     0.87  17.0  ~0  -0.177
  AVAX     2.40  0.400   1    1 / 6    24     0.88  17.4  ~0  +0.024
  DOGE     2.53  0.431   1    1 / 6    22     0.88  14.4  ~0  +0.270
  XRP      2.54  0.414   1    1 / 7    23.4   0.88  11.4  ~0  +0.105
  LINK     2.46  0.418   1    1 / 7    21     0.86  17.6  ~0  +0.044
  LTC      2.43  0.405   1    1 / 6    23     0.88  21.4  ~0  -0.155
  NEAR     2.32  0.375   1    1 / 6    22     0.89  12.1  ~0  -0.119

Spearman vs EV4R/EV6R: half_life_ar1 +0.77/+0.71, bars_per_ATR
+0.72/+0.65, gap_freq -0.66/-0.54 (degenerate metric, all ~0);
retest_p90, pivot_lag, volume_irreg, spread < 0.4.

Phase-0 criterion met (corr > 0.7) -> Phase 1 allowed.  Caveats:
metric spread is only 1.1-1.3x (not the hypothesised 2-3x); literal
half_life_acf spec is degenerate (return ACF < 0.5 at lag 1 always);
n=10 with noisy EV ranks.  Key structural fact: actual zigzag pivot
confirmation lag is p50=1-2, p90=6-9 bars - lookback=30 is ~4x the
real confirmation lag, so the Phase-1 formula (lookback = 1.5 x
pivot_p90 ~ 9-14, cw = 2 x retest_p90 ~ 42-54) would produce a
genuinely different configuration, not a cosmetic one.

PHASE 1 (reduced, PRE-REGISTERED before the run): the original
formula is broken - vol half-life ~1 bar cannot set a delay range
(conceptually wrong measure), and min_extreme_gap = 0.5 x pivot_p50
would disable the filter (p50 = 1-2).  What survives is a BTC-only
lookback recalibration:

  BTC only, 15m:
    lookback = int(1.5 x pivot_p90 = 9) = 13   (was 30, static)
    cw       = round(2.0 x retest_p90 = 27) = 54   (was 36)
    delay    = [5, 10)   (NOT adapted, kept from step 1)
    min_extreme_gap = 6 (default, NOT adapted)
    revATR = 2.5, zone_atr_multiplier = 0.2, TP = {4R, 6R}
  Secondary ablation arm (pre-registered, diagnostic only):
    lookback=13 with cw=36 (isolates the lookback effect).
  Decision on TRAIN (folds 0-3 + 7d embargo); test folds 4-6 are the
  readout vs the L=30/cw=36 baseline (train n=60 EV4 +0.425, test
  n=31 EV4 +0.198).  Criterion on EV_test: > +0.05R better -> the
  9-asset test with per-asset lookback/cw is allowed; within noise
  or worse -> phase 1 closed, OB track closed, funding carry.

PHASE 1 RESULT (runs/ob_lookback13.log, engine/experiments/
ob_lookback13.py): RECALIBRATION FAILS, criterion is a clean FAIL.

  arm                TRAIN n  EV4R/EV6R        TEST n  EV4R/EV6R
  A: L=30, cw=36        60  +0.425 / +0.478     31  +0.198 / +0.262
  B: L=13, cw=36 (abl)  73  +0.177 / +0.397     23  -0.171 / -0.241
  C: L=13, cw=54 (prim) 73  +0.177 / +0.397     23  -0.171 / -0.241

- EV_test drops -0.37R vs baseline (criterion was > +0.05R better);
  EV_train also lower.  Shorter lookback admits younger pivots whose
  fast retests are junk, not signal.
- B == C exactly: cw is irrelevant once the delay cut [5,10) is
  applied (all retests are < 10 bars after break anyway); cw only
  gates which blocks find a retest at all.
- Pivot-lag insight stands as a fact (real confirmation p90 = 6-9),
  but the "excess" lookback=30 was acting as a beneficial quality
  filter on pivot maturity, not as ballast.

FINAL: OB-retest on 15m is CLOSED per the pre-registered rule.
Hypothesis "lookback was masking edge" rejected.  Next: funding
carry recon (top-20 assets, funding history, annualized carry /
pct_positive / std), then baseline carry strategy.

Pre-closure diagnostics (runs/ob_ldgrid.log,
engine/experiments/ob_ldgrid.py) - all four confirm closure:

1. L x delay grid (5 L x 3 delay buckets, EV4R/EV6R, train vs test):
   NO coherent surface.  Cells flip sign between segments (L=13
   [5,10): train +0.51 -> test -0.10; L=35 [5,10): train -0.28 ->
   test +0.39; L=25 [8,15): train +0.22 -> test +0.84).  Train-best
   cells do not replicate; test-best cells were train-flat.  The
   "+0.35R working point" was a train-max artifact on a noise
   surface, as suspected.
2. Per-fold EV4R, delay [5,10): L=30 positive in 5/7 folds, L=13 in
   3/7; L=13 worse in 5 of 7 folds.  Consistent with the arm test,
   direction stable, magnitudes tiny-n noisy.
3. Age anomaly resolved: total validated blocks barely move with L
   (train 354 vs 355, test 179 vs 169; age med 40-41 vs 22-24, min
   age = L as expected).  The test survivor drop 31 -> 23 is delay-
   cut pool composition, not a missing population.
4. Null bootstrap of the holdout asset pattern: with true EV = 0 and
   per-asset SE from trade counts, P(>=5 of 9 positive) = 0.50,
   P(>=3 of 9) = 0.91.  Observed 5/9 positive at 4R (3/9 at 6R) is
   a coin flip - the "works on BTC/ETH/DOGE/XRP" pattern is
   statistically indistinguishable from noise.  Asset-segregation
   hypotheses (basis, beta, retail, depth) are moot.

OB-retest 15m: CLOSED, now with a defensible basis (grid incoherent,
bootstrap null-consistent).  Funding carry next.

## AVSL cross (new signal track) - PRE-REGISTERED before the run

Mapping (user-confirmed): fast line = avsl_ind(low, close, volume,
fast=70, slow=345) - the full AVSL indicator; slow line =
sma_ind(close, 345).  Data: BTC-USDT 15m okx21 (916d), warm-up 400
bars skipped.

Baseline arm (no filters): long when close crosses above fast
(close[t-1] < fast[t-1] and close[t] > fast[t]); short mirrored.
Signals with slow on the wrong side (risk = |close - slow| <= 0 or
stop beyond entry) are skipped - the stop is undefined there.
Stop = slow line at entry (structural); TP {3R, 5R, 8R}; horizon
192 bars (2d) with mark-to-market exit; conservative within-bar
ambiguity (stop wins).  Fees reported separately (gross / net with
taker 5bp x 2).  No cooldown, no alignment/ADX/volume filters -
those are step-3 arms, each pre-registered with criterion +0.05R
over baseline on train.

Segments: protocol folds 8x56d; train = folds 0-3, test = folds 4-7
(4 test folds; 916d history supports 16 windows).  Criterion on
train: EV > +0.05R signal, > +0.10R strong, <= 0 filters needed /
dead.  Readout: n, EV per TP, win rate, long vs short split.

BASELINE RESULT (runs/avsl_baseline.log): EV <= 0 gross, as the
pre-registered expectation for an unfiltered arm; filters are the
next step.  BTC 15m, 916d:

  TRAIN (folds 0-3): 1924 raw crosses (~2.1/day - the AVSL(70,345)
  line hugs price far closer than a swing MA; NOT 1-3/week), 757
  skipped (slow on wrong side - stop undefined).
    TP=3R n=1167 gross -0.003 (long -0.16/23%, short +0.08/31%)
    TP=5R n=1167 gross -0.007
    TP=8R n=1167 gross +0.098 (long -0.02/15%, short +0.16/22%)
  TEST (folds 4-7): 469 crosses, 181 skipped; gross +0.00/+0.06/+0.02.

Two structural findings:
1. Taker round trip in R = 2*fee*price/risk.  With no alignment
   filter the structural stop (slow SMA345) sits arbitrarily close
   to price on many crosses -> mean cost ~1.0R, net ~-1.0R.  The
   structural stop is economically undefined until slow-side
   alignment and a minimum-risk distance are enforced.
2. Long/short asymmetry flips between train and test (train short
   +, long -; test reversed) - no stable side edge at baseline.

Donor audit (user provided Pine source): the repo port is faithful
- lenV, VPCc clamp, PriceV/100, and the AVSL formula all match.
Two deltas: (a) Pine divides by PER-BAR VPCc[i] in the window loop,
the repo by the CURRENT bar's vpc_c (minor - VPCc moves slowly);
(b) donor default mult=2.0 vs stand_div=1.0 used in the first run.

Donor-calibration arm, stand_div=2.0 (runs/avsl_baseline_sd2.log):
  TRAIN n=1001 gross +0.03/-0.02/+0.05 (3/5/8R)
  TEST  n= 256 gross -0.03/-0.00/-0.07
Same conclusion: gross ~ 0, net ~ -0.85R (cost/risk collapse on
unfiltered crosses), long/short flip persists.  Cross frequency
~2/day is intrinsic to the indicator: AVSL is by construction a
trailing-stop line that lives near price (DeV offset), not a swing
level - the "swing cross" framing has no support in the formula.
Verdict unchanged: EV <= 0 -> filter step next, slow-alignment
first.  Honest alternative: treat AVSL crosses as what they are
(stop-flip events) or drop the track.

Bug fixes in ta/src/custom/avs_base.py (pre-validation, no Pine
cross-check by decision):
1. CRITICAL _price_v_rolling: window denominator now uses PER-BAR
   vpc_c[start+j] (Pine parity: src[i]/VPCc[i]/VPR[i] with i the
   loop index), previously current-bar vpc_c[i] was broadcast over
   the whole window.
2. _compute_len_v: banker's round() replaced with half-up
   floor(x+0.5), matching Pine's round().
Unit tests added (ta/tests/tests_custom/test_avs.py, 9 tests):
rolling mean on constant denominators, per-bar-VPCc regression
(fails on pre-fix code), zero-denominator skip, L=0 passthrough,
half-up rounding, len_v branches, vpcc clamp.  Full engine suite
green (236 passed / 2 skipped); ruff clean.
Fixed-code rerun (stand_div=2.0, runs/avsl_baseline_fixed.log):
  TRAIN n=990 gross +0.05/-0.01/+0.05; TEST n=260 gross
  -0.05/-0.02/-0.08 (3/5/8R).  Statistically identical to pre-fix:
  the VPCc-shift error was small (VPCc moves slowly).  Verdict
  unchanged: gross ~ 0 -> filters or close.

Long/short split + beta check + Path A (runs/avsl_baseline_fixed.log,
runs/avsl_align.log; stand_div=2.0, config 70/345):
1. Long/short EV tracks SEGMENT BTC DIRECTION, not signal quality:
   train (BTC -0.5% flat): short positive (+0.13/+0.10/+0.10),
   long negative (-0.09/-0.19/-0.02); test (BTC +8.4%): long
   positive (+0.14/+0.31/+0.08), short negative (-0.22/-0.26/-0.08).
   The "flip" between segments is beta BTC, confirmed by segment
   moves printed per segment.  Not a signal edge.
2. Path A slow-alignment arm (long: slow 1h-slope > 0 AND close >
   slow; short mirrored; pre-registered criterion +0.05R on train,
   all TPs): n 990 -> 648 train / 260 -> 175 test.  Train gross
   +0.039/+0.046/+0.135; test -0.071/-0.044/-0.066.  FAILS: two of
   three TPs below +0.05R on train, and the 8R TP that "passes" is
   negative on test.  Improvement does not transfer - consistent
   with the beta reading: the filter shaves trades but the residual
   EV is still segment drift.
Path A verdict: DEAD per pre-registration.  Path B (stop-flip exit
rule, separate experiment) or close the track.

Swap arm (for fun / diagnostic; runs/avsl_swap.log): entry line
= SMA(345), stop line = AVSL(70,345) - inverted config, same
protocol, stand_div=2.0.  Also fixed a NaN hazard: AVSL has
leading NaNs (~bar 400-710 in train), `risk <= 0` does not catch
NaN comparisons; entry loop now guards np.isfinite(risk).
  TRAIN (flat -0.5%): n=1089 gross +0.03/-0.00/+0.01
    [long -0.06..-0.11; short +0.19..+0.23]
  TEST (+8.4%):       n=248  gross -0.12/-0.23/-0.12
    [long -0.11/-0.21/+0.07; short -0.15/-0.27/-0.40]
Reading: swap is WORSE, and the beta pattern breaks - long is
negative even in a +8.4% segment.  Mechanism: SMA345 cross entry
is late (3.6d into the move), AVSL stop hugs price (tight risk)
-> stopped before continuation; net ~ -1.0R again.  Both configs
of AVSL/SMA cross-as-entry are dead; strengthens the B-or-C fork
(stop-flip exit rule vs closing the track).

Price-cross arm (no SMA; runs/avsl_price_cross.log): entry =
close crossing avsl(70,345) itself, stop = line at entry, both
orientations, 10 assets (BTC + 9 holdout), per-asset, train/test
as protocol.  Result: STRUCTURALLY DEGENERATE, not a fair test.
- Reverse arm: 0 trades on every asset/segment (100% skipped) BY
  CONSTRUCTION - at a down-cross close is below the line, so a
  reverse long has stop above entry: risk < 0 always.
- Normal arm: at the cross the line IS the price, so risk ~ 0 ->
  taker round trip = 2*fee*price/risk explodes (net -2.5R BNB-adj
  to -70R BNB-test); economically undefined, same cost collapse as
  the unfiltered baseline but worse.
- Only non-trivial signal: 8R TP gross is positive on 7/10 assets
  in BOTH train and test (e.g. AVAX +0.22/+0.03, LINK +0.23/+0.23,
  NEAR +0.08/+0.23) while 3R/5R are ~0/negative - tiny-risk, wide-
  target lottery asymmetry.  Untestable as taker: cost >> EV.
Conclusion: any stop tied to the AVSL line AT the cross is
economically void (risk -> 0).  Sane no-SMA designs are: (a) stop
= line + min-risk distance filter (bps of price, pre-registered),
or (b) Path B cross-to-cross flip, MTM, no fixed stop.

Price-cross v2, stop=1xATR(14)@entry (runs/avsl_price_cross_atr.log):
same 10 assets, normal + reverse, sane risk -> sane costs (net
-0.1..-0.6R).  Readout, 3R gross normal vs reverse:
  TRAIN: BTC +0.00/-0.02, AVAX +0.06/+0.01, BNB 0.00/-0.02,
  DOGE +0.04/-0.01, ETH +0.04/+0.02, LINK +0.12/-0.00,
  LTC +0.00/-0.03, NEAR -0.04/+0.02, SOL +0.10/+0.02,
  XRP -0.02/-0.01.
  TEST: BTC +0.02/-0.00, AVAX +0.01/-0.07, BNB +0.11/-0.02,
  DOGE +0.06/+0.00, ETH +0.00/+0.07, LINK +0.15/-0.00,
  LTC -0.02/-0.03, NEAR -0.07/-0.00, SOL -0.00/+0.03,
  XRP +0.12/+0.12.
Findings:
1. Normal beats reverse on ~7/10 assets in BOTH segments: the
   cross DOES carry directional info, but it is tiny, ~+0.03..+0.05R
   gross at 3R.
2. Absolute level ~ 0: 3R break-even win rate is 25%, observed
   24-29% -> EV ~ 0.  8R break-even is 11.1%; observed 12-15% ->
   small positive EV that is a property of the TP/ATR geometry
   (lottery payoff), present in BOTH orientations - not signal.
3. Taker costs on 1xATR(14) 15m risk (~0.3-0.5% price) are
   ~0.2-0.3R per trade -> every arm net-negative everywhere.
FINAL VERDICT, AVSL cross as entry (all configs tried: vs SMA345
stop, alignment, swap, price-cross ATR stop, both orientations,
10 assets): directional edge <= +0.05R gross, costs >= 0.2R ->
net-negative on every asset.  TRACK DEAD as entry signal.  The
only untested mechanism left is AVSL as exit (Path B stop-flip);
funding carry remains the standing pivot.

Path B stop-flip trailing (pre-registered, runs/avsl_trailing.log):
entry=cross, initSL=2xATR14, trail=AVSL-0.3ATR monotonic causal;
v1 time N=10 / v2 profit 1R / v3 AVSL>entry; bench=always-in;
10 assets, train folds 0-3.  Success criterion: trailing EV >
bench EV + 0.05R on train, replicated on test.
RESULT: 0/10 assets pass on train.  Best trailing vs bench EV
(train): BTC +0.148 vs +0.167, AVAX +0.202 vs +0.258, BNB +0.124
vs +0.082 (+0.042, <0.05), DOGE +0.150 vs +0.156, ETH +0.164 vs
+0.153 (+0.011), LINK +0.000 vs -0.022, LTC +0.006 vs +0.018,
NEAR +0.110 vs +0.084 (+0.026), SOL +0.119 vs +0.120, XRP +0.231
vs +0.183 (+0.048, <0.05).  Bench >= trailing on 6/10 outright;
no variant clears +0.05R-over-bench anywhere.
DD: trailing does cut maxDD (BTC 129-144R vs 178R; DOGE 45-53 vs
71; NEAR 57-61 vs 89) but only by cutting exposure - EV drops
proportionally.  No DD-free lunch.
Test replication: moot (nothing to replicate); test nets are
mostly negative, bench still generally >= trailing.
VERDICT: FAIL per pre-registration - trailing is beta with extra
steps.  AVSL track CLOSED in full: cross-as-entry dead (edge
~0.05R gross < costs ~0.2-0.3R), cross-as-exit no better than
always-in.  The always-in benchmark being the best arm is itself
the summary: the AVSL(70,345) line carries mild trend exposure
(beta), no tradable alpha at 15m taker costs.  Pivot: funding
carry recon.

Combined arm (user-requested, runs/avsl_trail_norm.log /
avsl_trail_rev.log): cross-entry + initSL=2xATR14 + IMMEDIATE
AVSL trailing (no activation gate; buffer 0.3ATR, monotonic),
normal AND reversed orientations, bench=always-in same orientation.
NORMAL trail vs bench, train EV: better on 6/10 but only XRP
clears +0.05R (+0.235 vs +0.183); NEAR +0.038; on test XRP
+0.183 vs +0.050 and NEAR +0.096 vs +0.005 do replicate, but 2/10
marginal passes are null-consistent (cf. OB bootstrap: asset
pattern coin flip at these sizes).  REVERSED trail: gross positive
9/10 train (fade + tight trail, win 40-46%, hold ~20 bars) but
below costs; net negative essentially everywhere, test 6/10.
DD: trail < bench nearly everywhere by construction (tighter
stops, smaller exposure), EV drops with it.
VERDICT: unchanged - no orientation/exit combo produces EV > bench
+ 0.05R robustly across assets.  XRP/NEAR flagged only as the
least-uninteresting cases; not actionable.  Track stays CLOSED.

HTF arms (runs/avsl_trail_htf.log): same combined design on 1H
(10 assets) and 4H (7 assets; no data for BNB/LINK/XRP).
1H NORMAL: bench (always-in) BEATS trailing on 8/10 train and
most of test (BTC test bench +0.29 net +0.20 vs trail -0.08;
SOL test +0.30 net vs -0.05).  Trailing still strictly dominated.
The only cross-TF pattern that is net-positive on multiple assets
in BOTH segments is the 1H ALWAYS-IN BENCH itself (train net:
BNB +0.48, DOGE +0.15, NEAR +0.14, SOL +0.12, XRP +0.07; test
net: XRP +0.74, SOL +0.30, LINK +0.27, BTC +0.20) - i.e. the
AVSL(70,345) line on 1H works as a plain trend-regime position
(long above / short below), which is beta-style directional
exposure, not per-trade alpha.  1H REVERSED: gross +7/10 test but
train only 4/10, different assets - noise.  4H: n too small
(test n=1..26 per arm; single trades dominate, e.g. ETH test
n=1 +7.6R) - no inference possible.
SUMMARY: AVSL(70,345) has one defensible use: 1H always-in regime
direction (beta overlay).  As entry signal, exit rule, or fade at
15m/1h/4h taker costs: closed.

yfinance data pipeline (engine/experiments/load_yf.py, data/yf/):
yfinance installed; 40 parquet files loaded (10 assets x 15m/1H/4H/
1D) in the okx21 schema (ts epoch-ms Int64 + OHLCV Float64), so
engine experiments run unchanged.  1H = 730d (17326 bars), 4H
resampled from 1H (4335), 15m = 60d (5742), 1D = full history
(2192-4387 bars, up to 12y).  Hour-aligned, gaps <= 7 on 1H.
DATA QUALITY WARNING: yfinance intraday crypto VOLUME is ~half
zeros (1H: ~8800/17326 zero-volume bars; 15m ~30%; 1D fine).
Anything volume-dependent (AVSL uses VWMA/VM) run on okx21 data
or 1D yf only; use yf intraday for price-only statistics or with
a volume-quality filter.

Universe expanded 10 -> 36 assets (3.6x).  144/144 files present
(36 x 15m/1H/4H/1D).  Yahoo rate-limits intermittently (different
symbols come back EMPTY per sweep; 2s pause + targeted re-runs
filled all holes).  Swaps after persistent Yahoo empties: UNI ->
CRV-USD, APT -> EOS-USD, SUI -> KSM-USD, GRT -> SAND-USD, PEPE ->
FLOKI-USD.  Final universe: BTC ETH SOL XRP DOGE AVAX LINK LTC
NEAR BNB ADA DOT UNI(CRV) ATOM APT(EOS) ARB OP FIL INJ SUI(KSM)
TIA SEI FET AAVE GRT(SAND) ALGO VET ICP HBAR ETC BCH TRX SHIB
PEPE(FLOKI) WIF TON.  Loader supports symbol filter args
(load_yf UNI APT 1H) + 2s throttle for targeted re-runs.

TRAILING ON YF UNIVERSE (runs/avsl_yf_{15m,1h,4h}.log; avsl_trailing
now accepts "yf" flag -> data/yf + 35-asset list): yf-specific
read path added: zero-volume ffill (see warning above) + bad-tick
excision (|1-bar logret|>50% bars -> OHLC := prev close, iterated).
TON EXCLUDED from yf stats: corrupt Yahoo series (636 bars stuck
at $0.017 after a fake -99.5% 1H print, Aug 2025); isolated spikes
in APT/ARB/TIA (1-5 bars) are excised.  15m yf not runnable: 60d
history < 448d walk-forward span (15m scale remains covered by
okx21).  Results (35 assets, net EV, pre-reg pass = train & test
both >= +0.05R, vs always-in bench same orientation):
1H NORMAL: 13/35 pass, trail>bench test 20/35, med diff +0.02R.
4H NORMAL: 11/35 pass, trail>bench test 25/35, med diff +0.16R.
1H/4H REVERSED: 6/35 and 3/35 pass, test med diff negative.
Reading: 4H NORMAL beats bench out-of-sample in 25/35 - nominally
binomial p~0.017, but (a) 6 configs tried, (b) 35 crypto assets
over one overlapping window are NOT independent trials, (c) trail
cuts exposure so bench DD (up to 200R on TRX) dominates gross
comparisons, (d) aggregate net-R is unusable (single 100x-trend
trades in SHIB/FLOKI give hundreds of R).  Before believing 4H:
block bootstrap over asset-level diffs + fresh window.  Verdict
unchanged pending that test: AVSL = beta overlay, not alpha; the
only new candidate is "AVSL trail on 4H" as DD-reducer.


