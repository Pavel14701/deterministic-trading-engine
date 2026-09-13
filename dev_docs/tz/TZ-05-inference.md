# TZ-05. Inference script

## 1. Context

A single point "strategy + data → signals (optionally P(win))". This is "backtest on a live tail":
the same signal path as TZ-04, without trade simulation.

## 2. Why this way

### 2.1. CLI, not an API/service
There is no main service yet (`main/` is a skeleton). A CLI gives a verifiable artifact for
debugging the path and a base for the future HTTP endpoints of TZ-10. **Rejected alternative**
(straight REST): the signal contract is not stable yet; fixing it in an API before backtest
guarantees breaking changes.

### 2.2. P(win) only via predict_p_win
ML inference is strictly through the TZ-06 §7 contract (`predict_p_win(model, bundle, window, ...)
-> float`) and only when a model bundle is present. Without a bundle the `--ml` flag is
unavailable. **Why:** the "model < 1 ms per trade" requirement is not verifiable without an
inference function; and a state_dict without config (currently) cannot even be loaded.

### 2.3. Data sources
T-Invest (`t_tech.invest`, as in `main/src/main.py`) — primary; yfinance — dev fallback;
Parquet — for tests. Data goes through `PriceDataFramePolars` (unified TZ-02 schema).

## 3. Requirements

1. ✅ CLI: `infer.cli` — `--source {synthetic|parquet|yfinance|tinvest}`,
   `--entry/--exit` or `--strategy-file` (JSON `{dsl_entry, dsl_exit}` — raw Strategy format of
   TZ-02), `--ml <bundle>` + `--p-threshold`, `--output` (csv/parquet by extension).
2. ✅ Pipeline: candles load → `BarSeriesProvider` (compute-once + cache, causal
   ema/sma/rsi/atr + price series) → parse once, Interpreter per bar → signal series → `--ml`:
   windows → `predict_p_win_at` (TZ-06 contract) → threshold filter.
   - Validation cache `_CachedContext` (manifest validator not run on every call);
   - Interpreter reused if the AST has no `let` (`_locals` safety, TZ-01 §3);
   - incidental fix (TZ-01 §1, partial): `Context.get_value` no longer swallows the provider's
     original `ProviderError` — it used to mask `WarmupNotReady` with a bland "No provider found".
3. ✅ Output: `{date, entry_signal, exit_signal, p_win}` + `summary()` (bars/entry/exit/
   warmup_skips/ml_filtered/time) and the list of provider errors. No trading — read-only module.
4. ✅ Performance: warm run 5000 bars × 2 expressions (`ema+rsi` / `sma`) — **~180 ms**
   (target < 1 s). First in-process run includes numba-JIT (~1.4 s) — one-off.
5. ✅ No broker order access.

Honest limitations:
- ML window: indicators/signals/tp/sl are zeros (the full feature pipeline arrives in TZ-02/TZ-04);
  dimensions verified against the bundle.
- Provider indicator set is minimal (ema/sma/rsi/atr + prices/volume); widening to full ta is TZ-03.
- T-Invest loader requires `INVEST_TOKEN`; yfinance is the dev fallback.

## 4. Acceptance criteria

- ✅ Smoke on a synthetic series: 8 tests in `infer/tests/` — resolve parity with direct ta
  functions, offset semantics (`[n]` = n bars back), warmup exceptions, legacy-schema
  normalization, end-to-end signals + summary, early parse error, CLI smoke writing CSV.
- ⬜ Manual run on real T-Invest candles (needs `INVEST_TOKEN`).
- ✅ `--ml` contract: P(win) in [0,1] on signal bars via `EntryExitPredictor.predict_p_win`
  (verified by TZ-06 tests); latency to measure on real hardware.
- Full set: 302 passed, 7 skipped (infer + dsl + ai), ruff clean.