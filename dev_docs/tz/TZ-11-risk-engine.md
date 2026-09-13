# TZ-11. Risk Engine — deterministic risk path (config-driven)

> **Status: ✅ implemented (22 tests + 12 integrations in backtest).**
> ✅ risk/config.py: typed config (frozen dataclass), strict validation — unknown key / wrong
> type / forbidden severity compile: warn → error at validate_config(); default hierarchy
> (configs/risk.yaml) → user --config (deep merge) → RISK_* env (only declared, unknown → error).
> ✅ risk/rules/: "contract" registry — name → implementation, params — data only;
> v1: require_stop_loss, position_limit, max_positions, daily_loss_limit, drawdown_stop
> (with pause_bars). Params schemas (PARAM_SCHEMAS) validated: unknown/untyped/missing required
> block → error.
> ✅ risk/engine.py: check(signal, state, cfg) -> Decision{approve, reason, size, rule} — pure
> function; a reject always carries the rule name.
> ✅ Integration (TZ-04 §4.5): run_backtest(risk_config=...) runs every entry through check();
> rejects stored in metrics.risk_rejects (bar_idx, rule, reason, params snapshot; len = counter).
> ✅ TZ-11 acceptance: config-driven e2e (strict config → 0 trades and 9 rejects; permissive →
> identical to the no-gate baseline); the "no approve without all active rules" invariant;
> size=0 on empty capital; "change limits" absent from the TZ-09 queue schema (test).
> Remaining: the TZ-10 live contour calls the same check() (glue after FastStream↔PG);
> Numba ATR causality — TZ-04 side (already causal).

## 1. Context

The project thesis — "decisions are made only by deterministic code" — is incomplete without a Risk
Engine: currently risk params (TP/SL, ATR multipliers) are scattered (`ai/src/features.py`,
configs), and position/drawdown limits do not exist at all. TZ-11 closes the gap **without
hardcoding**: rules and limits are **data** (config), the engine is their interpreter. Code holds
only safety invariants.

## 2. Place in the system

```
DSL signals (+P(win)) → Risk Engine (TZ-11) → orders (size, SL/TP) → execution (TZ-04 engine)
```

Outside the path: the LLM has neither an import nor transport access (TZ-09 has no limit-change
command — checked by a queue-schema test).

## 3. Principle: config is data, engine is the interpreter

| Layer | What it is | Flexibility |
|-------|-----------|-------------|
| **Engine** (`risk/engine.py`) | runs a signal through ordered rules, collects `Decision`; contains NO rule code | hard code |
| **Rules registry** (`risk/rules/`) | `name` → rule-implementation class | extended by code, enabled/disabled by data |
| **Config** (`configs/risk.yaml`) | rule set and order (`engine.rules`) + params (`params`) | data only, no code change |

An immutable TZ-11 rule: **any limit/threshold/rule-set change is achieved by editing config,
without touching sources.** Threshold hardcoding (magic numbers) is forbidden — everything that
affects a decision is read from config at startup.

## 3.1. Config schema (typed)

`configs/risk.yaml` → a frozen-dataclass config (like `ai/src/config.py`) with strict validation:
`Extra.forbid` (unknown key = error), type and allowed-value checks at `validate_config()`.
Example:

```yaml
engine:
  rules:                     # application order
    - name: require_stop_loss
      active: true
      params:
        tp:  { min_mult: 1.0 }             # thresholds as data, not code
        sl:  { min_mult: 0.0, use_atr: true, atr_lookback: 14 }
    - name: position_limit
      active: true
      params: { max_capital_pct: 0.1, max_units: 10000 }
    - name: max_positions
      active: true
      params: { max_open: 5 }
    - name: daily_loss_limit
      active: true
      params: { max_daily_loss_pct: 0.02 }   # daily limit
    - name: drawdown_stop
      active: true
      params: { max_drawdown_pct: 0.2, pause_bars: 60 }

portfolio:                 # per-instrument overlays (override engine-level)
  max_capital_pct: 0.1
  instruments:
    "TQBR.FIGI": { max_capital_pct: 0.05, max_units: 5000 }
```

## 3.2. Override hierarchy (not hardcode, not "drop-config")

```
defaults  configs/risk.yaml        → inspectable defaults
                              ↓
user      --config <file>.yaml     → merge (deep), unknown keys → error
                              ↓
env       RISK_*                   → strict overrides (only declared in the schema)
```

- `validate_config()` runs at every load layer;
- writing any value outside the declared schema (type/namespace/enum) is an error, not silent ignore.

## 3.3. Rule format = "contract"

Each rule in `engine.rules`:
- `name` → class from the `risk/rules/` registry (single source of logic);
- `params` → data only (no code in config);
- `active: true|false` → enabled/disabled without code edits;
- `severity: enforce|warn` → **in v1 only `enforce` is allowed** (a half-`warn` mode would blur the
## 4. Requirements

1. The `risk/` package — a workspace member **`dte-risk`** (deps: numpy, pyyaml); **decision fixed**:
   a separate package, not a strategies section (live and critical).
2. Config per §3.1–3.3 without hardcode; `validate_config()` on load.
3. API: `check(signal, portfolio, cfg) -> Decision{approve, reason, size}` — a pure function, no
   I/O, no time inside (time/date is a parameter).
4. Rules registry (v1): `require_stop_loss`, `position_limit`, `max_positions`,
   `daily_loss_limit`, `drawdown_stop`; each a "contract" per §3.3.
5. Integration: the TZ-04 backtest calls `check()` on every signal; the TZ-10 live contour uses the
   same `check()` (TZ-00 principle #2: one engine for three consumers).

## 5. What is strictly NOT configured (safety invariants = code + tests)

These guarantees live in code and tests, do not depend on config and cannot be weakened by editing
YAML:
- **no approve without passing all active rules** — no path issues an order;
- **no "change limits" command in the TZ-09 protocol** — queue-schema test;
- **`size=0` on empty/insufficient capital**;
- **rejectors and threshold movement are causal** (ATR from data ≤ t, TZ-04 §4.1.5).

## 6. Acceptance criteria

- **Config-driven**: two different configs on the same code give different behavior
  (threshold/rule-set change without source edits) — e2e test.
- **Validation**: unknown key / wrong type / forbidden `severity: warn` → error at
  `validate_config()`, not silent ignore.
- **Edge cases**: SL/TP ≤ threshold → reject; daily-loss exceeded → reject until end of day;
  MaxDD stop → pause; `size=0` on empty capital.
- **Invariants**: no approve without all active rules; the TZ-09 protocol has no "change limits".
- `uv run --package dte-risk pytest` green.

## 7. Cross-references

- TZ-04: the execution engine accepts `Decision`; the report stores rejects (rule name, params at
  rejection time, count).
- TZ-09: the queue contract has no change `engine.rules/params` command (schema test).
- TZ-14: the risk config is rendered/validated through the same typed-config mechanics as
  `ai/src/config.py`.
  determinism thesis; forbidden until the TZ-04 §4.6.1 baseline gate passes).