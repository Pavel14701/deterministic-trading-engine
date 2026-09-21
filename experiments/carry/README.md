# carry — funding-carry chain + barrier probability

Run: `uv run python -m experiments.carry.<name> [args]`

| module | status | verdict / state |
|---|---|---|
| `funding_carry_v3` | 🟡 SURVIVOR — PASS all gates (STATUS 2026-09-20) | per-asset hold-until-sign-flip carry, Binance 3y. 28/29 assets Sharpe_NW≥1, portfolio 5.19, maxDD 0.55%. Declared decay by fold: +13.5% → +3.75% → +1.45% ann (crowding). Params FROZEN. Next: OKX 96d tradability re-validation + execution design prereg |
| `funding_carry` | ⚫ REJECTED | v1 daily cross-sectional rotation: carry +1.59bp/d vs costs 10.5bp/d → net −32.6% ann. 96d OKX panel too thin |
| `funding_carry_v2` | ⚫ FAIL primary gate | weekly rotation collapses gross 1.6→0.68bp/d — cross-sectional funding extremes mean-revert within days. Maker cut is 1.5× not 5× (spot leg dominates). Secondary gate (per-asset slow carry) → became v3 |
| `barrier_prob` | ⚫ FAIL all gates | P(TP-first) NOT predictable from price/vol/structure features: model Brier 0.21747 > baseline 0.21688; measured P = 0.329 vs Brownian 0.333 (theory confirmed = no drift edge). v2 direction: flow/positioning features (→ ProSP v2) |
