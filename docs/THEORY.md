# THEORY.md — DSL-теории: эксперимент без питон-скрипта

## Что это

Теория эксперимента описывается **одним yaml-файлом** (`theories/*.yaml`):
условия входа — выражениями [DSL](../dsl/README.md) (индикаторы, `[offset]`,
rising/falling, let), риск-модель и пороги гейтов — полями схемы
(`dsl/theory.py:Theory`). Универсальный ранер
`experiments/infra/theory_runner.py` делает остальное: грузит бары,
предвычисляет индикаторы, симулирует сделки по frozen-конвенциям, считает
метрики **только** через `engine/core.py` + `battery_v2` и по `--register`
заводит папку эксперимента с `EXPERIMENT.md`.

```bash
uv run python -m experiments.infra.theory_runner theories/avsl_cross_4h.yaml
uv run python -m experiments.infra.theory_runner theories/avsl_cross_4h.yaml --register
```

## Схема теории

```yaml
name: avsl-cross-4h          # имя теории
version: 1.0.0               # версия ТЕОРИИ (не evidence-версии скрипта)
family: avsl                 # experiments/<family>/
experiment: cross_dsl_replica
universe: [BTC, ETH, SOL, XRP]
timeframe: 4h                # 1h | 4h | 1d (ресемпл 1H через engine.core.resample_bars)
warmup: 400                  # баров до первого допустимого сигнала
entry_long: >-               # DSL-выражение (bool), вычисляется на close бара t
  close > avsl(fast=70, slow=345)
  and close[1] <= avsl(fast=70, slow=345)[1]
entry_short: >- ...
k_atr: 2.0                   # риск = max(k_atr * atr(14), |close - stop_line|)
stop_line: "avsl(fast=70, slow=345)"   # опционально: линия стопа
targets: [3, 5, 8]           # TP-градация, R
primary: 5                   # основной TP для вердикта
horizon: 500                 # MTM-выход, баров
fee_bps: 5                   # taker за сторону (round trip = 2x)
sizing: s1                   # s1 | flat
segments: 2                  # на сколько сегментов делить поток (G1')
gates: {g1_min_sharpe: 1.0}  # переопределения порогов (дефолты BATTERY.md)
```

## Семантика симуляции (1:1 с engine/passed/avsl_cross_s1)

- сигнал вычисляется на close бара `t`, вход по `close[t]`;
- `risk = max(k_atr * atr(14)[t], |close[t] - stop_line[t]|)`;
- `stop = close[t] ∓ risk`, `tp = close[t] ± primary * risk`;
- **консервативный within-bar: stop wins** при касании обоих уровней в баре;
- выход MTM по `close[t + horizon]`;
- `fee_r = 2 * fee_bps * close[t] / risk` вычитается из gross R;
- сделки `{net, gross, e0, e1, long, sym}` — тот же контракт, что во frozen.

## Метрики и гейты (дефолты = docs/BATTERY.md)

| гейт | метрика | порог |
|---|---|---|
| G1' | min NW-Sharpe по сегментам потока (lags 500) | ≥ 1.0 |
| G2' | portfolio DD (1%/слот, S1-сайзинг) | ≤ 25% |
| G3' | pooled net EV на сделку | ≥ 0.10R |
| G4' | доля активов с EV>0 (только юниверс > 1) | ≥ 70% |
| G5' | block bootstrap CI (B 1000, block 500, seed 11) | 0 вне CI |

Пороги переопределяются в `theory.gates` (явное прereg-решение). Отчёт —
`runs/theory_<name>.json`; консоль печатает таблицу по активам и гейты.

## Валидация

Канонический пример `theories/avsl_cross_4h.yaml` — репликация frozen
AVSL-cross 4H. Прогон от 2026-09-26: PASS 5/5 (EV +0.261R, NW-Sh 1.67,
DD 21.8%, CI [+0.003, +0.016]) — совпадает по порядку с confirm-вердиктами
frozen-модуля (EV +0.17/+0.33R, Sh 1.50/2.84, DD 22/12%).

## Границы

- Поддержанные индикаторы: `close/high/low/volume`, `avsl(fast, slow)`,
  `sma(period)`, `atr(period)`; `atr(14)` всегда предвычислен (риск-модель).
- Это **теория/скрининг**: зачисление в evidence по-прежнему требует
  датированного пререга и frozen-пайплайна (см. docs/EXPERIMENTS.md);
  DSL-верdict PASS не создаёт evidence-версию автоматически.
