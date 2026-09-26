# t_inv_rag — исследовательский пайплайн: детерминированное ядро + DSL + теории

Quant-research репозиторий: детерминированное движок-ядро (индикаторы,
ресемпл, симуляция, метрики, батареи гейтов), декларативный DSL условий,
yaml-теории поверх DSL и каталог экспериментов по семьям — с
пререгистрацией, frozen-версиями и журналом доказательств.
Рынки: крипто (Binance 1h/15m), FX (Dukascopy), акции (Sharadar —
трек заморожен решением пользователя).

Единственная доказательная база — **[docs/JOURNAL.md](docs/JOURNAL.md)**
(хронология с вердиктами) и снапшот текущего состояния —
**[STATUS.md](STATUS.md)**. Карта всех док — [docs/README.md](docs/README.md).

## Живые результаты

| трек | статус | цифры |
|---|---|---|
| `engine/passed/avsl_cross_s1` (AVSL-cross 4H) | **SURVIVOR, промоучен, frozen** (regression-контракт бит-в-бит) | PASS 5/5: EV +0.17/+0.33R, NW-Sharpe 1.50→2.84 (усиление на holdout), DD 22/12%, CI excl 0 |
| `experiments/carry/funding_carry_v3` | SURVIVOR по пререгу, **затухает** (crowding), параметры frozen | F1 +13.5% → F2 +3.75% → F3 +1.45%/год — закрывающееся окно, не долговременная стратегия |
| AVS-channel S1 (`experiments/avsl/channel/`) | **LATENT** (PASS, ждёт следующего слоя) | для промоушена нужен execution-пререг (P4-EX: честный fill/cost слой) |
| DSL-теории (`theories/`, runner в `experiments/infra/`) | скрининг-слой, не evidence | `avsl_cross_4h.yaml` — реплика frozen: PASS 5/5, EV +0.261R, NW-Sh 1.67, DD 21.8% |

> ⚠️ Цифры +0.44R / +466R в старых документах относятся к ВЫВЕДЕННОМУ
> ИЗ ЭКСПЛУАТАЦИИ champion stack (артефакт сквозь-стоп в симуляторе,
> фикс D.13g). Единственные живые подтверждённые результаты — таблица
> выше. Подробно: `experiments/README.md`, `engine/passed/README.md`.

## Структура репозитория

```text
engine/       ядро и библиотека исследований, тесты рядом (engine/tests/):
  core.py       параметрическое ядро метрик: AVSL(fast/slow), ресемпл,
                S1-сайзинг, accrual-поток, NW-Sharpe, block bootstrap, DD;
                дефолты = frozen-значения; эквивалентность с passed — тестом
  battery_v2.py замерная батарея v2: гейты G1'–G5', ENB, concurrency,
                xs-bootstrap, ortho_ev, leg-разборы (пороги — docs/BATTERY.md)
  passed/       ПРОМОУЧЕННЫЕ стратегии: avsl_cross_s1, avsl_trailing_s1;
                изменение = аннулирование PASS (engine/passed/README.md)
  infra/ features/ structure/ sim/ backtest/ model/ ensemble/
  metrics/ datasets/ data/   — инфраструктура и исторические подсистемы
  tests/        core / passed / legacy

dsl/          dte-dsl: декларативный DSL условий (см. dsl/README.md):
              tokenizer → parser → AST → interpreter, контекст + провайдеры;
  theory.py     yaml-схема Theory, сканер индикаторов, SeriesProvider
  tests/        в дефолтном прогоне pytest и CI

theories/     yaml-теории (DSL-условия входа): theories/avsl_cross_4h.yaml

experiments/  каталог экспериментов: семья/ → эксперимент/ → скрипты
              с __version__; реестр и вердикты — docs/EXPERIMENTS.md:
  avsl/         семейство AVS: baseline … channel (LATENT), portfolio_layer
  carry/        funding_carry v1→v3, p4, prosp_v2, barrier_prob
  donchian/     breakout, quattro, overlay (семья закрыта)
  ob/ zscore/ ttf/ options/ fx/ stocks/  — прочие треки
  infra/        загрузчики (Binance/OKX/YF/Duka), sharadar, live-инфра
  panel/        champion stack — HISTORICAL (не импортировать, не цитировать)
  debug/        диагностика, не эксперименты

ta/           vendored-библиотека индикаторов (upstream)
configs/      configs/engine.yaml — движковые конфиги
scripts/      утилиты (audit_sim_gaps.py)
PREREG_*.md   пререги у корня (battery v2, FX AVSL 4H/D1, stocks AVSL D1)
docs/         вся документация (карта — docs/README.md)
legacy/       архив former-монорепо (см. legacy/MANIFEST.md перед касанием)
data/ runs/   parquet-данные и артефакты прогонов (gitignored)
```

