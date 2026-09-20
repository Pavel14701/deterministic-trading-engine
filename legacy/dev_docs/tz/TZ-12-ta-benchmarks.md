# TZ-12. `ta/` indicator benchmarks

> **Status: 🔨 runner ready (2 smoke tests, marker `performance`).**
> ✅ ta/benchmarks/run.py: scenarios by group — SMA/EMA (overlap), RSI/MACD (momentum), ATR
> (volatility), CDL-engulfing (candle), SCRSI (custom; OTT skipped due to the known numba
> int8+fillna bug). Baselines: pandas naive rolling (SMA/EMA/ATR), in-package *_numpy
> (RSI/MACD/SCRSI), TA-Lib (optional, n/a if not installed). Fairness: cold JIT on its own line,
> warm = best-of-N, fixed seed, identical inputs. Runner: `uv run python -m ta.benchmarks.run
> --n 100000 --save` → table + `ta/benchmarks/results/bench_<n>.md`.
> ⬜ README section with results; reproducible ±10% reruns; TA-Lib/pandas_ta in CI
> (optional job).

> Scenario sources and reference values: `dev_docs/overlap_indicators..md`,
> `dev_docs/momentum_indicators..md`, `dev_docs/volatility_indicators.md`,
> `dev_docs/trend_indicators..md`, `dev_docs/candle.md` (Bulkowski pattern efficiency — for smoke
> correctness, not speed).

## 1. Context

The project's strong suit — Numba cores of ta/ (1952 tests, causality) — is not backed by numbers.
README and portfolio positioning require public, measurable proof.

## 2. Requirements

1. The `ta/benchmarks/` directory: timing against three baselines — pandas (naive rolling),
   pandas_ta, TA-Lib — on 10k / 100k / 1M bar series.
2. Group representatives: SMA/EMA (overlap), RSI/MACD (momentum), ATR (volatility), one CDL
   pattern, one custom (OTT or SCRSI).
3. Runner: `uv run --package dte-ta python -m ta.benchmarks.run --n 100000` → a table
   (module/indicator/baseline, ms, speedup) + save to `ta/benchmarks/results/*.md` for README.
4. Fairness rules: JIT warm-up excluded from timing (separate "cold" line); identical inputs,
   causal windows; fixed seed for data.

## 3. Acceptance criteria

- Results reproducible (±10% across runs).
- The table added to README (the `ta/` section).
- Numba cores are no slower than baselines on any scenario; otherwise — an optimization issue.