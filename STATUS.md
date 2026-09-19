# STATUS — what is implemented vs what is needed

Single consolidated summary. Legend: ✅ done · 🔨 in progress / core done · ⬜ not started ·
⬜=spec only. Full per-task detail: `dev_docs/tz/TZ-00-roadmap.md`.

## Implemented ✅ / core 🔨

| Module | Status | Tested/verified |
|--------|--------|-----------------|
| `ta/` indicator library | ✅ 84 indicators in DSL (TZ-03 wave 2) | 1975 tests |
| `dsl/` trading DSL | ✅ TZ-01 | 154 tests |
| `strategies/` strategy layer | ✅ TZ-02 | 25 tests |
| `backtest/` backtest | ✅ core; risk-gate ✅ TZ-04 | 34 + 12 integration |
| `risk/` risk engine | ✅ config-driven TZ-11 | 22 + 12 integration |
| `ai/` model | 🔨 core; trained on real data (OKX 7×4TF), best classifier of the baseline run — edge not yet achieved (gate not passed) | 71 tests + first backtest vs 7 baselines |
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

**Named risk profiles** now live in `configs/ai.yaml`: `risk_profile: default`
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
   execution assumption explicitly in configs/ai.yaml `risk`.
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


