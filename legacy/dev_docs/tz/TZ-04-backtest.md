# TZ-04. Backtest module `backtest/`

> **Status: ✅ core done (34 tests green).**
> execution.py: fill at open[t+1], slippage, pessimistic SL-first, ATR-dynamic TP/SL.
> portfolio.py: TP1 (50%) + TP2, trailing callback, max_bars_hold, equity + unrealized PnL.
> engine.py: bar-by-bar loop, look-ahead safe, reproducibility.
> metrics.py: PF, Sharpe (annual), MaxDD, win_rate, avg_hold.
> validation.py: temporal split, walk-forward folds, baseline gate (pass/fail/simplify),
> report validator (mandatory: B&H, LR, RF, XGBoost + gate status).
> ✅ wave 2: risk-gate integration (TZ-11 §4.5) — `run_backtest(risk_config=...)` runs every
> entry through `risk.engine.check()`; rejects stored in `metrics.risk_rejects`
> (bar_idx, rule, reason, params snapshot) — 12 tests in test_risk_integration.py
> (config-driven e2e, "permissive gate == baseline" invariant, audit trail).
> Remaining: SIV integration run, msgspec contracts, live contour.

## 1. Context

Backtest is the judge of the whole system: strategy metrics fill RAG precedents, validate the
P(win) model and are the only "trade / don't trade" argument. Requirements are collected from
`dev_docs/quant_checklist.md` (look-ahead, execution, leaks, reproducibility, target metrics) and
`dev_docs/strategy.md` (partial takes, trailing by SuperTrend).

## 2. Point 0 — main principle: one execution engine, three consumers

```
backtest/execution.py  ← the only implementation of execution rules
        ▲                        ▲                      ▲
ai/ (labels)          backtest/ (backtest)      live (future)
```

**Why:** `ai/src/features.py` already implements fill at open[i+1], commission, slippage,
pessimistic SL — if backtest writes its own rules, P(win) predicts the outcomes of trades backtest
does not take. Moving `_process_exit`/`_effective_entry_price` into `backtest/execution.py` closes
checklist items 1–2 with one change and makes semantics unified by definition, not by developer
discipline.

## 3. Package structure

```
backtest/
├── contracts.py    # msgspec: BacktestConfig, Trade, EquityPoint, BacktestReport
├── data.py         # Candle (per api.md), sources: T-Invest, yfinance, synthetic, Parquet
├── execution.py    # execution rules (moved from ai/features.py)
├── portfolio.py    # positions, partial takes, trailing, equity curve
├── risk.py         # limits (deterministic, future Risk Engine)
├── engine.py       # event-driven bar-by-bar loop
├── metrics.py      # PF, Sharpe, MaxDD, win_rate, exposure, risk of ruin
├── validation.py   # walk-forward, temporal OOS split
├── config.py       # YAML config + seed
└── tests/
```

## 4. Requirements with rationale

### 4.1. Execution (execution.py) — closes checklist item 2
1. Signal at bar t → fill at `open[t+1]`. Never at the current bar's close (impossible live).
2. Exit is checked from bar t+1.
3. `commission_pct` (0.1%/side) + `slippage_pct` (0.05%) deducted on entry and exit.
4. TP/SL within one bar: SL is checked first (pessimism; already in ai/).
5. Dynamic TP/SL: `entry ± n × ATR(14)` — levels fixed at decision time from data ≤ t
   (replaces the fixed percentages from the checklist).
6. Minimum lot and quantization: `tick_sz, lot_sz, min_sz` from `Instrument` (api.md);
   a trade < min_sz is not opened. **Why:** without quantization results are not reproducible on a
   real exchange book.

### 4.2. Portfolio (portfolio.py) — SIV strategy.md requirements
- Partial takes: TP1 (50%) + TP2 (rest) — tracked at position level.
- Optional trailing: callback by SuperTrend (SIV); `max_bars_hold`.
- Equity curve: cumulative PnL with unrealized PnL (MTM) by position; used for MaxDD.

