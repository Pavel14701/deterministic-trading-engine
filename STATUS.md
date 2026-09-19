# STATUS — what is implemented vs what is needed

Single consolidated summary. Legend: ✅ done · 🔨 in progress / core done · ⬜ not started ·
⬜=spec only. Full per-task detail: `dev_docs/tz/TZ-00-roadmap.md`.

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
   `dev_docs/ai_baseline_report.md`.
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
   `dev_docs/ai_baseline_report.md` (thresholds, costs, horizon, DSL-config search)
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

Verdict: OB contribution (A-B) = **-0.03R** (negative in every seed);
AVSL contribution (A-C) = **-0.049R**; the detector-free stack D =
**+0.53..0.54R** - BETTER than the full stack (+0.11R, n +45%, dd
lower in 2/3 seeds).  The entire pess edge lives in stop/TP geometry
(rule table), cost-aware ranking, the gate and the slot state machine;
real OB level selection and AVSL contribute nothing measurable and
appear to cost R via candidate clustering (slot contention) and
low-quality avsl_bounce entries (consistent with D.5 anchor-stops and
D.12 maker adverse selection).  Corollary: "the OB finds zones that
hold" is NOT the source of the +0.44R - a random nearby zone does as
well or better.  Caveats: single regime sample (3 majors, 1h, 1.5y);
placebo keeps real zone timing/height/side so it ablates LEVEL
selection, not candidate timing per se; fold dispersion is real but
the B>A, D>A ordering is stable across all 3 placebo seeds.

Actions: (1) treat OB/AVSL as candidate generators, not edge sources -
no further detector tuning; (2) test dropping avsl_bounce outright;
(3) re-run this ablation after the data expansion (15m, more assets)
before committing to a detector-free architecture; (4) stop-head /
admission / state machine are the alpha carriers - hardening them
(and the live execution layer) is the priority.


