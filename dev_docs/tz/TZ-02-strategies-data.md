# TZ-02. Strategy layer and unified data schema

> **Status: ✅ core done** (unified schema + Strategy + validation + registry + AST + label generator).
> Implemented: unified OHLC schema (`open/high/low/close`) with legacy `*__price` mapping in
> `PriceDataFramePolars`; `Strategy` + `Metrics` (frozen dataclass);
> `validate_strategy(s, manifest)` = parse + indicator-manifest check;
> `StrategyRegistry` (JSON files in `strategies/data/`, auto-pinned manifest_hash);
> `indicators_used(expr)` via recursive AST to_dict walk;
> 25 tests green. Label generator implemented: labels.py -> generate_labels() ->
> action/outcome arrays for ai/src/dataset.py. Look-ahead invariant green.

## 1. Context

`strategies/` is a skeleton: `PriceDataFramePolars` + indicator functions. No strategy format,
registry or validation. A data-schema conflict was found at the same time: `PriceDataFramePolars`
requires `open_price, close_price, high_price, low_price`, while `ai/` and the polars `ta/`
functions use `open, high, low, close`. Two canonical OHLC schemas in one project = an adapter at
every seam, and one of them will eventually miss.

## 2. Why this way

### 2.1. Unified OHLC schema: `open, high, low, close, volume`
**Why these names:** (a) `ai/` is fully written for them (features, quickstart, contract);
(b) `ta` functions `*_polars` default to `close_col='close'`; (c) `dev_docs/api.md` and exchanges
use short names. Renaming `PriceDataFramePolars` is cheaper than adapters in all consumers.
**Rejected alternative** (adapter layer): three consumers × N modules = O(N) error points vs one.

### 2.2. Strategy format with manifest_hash
```python
@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    description: str
    dsl_entry: str            # DSL expression for entry
    dsl_exit: str | None      # DSL expression for exit (None = SL/TP only)
    params: dict              # constants for the provider/filters
    manifest_hash: str        # hash of the manifest it was validated against
    created_at: datetime
    metrics: Metrics | None   # filled by backtest
```
**Why manifest_hash is mandatory:** a strategy references indicators of a specific manifest
version. When new indicators are added, old strategies in RAG few-shot examples may feed the LLM a
nonexistent schema. A payload filter by the current hash solves this at retrieval (TZ-07).

### 2.3. Validation is the only entrance to the registry
`validate_strategy(s, manifest) -> list[str]` = parse of both expressions + ManifestValidator.
Nothing is saved without passing. **Why:** a DSL is a machine-checkable artifact; an invalid
strategy breaks backtest, RAG examples and inference at once.

### 2.4. The label generator lives here
`strategies/src/application/labels.py`: "DSL signal → trade → outcome" with fill logic from
`ai/src/features.py` (entry at open[i+1], commission, slippage), but on top of the TZ-04 execution
engine (see TZ-04 §0). **Why:** current ai/ labels describe only order-block setups — P(win) learns
the outcomes of someone else's trading. A "strategy signal → outcome" bridge is needed.

## 3. Requirements

1. Rename `PriceDataFramePolars` columns to the unified schema (§2.1), update consumers.
2. `Strategy` + `validate_strategy` + registry (JSON files in `strategies/data/`; migration to
   PostgreSQL via Alembic later, when the main service exists).
3. Label generator (§2.4) on the TZ-04 engine; result contract = `action/outcome` arrays
   compatible with `ai/src/dataset.py`.
4. AST metadata export: list of used indicators via AST walk (`to_dict` already exists) — for
   ai/ features and RAG payload.

## 4. Acceptance criteria

- Reference strategy (`let r = rsi(period=14) in r.value < 30 and rising(close, 5)`) goes through
  validate → backtest smoke on synthetic → correct action/outcome arrays.
- Label look-ahead invariant: a label at bar t does not change when bars > t are replaced.
- `uv run pytest strategies` green.