# Deterministic Trading Engine

A deterministic algorithmic trading system: trade decisions are made **only by verifiable
code** — a declarative **DSL** → signals → **Risk Engine (TZ-11)**. An ML model only scores
trade probability (`P(win)`), while the LLM/RAG is a supporting strategy-generation layer,
kept **outside** the decision path.

**Core principles:**
- entry/exit decisions are made only by deterministic code (DSL interpreter + execution engine);
- the ML model scores probability — it makes no decisions and has no risk-management access;
- the LLM/RAG is used only to generate/modify strategies and analyze results — outside the execution path;
- the Risk Engine is config-driven (TZ-11): limits are **data** in `configs/risk.yaml`,
  the engine is their interpreter; limits are unreachable by the LLM at every level,
  including transport (the TZ-09 queue protocol physically has no such command).

> The core is the deterministic trading path; RAG is a supporting layer (see TZ-07).

---

## Project status at a glance

- **Deterministic path is complete end-to-end on synthetic data:**
  `ta → DSL → signals → Risk Engine → backtest with reject-audit`.
- **Full suite: 2461 tests passed / 123 skipped / 0 warnings.** ruff & mypy clean
  repo-wide (only accepted tech-debt: docstrings in `ta/src/overlap/mama.py`).
- **Documents in English.** Status markers: ✅ implemented · 🔨 in progress · ⬜ not started
  · ⬜=spec only (see `dev_docs/tz/TZ-00-roadmap.md` and `STATUS.md`).

| Area | Status |
|------|--------|
| `ta/`, `dsl/` — indicators + DSL | ✅ |
| `strategies/` — strategy format + validation | ✅ |
| `backtest/` — execution + portfolio + metrics + baseline-gate validator | ✅ core |
| `risk/` — config-driven risk engine (TZ-11) | ✅ |
| `ai/` — Entry-Exit transformer | ✅ core; first real-data run done — best classifier, edge/gate not yet passed |
| `infer/` — inference CLI | ✅ |
| `rag/` — RAG: docs → DSL | 🔨 core; pass@1 not measured on live LLM |
| `main/` — DI / bridge / REST / PostgreSQL | 🔨 core; no live RabbitMQ/PG/Qdrant |
| `okx/` — OKX venue adapter (TZ-15) | ✅ core + ✅ live public md; no trading |
## Implemented ✅

**1. `ta/` — indicator library (`dte-ta`)**
- NumPy + Numba cores (`@njit`), Polars-compatible, no pandas in computations.
- Groups: `overlap/` (SMA…JMA, SuperTrend, Ichimoku), `momentum/` (RSI, MACD, Stoch…),
  `volatility/` (ATR, BBands), `trend/` (ADX, ZigZag), `statistics/`, `volume/`,
  `candle/` (CDL patterns, Heikin Ashi, Renko, Kagi), `custom/` (OTT, SCRSI, AVS…).
- Causality & NaN contract; benchmarks (TZ-12, n=100 000) committed to README below.
- **Wave 2 (TZ-03) universal mapper** `ta/src/registry.py`: bindings auto-derived from
  `*_ind` signatures → **84 indicators exposed to the DSL**, multi-output
  (`macd/ppo/fisher/brar/kst` named), batched resolve, cache-key covers all params.
  `SKIP`: ichimoku/scrsi/zigzag/tos_stdevall (not engine-usable); `SMOKE_SKIP`: ott
  (numba dispatch). 1975 ta tests.

**2. `dsl/` — trading-conditions DSL (`dte-dsl`)**
- Tokenizer → parser → AST → interpreter (Visitor), sync + async.
- Arithmetic, logic with short-circuit, indicator calls, offsets `close[1]`,
  `rising/falling`, `let` bindings. **No `eval`/`exec`** — arbitrary code not executable.
- Providers: in-process, HTTP (HTTP/2/3); manifests with strict validation,
  `resolve_history`, `DslValidationError` (TZ-01 ✅). 154 tests.

**3. `strategies/` — strategy layer (`dte-strategies`, TZ-02)**
- Unified OHLC schema (`open/high/low/close/volume`, legacy mapping), `Strategy`+`Metrics`
  frozen dataclasses, `validate_strategy(s, manifest)`, `StrategyRegistry`
  (JSON in `strategies/data/`, auto-pinned `manifest_hash`), `indicators_used(expr)` via AST.
- Label generator bridges strategy signals → outcomes on the TZ-04 execution engine
  (look-ahead invariant green). 25 tests.

