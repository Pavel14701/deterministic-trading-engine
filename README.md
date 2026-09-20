# Determenistic Trading Engine — BTC/ETH/SOL trading research pipeline

Research codebase behind a validated, live-defensible EV estimate for a
zone-geometry trading strategy (stop geometry is universal across assets;
direction is not predictable). The champion stack converts backtest EV into
portfolio EV: walk-forward validation → nested CV → portfolio capping →
rank-based admission. Full evidence trail: **STATUS.md**.

## Headline numbers (stage D, pessimistic R)

| metric | value |
|---|---|
| EV per taken trade | +0.44…+0.46 R pess (walk-forward, nested-CV discounted −2.2%) |
| With REPLACE-low admission (D.11) | **+466 R / 14.4 mo (~32 R/mo)** |
| Max drawdown | 2.44 R event-basis (~2.4% equity at 1R = 1%) |
| Walk-forward | B wins 6/8 pooled folds (BTC 7/8, ETH 6/8, SOL 5/8) |
| Portfolio cap | 2 concurrent (one crypto cluster; price corr 0.83–0.87, strategy corr 0.08–0.23) |
| Live rule | cap 2 · 1R = 1% equity · kill-switch armed 4R · REPLACE-low admission |

## Repository layout

```
engine/      research library, subpackaged by function:
               infra/       config, datatypes, parquet I/O, marketdata (OKX)
               features/    indicators, MTF resampling, panels, DSL
                            feed/spec/provider, MFE/MAE event collector
               structure/   zones, entry-candidate detectors
               sim/         event sim, maker entries, state machine,
                            admission policies
               backtest/    walk-forward protocol (folds, ranker, replay)
               model/       LGBM ranker head, feature builders, rule tables
               metrics/     per-trade R performance metrics
               datasets/    dataset assembly pipelines (OKX -> panels)
               experiments/ reproducible experiment drivers
tests/       unit tests (simulator, maker entry, zones, library)
ta/          vendored indicator library (upstream; excluded from default run)
dsl/         dte-dsl package: declarative trading-conditions DSL
             (tokenizer -> parser -> AST -> interpreter, manifest providers);
             ta/src/provider builds on its provider interface; own suite in
             dsl/tests, part of the default run and CI
legacy/      archived dead code of the former monorepo — see
             legacy/MANIFEST.md before touching anything in there
data/ runs/  parquet data and experiment artifacts (d-prefixed filenames are
             historical and referenced from STATUS.md)
```

## Run

```bash
uv sync --all-packages
uv run pytest                 # unit suite (tests/ + dsl/tests)
uv run ruff check engine tests dsl
uv run mypy engine

# experiments (each writes JSON/parquet artifacts into runs/):
uv run python -m engine.experiments.walk_forward_ab     # walk-forward A/B
uv run python -m engine.experiments.admission_policies  # REPLACE-low vs FCFS
uv run python -m engine.experiments.maker_entry         # maker-entry study
```

## Validation protocol (why the numbers are defensible)

- **Walk-forward**: 8 folds × 56d, expanding train, 7d embargo, pre-registered 6+/8 rule.
- **Nested CV**: outer = the same 8 WF folds, inner = last 25% of fold-train (3d gap);
  selection-bias discount measured at −2.2%.
- **Portfolio**: block bootstrap (1000 sims) on daily P&L, p95 DD « 30% flag;
  drawdown quoted on trade-event basis (daily aggregation is ~30% optimistic).
- **Admission**: REPLACE-low (new signal displaces the worst-score open position;
  displaced trades realize negative mean R) beats FCFS by +28% EV at flat DD.
- **Negative results are kept**: transformer parked (data volume does not help
  tabular features, D−C = 0), maker entries rejected (total adverse selection,
  −0.41 R/signal), kill-switch at 2R is pure EV loss.

## History

The repo started as a deterministic trading engine monorepo (DSL strategies,
RAG strategy generation, T-Bank/OKX adapters, service infrastructure — the
`TZ-*` docs in `dev_docs/`). After the geometry pivot the whole monorepo was
archived under `legacy/` (documented in `legacy/MANIFEST.md`); only the
research library, the stage pipeline and the data path survived. The OKX
adapter design lives in `legacy/packages/okx/` and is the starting point for
the future live-execution layer.
