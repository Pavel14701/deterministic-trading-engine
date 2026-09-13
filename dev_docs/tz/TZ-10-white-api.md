# TZ-10. White API: public service skeleton

> **Status: 🔨 core + PostgreSQL ready (12 REST/store tests + 10 db tests).**
> ✅ main/src/api.py: WhiteAPI — CandleStore (idempotent ingest by (inst_id, ts), a duplicate
> does not duplicate — test), JobStore (202 + job_id pattern), SignalStore (latest N),
> ACL check on submit_backtest.
> ✅ main/src/rest.py: REST per the §2.2 map on aiohttp (no new deps — aiohttp comes with aiogram):
> POST /ingest/candles, GET /strategies, GET /strategies/{id}, POST /backtests (202),
> GET /backtests/{job_id}, GET /signals?ticker=, POST /rag/generate (503 without the rag contour).
> Input validation via msgspec structures from contracts/, 400 on broken JSON.
> ✅ wave 2: PostgreSQL layer — main/src/db.py (SQLAlchemy 2.0 models candles/strategies/
> backtest_jobs/signals, portable schema: JSON in TEXT, sqlite for tests), main/src/pgstores.py
> (PgCandleStore/PgJobStore/PgSignalStore — same interfaces as in-memory; WhiteAPI accepts any
> implementation), Alembic: migrations/env.py (DATABASE_URL > alembic.ini, psycopg driver) +
> 0001_initial (4 tables + 2 indexes; upgrade/downgrade tested on sqlite). DI:
> DatabaseProvider/DatabasePort in the api contour (no DATABASE_URL → sessions=None →
> in-memory fallback).
> ✅ wave 2 (glue): main/src/service.py — make_pg_white_api (WhiteAPI over three PG stores),
> candle_saver (md.ohlcv → PG, asyncio.to_thread), make_local_bridge/make_white_bridge
> (cmd.backtest → injected runner, default a stub with a failed report, never silent); e2e tests
> over TestRabbitBroker: ohlcv → PG idempotent, cmd → evt.report → PG job completed.
> ⬜ Real local runner (DSL→signals→backtest+risk) for cmd.backtest.
> ⬜ aiogram bot over the same contracts; JWT auth.
> ⬜ Live PostgreSQL in CI (service container) for pgstores.

## 1. Context

`main/src` is currently a T-Invest script. Needed: a public-contour skeleton — exchange-data
ingest + REST for web and the aiogram bot. It does not host GPU/ML — only transport and storage.

## 2. Why this way

### 2.1. FastStream as the base
FastStream (with RabbitMQ) is already a dependency — the same one used in TZ-09; queue ingest
handlers and publish go through one framework. **Rejected alternatives:** bare aio-pika
(boilerplate), a hand-written asyncio loop (no retry/ack/serialization).

### 2.2. Endpoint map (v1)
```
POST /ingest/candles        # exchange data ingest (or internal: consume md.* directly)
GET  /strategies            # strategy registry (read-only)
GET  /strategies/{id}       # + DSL text, AST (JSON), metrics
POST /backtests             # backtest request → cmd.backtest, 202 + job_id
GET  /backtests/{job_id}    # status/report from evt.report
GET  /signals?ticker=...    # latest signals + P(win)
POST /rag/generate          # RAG DSL generation (validation inside the rag contour)
POST /telegram/webhook      # aiogram
```
**Why asynchronous backtest (202 + job):** it runs on the local via a queue; synchronous HTTP for
minute-long work is an anti-pattern.

### 2.3. What is absent from the API and why
- No endpoints to change risk limits, positions, or execute orders — they do not exist in the
  queue protocol (TZ-09 §2.3), so they cannot exist here.
- No direct Qdrant/Ollama access — only through the local rag contour.
- ML training is launched only by the cmd.train command (ACL); statuses via evt.report.

### 2.4. Storage
PostgreSQL (already in compose, Alembic configured): strategies, backtest reports, signals, jobs.
Market data also in PG (timescale-compatible schema later; first a simple candles table with a
unique index (ticker, ts) — ingest idempotency).

### 2.5. Authentication
Web/bot — JWT against the white API; a service token for ingest from exchange connectors.

## 3. Requirements

1. FastStream app skeleton: consumers md.* → write to PG, publishers cmd.*.
2. REST per the §2.2 map (FastAPI on top if needed; first FastStream + minimal HTTP).
3. aiogram bot: the same data through the same contracts (not separate logic).
4. Alembic migrations for tables strategies/backtest_jobs/signals/candles.
5. Input validation via msgspec structures from contracts/ (TZ-08).

## 4. Acceptance criteria

- Ingest: idempotent candle write (a duplicate does not duplicate), retry-safe.
- POST /backtests → cmd.backtest → (mock local) → evt.report → GET returns the report.
- Response schemas fully from contracts/, no local duplicates.