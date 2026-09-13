# TZ-08. Shared contracts and DI (contracts/ + dishka)

> **Status: 🔨 DI fully assembled (16 tests green).**
> Implemented: AppConfig (frozen, from_env: database/rabbitmq/ollama/qdrant/
> model_bundle/llm_model), ContourConfig + CONTOURS registry, dishka providers,
> build_container() for 4 contours (backtest/inference/rag/api).
> ✅ wave 2: rag providers — LLMProviderDishka (OllamaProvider), EmbeddingProvider
> (OllamaEmbedding bge-m3), VectorStoreProvider (QdrantVectorStore, lazy client);
> ModelBundleProvider (MODEL_BUNDLE_PATH; no path → bundle=None, no torch import);
> typed DI keys LLMPort/EmbeddingsPort/VectorStorePort (Protocol) + ModelBundlePort. The api
> contour does not pull GPU/rag deps (test).
> ✅ DatabaseProvider (wave 2.1): DatabasePort with a sessionmaker from DATABASE_URL
> (psycopg); no URL → None → in-memory fallback. PostgreSQL provider closed.
> Remaining: Alembic glue with the service (TZ-10, migrations ready).

## 1. Context

By the time of gluing, modules depend on each other: backtest → strategies → dsl → ta,
rag → dsl + strategies, ai → shared data. Without a dedicated contracts package, dependencies
become transitive and fragile (an edit to dsl breaks ai through a chain).

## 2. Why this way

### 2.1. The `contracts/` package — dependencies only on it
Shared types: `Strategy`, `Signal`, `ValidationResult`, `ManifestHash`, `OHLCVFrame`
(unified TZ-02 schema), `ModelBundle`, `PredictionContract`, `BacktestReport`.
**Why dataclasses/msgspec rather than private classes per module:** serialization across the
white API ↔ local boundary (TZ-09) requires identical structures on both sides; msgspec is
declared in api.md and is 5–10× faster than pydantic. Starting with dataclass + conversion is
acceptable.

### 2.2. dishka as DI
dishka is already a dependency. Providers: `Context` (dsl), `TaProvider`, `QdrantClient`,
`OllamaClient`, model + bundle, DB connections. **Why not a manual singleton module:** different
contours (backtest, inference, RAG) require different dependency graphs from the same components;
dishka gives scopes without boilerplate.

### 2.3. Configuration
Extend `main/src/config.py`: env vars for all external deps (DB_*, REDIS_*, MQ_* already in
compose; add OLLAMA_HOST, QDRANT_URL, RAG_* params, MODEL_BUNDLE_PATH). One config source —
otherwise with two contours (white/local) configs drift across modules.

## 3. Requirements

1. The `contracts/` package (or `common/contracts`) with the types above; modules depend only on it.
2. dishka DI providers for all external components; contours: backtest, inference, rag, api.
3. Unified env config (§2.3), validated at startup.
4. No business logic in contracts/ — only types and (at most) structure validation.

## 4. Acceptance criteria

- Building the dependency graph for each contour in a test (no I/O, mocks).
- `import contracts` does not pull torch/qdrant (checked by import time / optional deps).