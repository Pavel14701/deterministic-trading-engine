# Карта репозитория

## Ядро (`engine/`)

| Путь | Что это | Статус |
|---|---|---|
| `engine/core.py` | **параметрическое ядро метрик**: AVSL-линия (fast/slow), ресемпл, S1-сайзинг, accrual-поток, NW-Sharpe, block bootstrap, DD; реэкспорт battery v2 | живое; дефолты = frozen-значения; бит-в-бит эквивалентность с passed — `engine/tests/test_core.py` |
| `engine/battery_v2.py` | замерная батарея v2: G1'–G5', ENB, concurrency, xs-bootstrap, ortho_ev, leg-разборы | frozen |
| `engine/passed/` | промоученные стратегии (regression-контракт) | см. `engine/passed/README.md` |
| `engine/tests/` | юнит-тесты ядра, passed-модулей и инфраструктуры | запускаются pytest |

### Промоучено (frozen, измение = аннулирование PASS)

| Модуль | Вердикт | Дока |
|---|---|---|
| `engine/passed/avsl_cross_s1.py` | PASS 5/5 (Sh 1.50/2.84, DD 22/12%, EV +0.17/+0.33R, CI excl 0) | `engine/passed/README.md` |
| `engine/passed/avsl_trailing_s1.py` | S1 vol-target для trailing-модификации | там же |

LATENT (PASS, но не промоучен): **AVS-channel S1** — runner в
`experiments/avsr/`, R = ширина канала; для промоушена нужен
execution-пререг.

## Эксперименты (`experiments/`)

Каждый трек — папка с README-индексом; полный реестр с вердиктами:
[`docs/EXPERIMENTS.md`](EXPERIMENTS.md).  Правила каталога:
запуск `uv run python -m experiments.<track>.<name>`; результаты в
`runs/`; вердикты — в журнал `docs/JOURNAL.md`.

## Пререги (frozen, у корня)

`PREREG_BATTERY_V2.md`, `PREREG_FX_AVSL_D1.md` (отозван),
`PREREG_STOCKS_AVSL_D1.md`, `PREREG_FX_AVSL_4H.md`.
Исторические пререги (AVSL, risk-overlay, live-scale и т.д.)
хранятся текстом в журнале.

## Данные (`data/`)

См. [`docs/DATA.md`](DATA.md).  Кэши resumable, фетчеры —
`experiments/loaders/`, `experiments/fx/duka_fetch.py`,
`experiments/sharadar/fetch_sharadar.py`, `experiments/options/deribit_fetch.py`.

## Прогоны (`runs/`)

Каждый вердикт имеет лог в `runs/` — на лог ссылается журнал.
Логи — часть evidence trail, не удалять.
