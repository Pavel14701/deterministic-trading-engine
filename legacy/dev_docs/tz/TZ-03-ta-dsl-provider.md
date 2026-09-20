# TZ-03. TaProvider: exposing ta through the DSL

> **Status: ✅ done (wave 1 + wave 2).**
> Wave 1: `IndicatorBinding` + golden-anchor registry (ema, sma, rsi, atr, ...); `build_manifest()`;
> `TaProvider(IndicatorProvider)`: compute-once cache, DSL-offset = cache index,
> `WarmupNotReady` contract, look-ahead invariant, performance < 1 s / 5000 bars.
> Wave 2 (✅): universal mapper `ta/src/registry.py` — auto-bindings from `*_ind` signatures,
> **84 indicators in the manifest/DSL**, multi-output (NAMED_OUTPUTS: macd/ppo/fisher/brar/kst),
> cache-key fix (covers all params), 1975 ta tests (ruff 0, mypy 0). SMOKE_SKIP: ott
> (numba dispatch); SKIP: ichimoku/scrsi/zigzag/tos_stdevall (not engine-usable).

## 1. Context

The `ta` contract is uniform: every module has a triplet `x_numpy / x_ind / x_polars`;
`x_ind` accepts `np.ndarray | pl.Series`; common params `offset, fillna, nan_policy, trim`;
IEEE 754 discipline (Inf→NaN, NaN propagates); TA-Lib only on exact semantics match. Examples by
group: `rsi_ind(close, length, ...)`, `atr_ind(high, low, close, length, mamode, ...)`,
`adx_ind` (multi-output), `entropy_ind`, `vwma_ind(close, volume, ...)`, `ott_ind` → tuple of 5
arrays (ma, long_stop, short_stop, **direction**, ott).

The DSL resolver, however, expects `(indicator, params, attributes, offset) -> float`. The task is
a bridge without the four error classes (T1–T4 below).

## 2. Why this way

### T1. Offset semantics — a false friend
In ta, `offset` shifts the output series (for plotting). DSL `rsi.value[3]` means "3 bars back".
**Rule: DSL-offset is never passed to ta** — implemented as cache indexing `arr[t - offset]`.
Otherwise signals silently shift. Rejected alternative (using ta-offset "because convenient")
creates an implicit dependency between two different meanings of the same word.

### T2. Compute-once + cache (no per-bar recompute)
A naive resolve recomputing RSI each bar is O(n²) on backtest.
**Model:** compute the series once over the available slice → cache by key
`(dsl_name, frozenset(params.items()), slice_end)` → `resolve(offset)` = O(1),
`resolve_history(n)` = cache slice. Numba cores already `cache=True`; a full 5000-bar series
recompute is milliseconds — but not 5000 times. In live, the cache invalidates on a new bar.

### T3. Multi-output via IndicatorBinding
DSL attributes (`rsi.value`, `ott.direction`, adx/plus_di/minus_di) need an explicit
"attribute → output" map. OTT-direction lives in a separate numba function — without an adapter it
never reaches the DSL, yet the SIV reference strategy (`dev_docs/strategy.md`) requires
`ott.direction == 1`.

**Binding registry** (design core, not hardcoded resolvers):
```python
@dataclass(frozen=True)
class IndicatorBinding:
    dsl_name: str                     # 'rsi'
    func: Callable[..., np.ndarray]   # rsi_ind
    params: dict[str, ParamSpec]      # length: int(1..), ...
    outputs: dict[str, OutputSpec]    # 'value' -> output 0; 'direction' -> output 3
    sources: tuple[str, ...]          # ('close',) | ('high','low','close') | ('close','volume')
    min_bars: Callable[[dict], int]   # warm-up as a function of params
```
The manifest is generated from bindings (`build_manifest`) → `ManifestValidator` works for free,
and RAG (TZ-07) renders deterministic context from it. The registry is assembled from group
`__all__` + an explicit table of approved indicators (not all ta is exposed).

### T4. Warm-up/NaN — a contract, not default behavior
Inside the provider `nan_policy='ignore'` (not 'raise' — otherwise warm-up kills everything), but:
- `t < min_bars(params)` → NotReady: signal False + warmup-skip counter in the report;
- NaN after warm-up → `EvaluationError` (data anomaly).
Unified with TZ-01 §5. Rejected alternative (fillna with zeros) distorts indicator values in the
first bars — warm-up signals would be garbage.

## 3. Requirements

1. `IndicatorBinding` + registry per 7 groups (1–2 indicators per group first).
2. `build_manifest(bindings) -> Manifest`.
3. `TaProvider(IndicatorProvider)`: compute-once/cache/offset-indexing/multi-output/
   NotReady contract; batched `resolve_history` (override from TZ-01 §4).
4. Look-ahead safety inherited from the engine (slice `[:t+1]`); test invariant: replacing
   "future" bars with garbage does not change any resolve(t).
5. All AST indicators computed batched once before the run (AST walk via `to_dict` is available).

## 4. Acceptance criteria

- **Parity**: `evaluate_dsl("rsi(period=14).value[2] < 30")` at bar t ==
  `rsi_ind(close, 14)[t-2]` — for a representative of each of the 7 groups.
- Warm-up: exactly `min_bars` NotReady bars, then values.
- Multi-output: `ott.direction` == `_compute_trend_direction_numba`.
- Offset: `x[3] == arr[t-3]` (not ta-shift).
- Performance: 2 expressions × 5000 bars < 1 s.