**4. `backtest/` — backtest module (`dte-backtest`, TZ-04)**
- `execution.py`: fill at `open[t+1]`, commission/slippage, pessimistic SL-first, ATR-dynamic TP/SL.
- `portfolio.py`: TP1 (50%) + TP2, trailing callback, `max_bars_hold`, equity + unrealized PnL.
- `engine.py`: bar-by-bar loop, look-ahead safe, reproducibility.
- `metrics.py`: PF, annual Sharpe, MaxDD, win_rate, avg_hold.
- `validation.py`: temporal split, walk-forward folds, baseline-gate
  (pass/fail/simplify), report validator (requires B&H, LR, RF, XGBoost + gate status).
- **Risk gate (wave 2, TZ-11 §4.5)**: `run_backtest(risk_config=...)` runs every entry
  through `risk.engine.check()`; rejects in `metrics.risk_rejects`
  (bar_idx, rule, reason, params snapshot). 34 + 12 integration tests.
- **Not implemented**: msgspec report contracts, SIV integration run, live contour.

**5. `risk/` — deterministic risk engine (`dte-risk`, TZ-11)**
- Config-driven: rules/limits are **data** (`configs/risk.yaml`), engine is the interpreter,
  code holds only safety invariants.
- Typed config (frozen dataclass) with strict validation — unknown key/type → error.
- Rules registry (v1): `require_stop_loss`, `position_limit`, `max_positions`,
  `daily_loss_limit`, `drawdown_stop` (with `pause_bars`); params schemas validated.
- `check(signal, state, cfg) -> Decision{approve, reason, size, rule}` — pure function.
- Safety invariants (code + tests, not config): no approve without all active rules;
  no "change limits" command in the TZ-09 protocol; `size=0` on empty capital; causal ATR.
- 22 unit + 12 backtest-integration tests.
**6. `ai/` — Entry-Exit Transformer (`dte-ai`, TZ-06 ✅ core)**
- Predicts: action (hold/entry/exit), outcome (win/loss + R-multiple), patterns —
  from a candle + order-block window.
- Supervised + self-training (pseudo-labelling), causal TP/SL from ATR(t-1),
  chronological train/val split (no validation leak), model bundle +
  inference contract `predict_p_win` (TZ-06 ✅).
- YAML config (`configs/ai.yaml`), reproducibility (seed). 71 tests.
- **First real-data run (OKX, 7 assets × 4 TF — `dev_docs/ai_baseline_report.md`):**
  the transformer is the **best classifier** of all tested models — action acc
  **0.719** / macro-F1 **0.710** vs random floor 0.50/0.49, ahead of RF (0.673),
  MLP (0.652), LightGBM/XGBoost (0.703) and linear baselines (0.58–0.59).
- **Not achieved yet: trading edge** — out-of-sample with costs every model loses
  (transformer −89.8 %/slice vs random floor −90.7); the baseline gate
  (TZ-04 §4.6.1, > 5–10% Sharpe/PF over the best simple baseline) is **not passed**.
  Improvement criteria and the next-attempt list (confidence thresholds instead of
  argmax, cost-sensitivity study, TP/SL-vs-hold horizon alignment, **DSL-driven
  indicator-config search**) live in `dev_docs/ai_baseline_report.md`.
  OB-encoder batching and <5 ms measurement remain.

**7. `infer/` — inference CLI (`dte-infer`, TZ-05 ✅)**
- CLI: candles (synthetic/parquet/yfinance/tinvest) → DSL signals → `--ml` filter by
  `P(win)`. Warm 5000-bars × 2 expressions ≈ 180 ms (target < 1 s).
- **Not implemented**: manual run on real T-Invest candles (needs `INVEST_TOKEN`).

**8. `rag/` — applied RAG contour (`dte-rag`, TZ-07 🔨 core)**
- LLM layer: per-request provider/model routing (Ollama + OpenAI-compatible).
- ingestion (`chunk_markdown`, white-listed docs), vectorstore (InMemory + Qdrant),
  embeddings (Mock + Ollama bge-m3), retrieval, `RAGPipeline` with pass@1/pass@N
  metrics (TZ-07). 47 tests.
