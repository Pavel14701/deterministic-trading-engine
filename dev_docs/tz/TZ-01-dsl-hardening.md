# TZ-01. DSL hardening (priority 1)

> **Status: ✅ done** — `DslValidationError`, `resolve_history`/`resolve_history_async`,
> manifest routing, NaN contract, strict param typing (verified in code); parsing < 1 ms (tests).

## 1. Context

The DSL (`dsl/`, ~2800 lines: tokenizer → parser → AST → interpreter → context → providers) is
the most mature module and the system core: strategies and RAG generation both flow through it.
The audit found problems that cannot be fixed after clients (backtest, RAG, inference) appear,
because all of them bind to the current contracts.

## 2. Problems and rationale

### 2.1. Provider routing by manifest (instead of getattr)
**Now:** `Context.get_value` uses `if getattr(provider, 'resolve'):` — a method is always truthy;
it checks attribute presence, not "does this provider know this indicator". The first provider
swallows any request; fallback only works via exception.
**Why change:** there will be ≥2 providers (ta indicators + price data). Selection:
`indicator in provider.manifest.indicators` — O(1), deterministic, no exception-based control flow.
**Rejected alternative** ("keep as is, search by ProviderError"): cannot distinguish "unknown
indicator" from "data error at this bar".

### 2.2. Unified exception contract
**Now:** `Context._validate` throws a bare `ValueError` though a `DSLError` hierarchy exists.
**Why change:** the RAG repair loop (TZ-07) catches DSL errors by one contract and returns the
message to the model. A leaky contract = some errors go unhandled. `DslValidationError(DSLError)`
with human-readable text from `ManifestValidator.validate()` (ready messages `Unknown indicator: X`,
`Invalid parameter 'Y'` — almost perfect repair hints).

### 2.3. Interpreter re-entrancy
**Now:** `Interpreter._locals` is mutable state shared across all visit().
**Why change:** in async mode, evaluating one strategy over several bars/instruments in parallel
races let bindings. `_locals` moves into the local visit-stack state. Rejected alternative
"document one-visit-per-thread": it surfaces as rare wrong signals — the worst bug class in trading.

### 2.4. resolve_history as a first-class provider method
**Now:** the `get_history` fallback makes O(n) separate `get_value` calls with re-validation;
`rising(close, 50)` = 50 full resolves.
**Why change:** backtest (TZ-04) makes millions of history lookups. Add
`resolve_history(ind, params, attrs, n)` to the abstract `IndicatorProvider`; InProcess overrides
with a cache slice, HTTP with one batch request.

### 2.5. NaN contract (cross-cutting principle #5)
**Now:** `rising/falling` silently return False on insufficient history; NaN comparisons give
False. Behavior is sensible but unspecified → "the strategy does not trade" for the first N bars
goes unnoticed.
**Decision:** warm-up (< min_bars) = `NotReady` (False + skip counter in the report); NaN after
warm-up = `EvaluationError`. Documented in dsl/docs as part of semantics — otherwise RAG explains
signals wrongly.

### 2.6. Strict parameter typing
**Now:** `validate_parameter` silently passes a non-numeric value for integer/float types.
**Why change:** RAG generation will feed malformed params; silent pass = NaN somewhere in
computations instead of a clear validation error.

### 2.7. Legacy docs
`ai/docs/README.md` describes a nonexistent Lark parser (`dsl/grammar.lark`) and `trading.*`
packages; the import in `ai/src/quickstart.py` is broken. Fixed in TZ-06, recorded here: RAG
ingestion must not index a fabricated spec.

## 3. Requirements

1. Provider routing by manifest (§2.1).
2. `DslValidationError(DSLError)` instead of ValueError; keep error texts (RAG parses them).
3. `_locals` local to the visit stack; thread-safety documented.
4. `resolve_history` in `IndicatorProvider` + default loop implementation + overrides.
5. NaN contract §2.5, unified with TZ-03 §4.
6. Strict param typing (§2.6).
7. Public API (`evaluate_dsl`, `parse`, `Interpreter.visit`) keeps signatures.

## 4. Acceptance criteria

- All existing tests green without semantics change.
- New tests: routing (2 providers, overlapping manifests), exception contract,
  parallel async evaluation with let (no race), warm-up/NaN, resolve_history == loop over resolve.
- Parsing a typical expression (< 50 chars) < 1 ms (requirement from dsl_requires.md,
  previously unverified).