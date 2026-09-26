# D1 Covered calls -- спека frozen ДО кода (v1.0.0, один ран)

Гипотеза: BTC long 1.0 notional + систематический short OTM call
генерирует yield поверх beta и улучшает Calmar vs buy-hold.

## Setup (frozen)

- Underlying: BTC spot 1.0 notional, daily close-to-close.
- Short call: тот же выбор ноги, что strangle_carry -- monthly
  roll, strike m ~ 1.10 (ближайший из subset), NOTIONAL 0.10,
  HAIRCUT 0.25, hold to expiry (правила _runner.simulate).
- Период: все frozen-роллы (2021-04..2026-09).
- Port daily = BTC daily ret % + call-leg daily %.

## Gates (frozen)

| гейт | метрика | порог |
|---|---|---|
| G-D1a | Sharpe портфеля (annualized) | >= 0.8 |
| G-D1b | max DD | <= 40% |
| G-D1c | Calmar портфеля > Calmar BTC buy-hold | строго |
| G-D1d | yield (премия/год) | >= 2% |

PASS = все четыре. Read-out: cumulative vs BTC, yield by year,
doly capped upside (доля месяцев, где spot > strike на экспирации).

## Прereg-оговорки

Это beta-overlay тест, не alpha: G-D1a намеренно 0.8. Если
G-D1c FAIL -- стратегия не бьёт buy-hold, регистрируется как FAIL
без рестартов (change strike/tenor = подгонка).