- Safe by construction: risk limits have no ingestion route (TZ-00 cross-cutting #1).
- **Not implemented**: pass@1 evaluation on a live LLM; live Qdrant/Ollama integration
  (marker `rag_integration`).

**9. `main/` — entry point (`dte-main`, TZ-08/09/10 core ✅)**
- DI (dishka, 4 contours: backtest/inference/rag/api) with LLM/Embeddings/Qdrant/
  model-bundle/PostgreSQL providers (TZ-08 ✅).
- FastStream bridge WhiteBridge/LocalBridge: ACL, schema-version tolerance,
  reconnect with backoff, heartbeat (TZ-09 core ✅).
- REST on aiohttp (ingest/strategies/backtests/signals/rag) + PostgreSQL stores
  and Alembic migrations (TZ-10 core ✅).
- `main/src/service.py` glue: `make_pg_white_api`, `candle_saver` (md.ohlcv → PG via
  `asyncio.to_thread`), `make_local_bridge`/`make_white_bridge` (cmd.backtest → injected
  runner; default stub never stays silent). E2E tests on in-memory broker + SQLite.
- **Not implemented**: real local backtest runner (DSL→signals→backtest+risk);
  aiogram bot + JWT; live RabbitMQ/PostgreSQL/Qdrant/Ollama; Alembic glue in server.

**10. `okx/` — OKX venue adapter + event loop (`dte-okx`, TZ-15 ✅ core + live public md)**
- Onion architecture: L1 `domain.py`/`ports.py` (OkxEvent, OrderRequest,
  InstrumentSpec, 9 Protocol ports), L2 `events.py` (per-instrument serial
  event loop), `executor.py`, `collector.py` (live WS stream + REST warm-up);
  L3 `okx_client.py` (signing, posMode startup check), `mapping.py`
  (payload → canon: ts ms bar-open, confirm gate, SPOT/SWAP volume
  semantics, lotSz/tickSz rounding, BAR_MAP); L4 `http_impl.py` (niquests),
  `ws_impl.py` (websockets).
- **Live public market data — verified against the real venue**: REST
  `GET /api/v5/market/candles` warm-up + WS `candle{bar}` stream on
  `wss://ws.okx.com:8443/ws/v5/business` (candle channels are served by the
  *business* endpoint, not `/public`); only `confirm=1` bars reach md.ohlcv.
  No API keys needed. Smoke tests: `OKX_LIVE_SMOKE=1 pytest okx/tests -m integration`.
- dishka assembly `okx/src/di.py` (`make_okx_container`, fakes-injectable).
- Invariants in code: order only on confirmed candle; every order through
  RiskGate; deterministic `clOrdId` per (inst, ts, side) → replay-safe;
  reconcile = source of truth after WS break.
- **Not implemented**: private WS channels (orders/positions/account) + order
  placement (trading contour closed until baseline gate), algo SL/TP attach,
  PG-backed `InstrumentMap`/fill journal (TZ-10).
## Not implemented ⬜ / remaining

1. **Live production backends never wired**: everything runs on in-memory
   RabbitMQ (TestRabbitBroker), SQLite, and mock/Ollama-via-mocks. `docker compose up`
   with real RabbitMQ/PG/Qdrant/Ollama is untested.
2. **Local backtest runner in `main/`** — cmd.backtest returns a stub "failed: no runner".
3. **Model not trained** — no artifacts; `--ml` unavailable without a bundle.
   **Baseline gate not passed** — live contour stays closed until then (TZ-04 §4.6.1, TZ-00 §5).
4. **pass@1 ≥ 70%** (RAG success criterion) — metric implemented, not measured on a live LLM.
5. **OKX trading contour (TZ-15)** — public market data is live (REST + WS, verified
   against the real venue); private channels, order placement, algo SL/TP and
   PG `InstrumentMap` — after the baseline gate.
6. Manual T-Invest run (TZ-05), aiogram bot, JWT, TLS/tokens, lag metrics (TZ-09/10) — spec'd.
7. **AI remaining**: OB-encoder batching, <5 ms measurement, training on real data, SIV run.
8. **TZ-12 final**: reproducible ±10% reruns, TA-Lib optional CI job; only accepted
   ruff tech-debt remains (docstrings in `ta/src/overlap/mama.py`).

The authoritative upcoming order is in `dev_docs/tz/TZ-00-roadmap.md` §3.2.

---

## Architecture

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
```

Decision path:

```
DSL signals (+P(win)) → Risk Engine (check) → Order (size, SL/TP) → execution (TZ-04 engine)
                                                                      ▲
                                          [LLM/RAG] → strategy generation/explanation
                                                       (outside the decision path)
```

The LLM/RAG runs **in parallel**, not inside the decision path.

---

## Run

```bash
uv sync --all-packages
docker compose up -d          # postgres, redis, rabbitmq, qdrant, ollama
uv run --package dte-main alembic upgrade head   # DB migrations
uv run --package dte-dsl pytest dsl/tests        # DSL tests
uv run --package dte-ta pytest ta/tests          # indicator tests
uv run --package dte-ai pytest ai/tests          # ai tests
uv run --package dte-rag pytest rag/tests        # LLM layer tests
uv run --package dte-infer pytest infer/tests    # inference smoke tests
uv run --package dte-strategies pytest strategies/tests  # strategy tests
uv run pytest -m dsl                            # only dte-dsl tests (service markers)
uv run --package dte-infer python -m infer.cli --help   # inference
```

## Technologies

Python ≥ 3.12 · uv (workspaces) · NumPy/Numba · Polars · TA-Lib · PyTorch ·
LlamaIndex + Ollama · Qdrant · PostgreSQL + SQLAlchemy + Alembic · Redis · RabbitMQ
(FastStream) · aiogram · dishka. OKX adapter (TZ-15 core): msgspec · pyyaml · dishka;
live transports (websockets/niquests) pending.

### `ta/` indicator benchmarks (TZ-12, n=100 000)

Numba cores vs baselines; cold = first call (JIT), warm = best-of-3, fixed seed.
TA-Lib not installed in the default env (n/a).

| module | indicator | impl | ms | speedup |
|---|---|---|---:|---:|
| overlap | sma | numba (cold) | 1.16 | - |
| overlap | sma | numba (warm) | 0.62 | 1.0x |
| overlap | sma | pandas | 1.04 | 1.7x |
| overlap | ema | numba (warm) | 0.86 | 1.0x |
| overlap | ema | pandas | 0.57 | 0.7x |
| momentum | rsi | numba (warm) | 3.09 | 1.0x |
| momentum | rsi | numpy | 3.14 | 1.0x |
| momentum | macd | numba (warm) | 3.16 | 1.0x |
| momentum | macd | numpy | 3.07 | 1.0x |
| volatility | atr | numba (warm) | 2.05 | 1.0x |
| volatility | atr | pandas | 13.09 | 6.4x |
| candle | cdl_engulfing | numba (warm) | 1.18 | 1.0x |
| custom | scrsi | numba (warm) | 4.09 | 1.0x |
| custom | scrsi | numpy | 3.87 | 0.9x |

Reproduce: `uv run python -m ta.benchmarks.run --n 100000 --save`.

## Code quality

Ruff (+format) is the single linter (flake8/isort eliminated in TZ-14), mypy is tightened
in stages (strict first for ai/infer), 79-char line length, Python 3.12.
**English only in code/identifiers/docstrings/comments** (Numba/toolchain degrade on
non-ASCII in `.py`); Russian stays in `*.md` docs only. Test convention:
`dev_docs/testing_convention.md`. CI: TZ-13.

## Limitations (unchanged principles)

- The LLM does not make trading decisions.
- The LLM does not change risk parameters (no such command in the TZ-09 queue protocol).
- The LLM does not generate trade-execution code.
- All decisions are made by code only.

## Roadmap

Current order: `dev_docs/tz/TZ-00-roadmap.md` §3.2. In brief:

- [x] TZ-14 quality baseline (ruff/mypy/en-only/pytest matrix)
- [x] TZ-01 DSL hardening · TZ-06 ai stabilization · TZ-05 inference
- [x] TZ-02 strategies + unified OHLC
- [x] TZ-03 ta-dsl provider (wave 2: mapper, 84 indicators in DSL)
- [x] TZ-04 backtest core (execution + portfolio + engine + metrics + baseline gate)
- [x] TZ-11 Risk Engine (config-driven core)
- [ ] TZ-09/10 live bridge + white API (real runner, JWT, aiogram)
- [ ] TZ-07 pass@1 eval + live Ollama/Qdrant integration
- [ ] TZ-04/TZ-06 real-data SIV run + model training + baseline gate
- [ ] TZ-08 DB glue in server · TZ-12 benchmark reruns ±10%
- [x] TZ-15 OKX venue adapter — core v1 (event loop, mapping, DI) + live public
  market data (REST warm-up + WS business stream, verified vs real venue);
  trading contour (private channels, order placement) stays closed until the
  baseline gate
| `okx/` — OKX venue adapter + event loop (TZ-15) | ⬜ spec only |