### 4.3. Signals can come from python helpers, not only DSL
SIV needs "at least N of M conditions", which the DSL cannot express. The engine accepts
python-filter callables alongside the DSL entry/exit. Contract: `list[bool]` per-bar (for the
whole history) — must be look-ahead safe like the DSL path. Marked SIV-specific.

### 4.4. Risk (risk.py)
Risk per trade ≤ 1–2% (`RiskCapital = capital × 1% / stop_in_points`), concurrent-position limit,
MaxDD stop, instrument white-list, max_bars_hold. All deterministic, no LLM — this becomes the
future Risk Engine as is.

### 4.5. Metrics and reproducibility (checklist item 6)
`profit_factor, sharpe (annual), max_drawdown, win_rate, num_trades, exposure,
avg_hold_bars, risk_of_ruin`. `BacktestReport` (msgspec) always contains the full config +
### 4.6. Validation (validation.py) — checklist item 5
- Temporal split only (train ≤ 2023 → test 2024+), no shuffling.
- Walk-forward: rolling windows + stability map across folds.
- Cross-asset test (train SPY → test QQQ) — optional.
- Baselines (checklist item 3): Buy & Hold, **logistic regression** on the same features
  (prices + indicators, action prediction), **Random Forest / XGBoost** on aggregated features
  (last indicator values); the report must include a comparison with the Transformer
  (Accuracy, F1, Profit Factor), otherwise results are not accepted. If the complex model does
  not beat a simple one by > 5–10% on Sharpe/PF — simplify the architecture.

### 4.6.1. Baseline gate — a mandatory gate (attention, checklist item 3)

Blocks all downstream consumption of backtest and model results:

1. **A backtest report without the baseline table is invalid by construction** — the report
   validator rejects it with an error (not a warning). Mandatory baselines: Buy & Hold,
   logistic regression, Random Forest **and** XGBoost (compute all, don't pick the best).
2. **Pass condition**: the Transformer beats the best simple model by
   **> 5–10% on Sharpe or Profit Factor** on out-of-sample with commissions.
   Fail → decide in favor of the simple model / simplify the architecture
   (recorded in the report as `baseline_gate: pass|fail|simplify`).
3. **The gate freezes inputs**: feature space of the Transformer and baselines is the same
   (prices + ta/ indicators, same windows, same test period). If a baseline trains on fewer
   features, that is recorded in the report.
4. **Re-gate**: any feature/architecture/period change requires re-running baselines; caching old
   comparisons is forbidden.
5. Test: the report without a baseline section fails validation; invariant — Transformer and
   baseline metrics are computed on the identical §0-engine trades.

### 4.7. Config
One YAML: `{data, strategy{dsl_entry/exit, python_filters}, execution{commission,
slippage, lot}, risk, portfolio{tp1, tp2, trailing}, validation{mode, folds}, seed}`.
Logs in `backtest/runs/{config, report, git_hash, date}`.

## 5. Seams

- TZ-02: uses `Strategy`, `TaProvider`; the ai/ label generator moves to execution.py.
- TZ-05: inference = "backtest on a live tail" — shared data.py and signal path.
- TZ-06: model predictions are mixed in only via predict_p_win.
- msgspec to be added to pyproject (declared in api.md, missing from deps).
- backtrader/vectorbt (mentioned in the checklist) are NOT taken: a custom engine is needed for
  DSL, SIV, partial takes; libraries only for cross-checks.

## 6. Acceptance criteria

1. Golden test: identical signals give identical Trade in the ai/ label generator and backtest.
2. Look-ahead invariant: replacing future bars does not change the report.
3. Reproducibility: seed + config = identical report.
4. SIV: full run, DSL discrepancies recorded as a list.
5. 5000 bars × 2 expressions < 1 s.
seed + git hash + data hash. Test: rerun = identical report.