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