## Запуск

```bash
# тесты (по умолчанию: engine/tests + dsl/tests; legacy и тяжёлое — deselected)
uv run pytest                # сейчас: 434 passed / 6 skipped / 69 deselected
uv run ruff check engine dsl experiments
uv run mypy engine experiments

# DSL-теория: прогон + (опционально) регистрация эксперимента
uv run python -m experiments.infra.theory_runner --theory theories/avsl_cross_4h.yaml

# эксперименты (общий вид; каждый пишет артефакты в runs/)
uv run python -m experiments.<семья>.<эксперимент>.<скрипт> [args]
```

Нюансы окружения:

- **ruff имеет `fix = true` в pyproject** — `ruff check` может молча
  править чужие файлы. Перед коммитом проверяй `git diff`; для
  просмотра без правок — `--no-fix`.
- `uv run` в этой сети упирается в корпоративный TLS — инструменты
  брать из `.venv/Scripts/` напрямую (`.venv/Scripts/python.exe -m pytest`).

## Правила доказательности

1. **Пререг → замер → вердикт.** Гейты frozen до прогона (пороги —
   `docs/BATTERY.md`); вердикт пишется в `docs/JOURNAL.md`.
2. **Версии:** `v1.0.0` = evidence-версия, изменять запрещено; правка
   = новая версия + запись в `EXPERIMENT.md`.
3. **Frozen бит-в-бит:** модули в `engine/passed/` — regression-контракт;
   `engine/core.py` обязан воспроизводить их числа тестом.
4. **Отрицательные результаты сохраняются:** закрытый трек закрыт по
   своему пререгу; оживление — только через НОВЫЙ пререг.
5. **DSL-теория ≠ evidence:** PASS yaml-теории — скрининг; evidence
   требует датированного пререга и frozen-пайплайна (`docs/THEORY.md`).

## Документация

| дока | что там |
|---|---|
| [docs/README.md](docs/README.md) | карта репозитория: ядро, промоученное, пререги |
| [docs/JOURNAL.md](docs/JOURNAL.md) | доказательная база: хронология, вердикты, negative results |
| [STATUS.md](STATUS.md) | снапшот текущего состояния (done / in-progress / next) |
| [docs/CORE.md](docs/CORE.md) | движок-ядро: контракты, инварианты, гоча |
| [docs/BATTERY.md](docs/BATTERY.md) | пороги гейтов G1'–G5' и семантика батареи v2 |
| [docs/THEORY.md](docs/THEORY.md) | yaml-теории: схема, симуляция, границы DSL-вердикта |
| [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) | полный реестр треков со статусами |
| [docs/DATA.md](docs/DATA.md) | данные: источники, схемы, ресемпл |
| [engine/passed/README.md](engine/passed/README.md) | frozen-стратегии и их числа |
| [experiments/README.md](experiments/README.md) | каталог экспериментов, легенда статусов |
| [dsl/README.md](dsl/README.md) | DSL: синтаксис, провайдеры, yaml-теории, API |

## История

Репозиторий начинался как детерминированный торговый монорепо-движок
(DSL-стратегии, RAG-генерация стратегий, адаптеры T-Bank/OKX,
сервисная инфраструктура — архивные ТЗ в `legacy/dev_docs/`).
После geometry-pivot монорепо ушло в `legacy/` (описано в
`legacy/MANIFEST.md`); выжили research-библиотека, data path и DSL.
Дизайн OKX-адаптера (`legacy/packages/okx/`) — стартовая точка для
будущего live-execution слоя.
