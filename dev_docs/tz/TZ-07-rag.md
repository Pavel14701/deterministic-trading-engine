# TZ-07. RAG contour (ingest, retrieval, DSL generation)

> **Status: 🔨 RAG core ready (47 tests green).**
> ✅ LLM layer (per-request routing, 15 tests).
> ✅ ingestion.py: chunk_markdown (by headings, max_chunk_chars), ingest_docs (white-list),
> render_manifest_text (for the prompt), strategy_to_case (for retrieval).
> ✅ generation.py: GENERATION_PROMPT (manifest + docs + few-shot + task),
> REPAIR_PROMPT, generate_dsl() with repair-loop ≤ 2, markdown fence stripping,
> mocked LLM transport for tests.
> ✅ wave 2: vectorstore.py (VectorStore protocol, InMemoryVectorStore with cosine +
> payload filter + idempotent upsert, QdrantVectorStore with lazy qdrant-client import,
> query_points API); embeddings.py (EmbeddingFunction protocol, MockEmbedding — deterministic
> sha256 hash, unit norm, dim=64; OllamaEmbedding — bge-m3, dim=1024); retrieval.py (Retriever,
> collections dsl_docs/strategy_cases); pipeline.py (RAGPipeline: ingest_docs/ingest_strategies/
> generate with retrieval→generate_dsl, PipelineMetrics with pass@1/pass@N/failed/avg_iterations,
> QueryLog).
> ⬜ pass@1 evaluation script over a query-set (needs a live LLM).
> ⬜ rag_integration marker: live Qdrant/Ollama (skip without infra).

## 1. Context

The infrastructure is chosen (Qdrant, Ollama, LlamaIndex, sentence-transformers — in
pyproject/compose); the application layer is missing. RAG exists for exactly one purpose: feed the
LLM relevant context (DSL spec, indicator docs, similar strategies, backtests) so the model does
not hallucinate nonexistent indicators. Risk limits never enter the index by construction
(cross-cutting principle #1).

## 2. Why this way

### 2.1. The "deterministic manifest + retrieval + few-shot" hybrid is the main lever
- **The manifest is rendered into the prompt programmatically** (`Manifest.to_dict()` → text),
  not embedded: vectorizing `{"type": "integer", "min": 2}` is meaningless and lies in retrieval.
  It answers for syntactic correctness.
- **Retrieval over `dsl/docs/*.md` and `dev_docs/`** — for semantics ("how to write trend
  conditions"). Chunks by heading, 400–800 tokens, ~15% overlap.
- **Few-shot precedents**: "find 2–3 similar validated strategies and put them in the prompt" —
  the most effective way to make an 8B model write valid DSL. One strategy = one point, no chunking.

### 2.2. Two Qdrant collections, not one
`dsl_docs` (static-doc chunks, payload `{source, heading, doc_type, lang}`) and `strategy_cases`
(one strategy = one point, payload `{dsl_entry, dsl_exit, indicators_used, metrics, manifest_hash}`).
**Why:** fundamentally different data with different lifecycles (docs update by git hash;
strategies — by backtest results) and different search (semantic vs precedent).

### 2.3. `indicators_used` — AST walk, not regex
AST serialization (`to_dict`) already exists. Regex over DSL text misses let bindings and aliases.

### 2.4. White-list ingestion — enforcement, not a request
The ingest pipeline accepts an explicit path config (`dsl/docs/**`, `dev_docs/**` minus
risk docs). Risk limits cannot enter the collection because there is no ingest route for them.
**Why not "ask the LLM not to use":** the only architectural defense is the physical absence of
the data in the context.

### 2.5. Repair loop through our own parser
LLM output is machine-checkable: parse → ManifestValidator → on error, the error text + manifest
are returned to the model (max 2 iterations; then `status: failed`). **Why 2, not 5:** after 2
iterations an 8B model starts degrading and "fixing" working code. Result contract:
`{status, dsl, errors[], iterations, chunks_used[]}` — failed does not leave the rag layer.

### 2.6. Embeddings via Ollama, not sentence-transformers in-process
sentence-transformers pulls PyTorch (~1–2 GB RAM) into the process. Fine for a local GPU node,
but the correct approach is a single Ollama embedding point (`/api/embeddings`) — the model
(bge-m3 or multilingual) in a container. **Language nuance:** queries will be Russian, `dsl/docs`
English; use a multilingual model and/or English annotations on Russian chunks at ingest.

### 2.7. Idempotent ingest
Repeated runs do not duplicate points: key = hash(chunk) / strategy.id; stale points with an old
git hash are deleted.

## 3. Requirements

0. **LLM layer with per-request routing — ✅ done** (`rag/llm.py`): `LLM_PROVIDER` from env sets
   only the **default** provider for the worker; each request can override both the provider
   (`router.complete(prompt, provider=...)`) and the model (`CompletionOptions(model=...)`). For
   Ollama and OpenAI-compatible backends `model` is a request field, so one worker serves multiple
   models simultaneously — multi-tenant scenarios supported. Transports are injected → tests run
   without network (11 tests `rag/tests/test_llm.py`). The project is licensed **MIT** (`LICENSE`,
   `license`/`license-files` in pyproject).
1. `rag/ingestion`: chunker + white-list paths + manifest render + two collections.
2. `rag/retrieval`: docs top-k (5–8) + cases top-k (2–3, filtered by the current manifest_hash
   from TZ-02).
3. `rag/generation`: prompt templates (brief DSL grammar, ban on inventing indicators,
   temperature ≤ 0.3) → Ollama DeepSeek-R1:8b → validate_strategy → repair-loop ≤ 2.
4. pass@1 metric (share OK on the first attempt) with query/chunks/iterations/status logging —
   simultaneously a retrieval-quality metric (repaired queries reference indicators whose docs
   were absent from context → retrieval is at fault).
5. Cross-check: before indexing `ai/docs`, sync with reality (TZ-06 §2.7), otherwise a fabricated
   spec gets indexed.

## 4. Acceptance criteria

- Ingest is idempotent (rerun does not duplicate points).
- For "oversold with trend confirmation" the context contains the RSI/rising docs.
- ≥ 70% of queries from a reference set of 10 phrases → valid DSL within ≤ 2 iterations.
- Collections contain no chunks with risk limits (white-list test).