# TZ-00. Roadmap: consolidating the modules into one system

## 1. Purpose

Root document. Each TZ (TZ-01..TZ-15) is self-contained; the execution order is defined here.
Project: **Deterministic Trading Engine** (formerly `t_inv_rag`) — a deterministic trading
path; RAG/LLM is a supporting layer outside the decision loop.

## 1.1. Monorepo (uv workspaces)

Each module is a uv workspace member with an isolated environment:

| Package | Dir | Key deps | Tests |
|---------|-----|----------|-------|
| `dte-ta` | `ta/` | numba, numpy, scipy | `uv run --package dte-ta pytest ta/tests` |
| `dte-dsl` | `dsl/` | niquests | `uv run --package dte-dsl pytest dsl/tests` |
| `dte-strategies` | `strategies/` | polars | `uv run --package dte-strategies pytest strategies/tests` (TZ-02) |
| `dte-ai` | `ai/` | torch, tensorboard, pyyaml | `uv run --package dte-ai pytest ai/tests` |
| `dte-infer` | `infer/` | polars, yfinance, t-tech (+`ml`: torch) | `uv run --package dte-infer pytest infer/tests` |
| `dte-rag` | `rag/` | llama-index, qdrant, sentence-transformers | `uv run --package dte-rag pytest rag/tests` |
| `dte-risk` | `risk/` | numpy, pyyaml | `uv run --package dte-risk pytest risk/tests` |
| `dte-main` | `main/` | dishka, faststream, aiogram, sqlalchemy, alembic | — (TZ-08/10) |
| `dte-okx` | `okx/` | msgspec, pyyaml, dishka, niquests, websockets | TZ-15 core + live public md |

Monorepo principles:
1. **Environment isolation**: `uv sync --package dte-<x>` builds the env with only that
   package's deps; the full dev env is `uv sync --all-packages`.
2. **GPU deps isolated** (§4.7): torch exists only in `dte-ai` (and optionally
   `dte-infer[ml]`); `dte-dsl`/`dte-ta`/`dte-strategies`/`dte-risk` do not pull it.
3. **Import names unchanged** (`ta`, `dsl`, `ai`, `infer`, `rag`, `main`): packaging changes,
   code and existing tests do not break. Physical src-layout is not introduced until a second
   consumer appears (decision fixed here; revisit in TZ-08). Consequence: workspace members are
   virtual packages, so cross-package deps (e.g. `dte-infer` → niquests/numba/scipy for dsl/ta)
   are declared directly in the member's pyproject, not as workspace deps.
4. Each workspace member has its own `pyproject.toml` (+ `pytest.ini`); the root project only
   carries dev tools and the shared test stack.

## 2. System map

```
Exchanges (T-Invest, OKX) ──► [White API: ingest + REST + aiogram]   (public contour, no GPU)
                                  │  RabbitMQ over TLS
                                  │  connection initiated by the LOCAL node (outbound,
                                  ▼  inbound ports on the local are closed)
                          [Local GPU node: ai training/inference,
                           ta+DSL engine, backtest, RAG, Qdrant, Ollama]
```

Inside the local node:

```
ta ──(TaProvider, TZ-03)──► dsl ──► backtest (TZ-04) ──► reports ──► White API
                         ▲                    ▲
              strategies (TZ-02)          ai P(win) (TZ-06)
## 3. Execution order and statuses

Legend: ✅ done · 🔨 in progress · ⬜ not started (order fixed by TZ-00).

| # | TZ | Status | Why here |
|---|----|--------|----------|
| 0 | TZ-14 quality baseline | ✅ (ruff single linter, root pytest config + service markers, EN-only guard, mypy clean repo-wide, 0 warnings; full suite 2425 passed / 120 skipped) | mypy/linters/tests/language discipline (EN-only: Numba degrades silently on non-ASCII) — without a safe base, TZ-02+ refactors are not verifiable |
| 1 | TZ-01 dsl hardening | ✅ (DslValidationError, resolve_history, manifest routing, NaN contract, strict param typing; parsing < 1 ms) | DSL is the core: strategies and RAG-generation both flow through it; contracts must be fixed before clients appear |
| 2 | TZ-06 ai stabilization | ✅ (torch explicit, temporal split, model bundle, predict_p_win, device backends; 68 tests) | tor and validation leak block any model use; order justified in the TZ |
| 3 | TZ-02 strategies + unified OHLC | ✅ (25 tests: unified schema + Strategy + validation + registry + AST + label generator) | Strategy format and data schema — glues ta/dsl/ai; schema conflict blocks everything downstream |
| 4 | TZ-03 ta-dsl provider | ✅ wave 2 (universal mapper `ta/src/registry.py`, 84 indicators in DSL, multi-output, cache-key fix; wave 1 golden anchors; 1975 tests) | Indicators into the DSL; needs the TZ-02 data format |
| 5 | TZ-04 backtest | ✅ core (execution + portfolio + engine + metrics + baseline gate + risk gate; 34 + 12 integration tests) | Honest backtest BEFORE RAG and BEFORE ML inference on real data |
| 6 | TZ-05 inference | ✅ (CLI, pipeline, --ml; manual T-Invest run remains) | Signal script — "backtest on a live tail"; depends on TZ-02/03/04 (strategy format is a stub) |
| 7 | TZ-07 rag | 🔨 core (47 tests; pipeline + pass@1/pass@N metrics) | pass@1 eval needs a live LLM; integration tests need live Qdrant/Ollama |
| 8 | TZ-08 contracts + DI | ✅ (contracts via msgspec; dishka 4 contours; DatabaseProvider; 16 tests) | Module gluing; code must not duplicate strategy models or pull heavy deps |
| 9 | TZ-09 api bridge | ✅ transport core (11 bridge + 14 contract tests; ACL, schema-version, reconnect, heartbeat) | Public contour ↔ local GPU node; protocol is the only boundary |
| 10 | TZ-10 white API | ✅ core (12 REST/store + 10 db + e2e service tests; PG stores + Alembic + DI) | Public service skeleton; async backtest via queue |
| 11 | TZ-11 risk engine | ✅ (22 + 12 integration tests; config-driven, rules registry, strict validation) | "Decisions only by deterministic code" is incomplete without risk management; the invariant-gate blocks live |
| 12 | TZ-12 ta benchmarks | 🔨 runner (2 smoke tests, marker `performance`) | Public measurable proof for README/portfolio |
| 13 | TZ-13 CI | ✅ (lint + mypy + EN-only guard + 9 pytest matrix jobs — main added) | Prevent monorepo regressions |
| 14 | TZ-15 okx venue | ✅ core v1 + ✅ live public market data (onion L1-L4, REST warm-up + WS business stream verified vs the real venue, 39 tests; trading contour closed until the baseline gate) | Second venue; depends on the deterministic path and DI |
> Order deviation: TZ-05 was completed before TZ-02/03/04 (synthetic smoke was acceptable;
> the strategy format in infer stays a stub until TZ-02).

## 3.1. Summary right now

- **Full suite: 2461 passed / 123 skipped / 0 warnings**; ruff and mypy clean repo-wide
  (only accepted tech-debt: docstrings in `ta/src/overlap/mama.py`).
- **Deterministic path complete end-to-end on synthetic data**:
  ta → DSL → signals → **Risk Engine (TZ-11 ✅)** → backtest with reject-audit;
  the DSL manifest now exposes **84 indicators** (TZ-03 wave 2 ✅: universal mapper
  `ta/src/registry.py`, auto-bindings from `*_ind` signatures).
- **Infrastructure**: DI (4 contours), FastStream bridge with ACL, REST, PostgreSQL +
  Alembic, white/local glue via `service.py` — all with e2e tests on an in-memory broker and
  SQLite; **live backends (RabbitMQ, PG, Qdrant, Ollama) have NOT been wired up yet**.

## 3.2. Remaining work order

1. **Local backtest-runner in `main/`** (closes TZ-04 live + TZ-09/TZ-10): cmd.backtest →
   DSL→signals → `run_backtest(risk_config=...)` → evt.report; in parallel add the TZ-04
   msgspec report contracts.
2. **TZ-07 final** — pass@1 eval script (needs a live Ollama), `rag_integration` marker for
   live Qdrant/Ollama (docker compose exists).
3. **TZ-10 finish** — aiogram bot, JWT, live PostgreSQL in CI (service container).
4. **TZ-09 finish** — live RabbitMQ, TLS/tokens, lag metrics.
5. **TZ-04/TZ-06 on real data** — SIV run, model training, baseline gate (opens live),
   OB batching, <5 ms measurement.
6. **TZ-12 final** — reproducible ±10% reruns, TA-Lib optional CI job.
7. **TZ-15 OKX** — implement the spec (adapter, event loop, DI, normalization).

## 4. Cross-cutting principles (mandatory for all TZs)

1. **LLM outside the decision path.** The LLM generates/explains strategies; entry/exit is
   decided by deterministic code. Risk limits are unreachable by the LLM at every level,
   including transport: the TZ-09 queue protocol has no "change limits" command.
2. **One execution engine, three consumers** (ai labels, backtest, live) — TZ-04 §0.
   Three implementations = trade semantics diverge between P(win), backtest and reality.
3. **Unified OHLC schema**: `open, high, low, close, volume` (TZ-02 §3).
4. **Look-ahead invariant**: a function at bar t receives only `[:t+1]`; verified by tests
   that replace "future" bars with garbage (TZ-03 §5, TZ-04 §5).
5. **NaN contract**: warm-up = NotReady (signal False + skip counter), NaN after warm-up =
   data error (TZ-01 §5, TZ-03 §4).
6. **Reproducibility**: seed (numpy/torch/random) + config + git hash in every report.
7. **GPU deps only on the local node** (TZ-09): the public contour requirements have no torch.

## 5. Overall success criteria (from quant_checklist.md)

> ⚠️ **Baseline gate — the main filter.** Comparing the model with simple methods
> (Buy & Hold, logistic regression, RF/XGBoost) is a mandatory gate: without a passed
> comparison, backtest results are not valid, real-data training and the live contour stay
> closed. Details — TZ-04 §4.6.1.

- Profit Factor > 1.5 on out-of-sample with commissions; MaxDD ≤ 20%; Sharpe > 1.0.
- **Gate:** the model beats baselines (logistic regression, RF/XGBoost, Buy & Hold) by
  **> 5–10% on Sharpe or Profit Factor** on aggregate metrics (Accuracy, F1, Profit Factor,
  Sharpe) — otherwise simplify / fall back to a simple model.
- Rerunning with the same seed produces an identical report.
- RAG: ≥ 70% of queries produce valid DSL within ≤ 2 repair iterations (pass@1).
```