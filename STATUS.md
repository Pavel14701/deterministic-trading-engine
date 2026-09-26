# STATUS — текущее состояние книги

> Полная доказательная база (append-only журнал, ~7.4k строк):
> [`docs/JOURNAL.md`](docs/JOURNAL.md).  Все новые записи
> дописываются **в конец журнала**, не сюда.  Этот файл — только
> снапшот-указатель.  Инвентаризация всех экспериментов:
> [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).  Методология
> измерения: [`docs/BATTERY.md`](docs/BATTERY.md).  Данные:
> [`docs/DATA.md`](docs/DATA.md).

## Состояние на 2026-09-25

### Живое (что можно трогать деньгами и что ждёт следующего слоя)

| Объект | Вердикт | Где | Следующий слой |
|---|---|---|---|
| **AVSL-cross 4H S1** | PASS 5/5, промоучен, frozen | `engine/passed/avsl_cross_s1` | live-scale: Phase A paper ≥90д/≥50 сделок (`experiments/infra/live/`) |
| **AVS-channel S1** | PASS 5/5, LATENT | runner `experiments/avsl/` (channel_breakout, бывш. avsr/) | execution-пререг (P4-EX паттерн) до капитала; R = ширина канала, EV не сравним с AVSL напрямую |
| **funding_carry_v3** | PASS с затуханием (F1 13.5% → F3 1.45%/год) | `experiments/carry/funding_carry_v3` | tradability re-validation; окно закрывается |

### Сводка вердиктов (полный текст — в журнале)

| Семья/трек | Вердикт | Дата |
|---|---|---|
| AVSL entry (15m/1H/4H, цена, trailing, Donchian, фильтры F1–F7) | CLOSED (gross ≈ 0 нетто) | 2026-09-21 |
| AVSL-cross 4H → risk-overlay S1 | **PASS 5/5 → passed** | 2026-09-22 |
| Decomposition E1–E5 | диагност. (4H-сетка + wide-TP = движок) | 2026-09-22 |
| Re-test семьи (z-score E6, Donchian E7, OB E8) | KILL/KILL/KILL | 2026-09-22 |
| TTF v1 (flow divergence 1H) | CLOSED — анти-сигнал gross<0 | 2026-09-24 |
| ProSP v2 (prob-модель потоков) | CLOSED — signal-dead | 2026-09-24 |
| P4 carry exec | CLOSED — execution-blocked; PASS → upper bound | 2026-09-24 |
| AVSR-mirror | CLOSED — 0/4 (F3-ноги нет) | 2026-09-24 |
| AVS-channel (попытка #3/3) | **PASS 5/5, LATENT** | 2026-09-24 |
| Portfolio-layer (AVSL+channel, +OB) | CLOSED (PF-G4: общая дыра 2022–23) | 2026-09-24 |
| SVD universe | rank-one подтверждён; экспансия закрыта | 2026-09-24 |
| AVSL-extended (29 активов) | CLOSED (edge есть, DD-гейты нет) | 2026-09-24 |
| Short-strangle vol carry | CLOSED (VRP +8.6 pts < drain хвостов) | 2026-09-25 |
| FX AVSL D1 | ОТЗЫВАН (invalid transfer, timescale ×6) | 2026-09-25 |
| Stocks AVSL D1 (12/58) | FAIL; disclosure: long EV_orth t+5.2 — декада-однороден, ликвидность-концентрирован; UNRESOLVED (Sharadar срезан) | 2026-09-25 |
| FX AVSL 4H (валидный transfer, полный конфиг) | **FAIL** — тик-объём vs ones control исключает прокси-защиту | 2026-09-25 |

### Главная выводная линия книги

**AVSL-эдж крипто-4H-специфичен** — подтверждено двумя валидными
out-of-crypto тестами с корректным масштабированием.  Живой
движок один + channel-LATENT как кандидат.  Дыра 2022–23 —
структурная (rank-one режим у всех крипто-семей); портфельная
сборка её не чинит.

### Закрыто навсегда (без нового пререга не трогать)

- Конкурсные капы (S3/S4) и ATR-режимный сайзинг для AVSL-наследников — измерено-запрещено (см. `engine/passed/README`).
- Расширение universal-ма крипто (29+ активов, SVD rank-one).
- Entry-вариации AVS-семьи; flow-фичи (TTF/ProSP); short-wings опционные шейпы; шорты stocks-AVSL.

## Правила (кратко)

1. Прereg до прогона; параметр, тронутый после первого рана, убивает трек.
2. One-shot; FAIL закрывает семью по kill-rule; PASS LATENT не потребляет бюджет семьи.
3. Гейты только на PRIMARY + holdout F3; затухание по фолдам — часть вердикта.
4. Отрицательные результаты сохраняются (модуль + лог + запись в журнале).
