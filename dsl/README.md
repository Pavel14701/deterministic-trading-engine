# dte-dsl — декларативный DSL торговых условий

Малый язык для описания условий входа/выхода без Python-кода:
`close > avsl(fast=70, slow=345) and close[1] <= avsl(fast=70, slow=345)[1]`.
Чистый stdlib, ~4k строк: **tokenizer → parser → AST → interpreter**,
поверх **Context** с цепочкой **провайдеров индикаторов**. Есть
синхронный и асинхронный путь вычисления. Язык ни о чём не знает про
рынок: имена индикаторов, их параметры и атрибуты задаются манифестом
провайдера.

В этом репозитории DSL используется на двух уровнях:

1. **Напрямую** — условия в коде (адаптер `ta/src/provider` строится
   на интерфейсе провайдеров; движок-фичи через `engine/features/dsl`).
2. **Через yaml-теории** — `theories/*.yaml` + `dsl/theory.py` +
   `experiments/infra/theory_runner.py`: условие входа из DSL
   становится полноценным экспериментом с симуляцией, метриками
   через `engine` и гейтами (см. [docs/THEORY.md](../docs/THEORY.md)).

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Архитектура](#архитектура)
- [Синтаксис](#синтаксис)
- [Индикаторы, параметры, атрибуты, история](#индикаторы-параметры-атрибуты-история)
- [Контекст и провайдеры](#контекст-и-провайдеры)
- [Язык в yaml-теориях](#язык-в-yaml-теориях)
- [Обработка ошибок](#обработка-ошибок)
- [API-референс](#api-референс)
- [Тесты](#тесты)
- [Границы и контракты](#границы-и-контракты)
- [Архивные подробные доки](#архивные-подробные-доки)

## Быстрый старт

```python
from dsl.context import Context
from dsl.evaluate import evaluate_dsl
from dsl.providers.in_process import InProcessProvider

manifest = {
    "indicators": {
        "sma": {
            "parameters": {
                "period": {"type": "int", "min": 1, "max": 500, "default": 20},
            },
            "attributes": ["value"],
        },
        "close": {"parameters": {}, "attributes": []},
    }
}

def resolver(name: str, params: dict, attributes: list[str], history: int) -> float:
    # name='sma'|'close', params={'period': 20}|{}, attributes=[], history=0|N
    return series[name][history]  # history = 0 (текущий бар) или глубина смещения

provider = InProcessProvider(manifest, resolver)
context = Context([provider])

ok = evaluate_dsl("sma(period=20) > close", context)
```

Формульный вход `evaluate_dsl` делает всё сразу: tokenize → parse →
interpret, возвращает `bool`. Для асинхронных провайдеров —
`await evaluate_dsl_async(code, context)`.

## Архитектура

```text
строка кода
   │  Tokenizer (dsl/tokenizer.py)   — regex-лексер, токены с позицией
   ▼
токены                 → ParseError на неожидаемом символе
   │  Parser (dsl/parser.py)         — рекурсивный спуск → AST
   ▼
AST (dsl/ast.py)       — BinaryOp, Comparison, MultiComparison,
   │                     IndicatorCall, AttributeAccess,
   ▼                     HistoricalAccess, LetExpression, Rising/Falling, …
Interpreter (dsl/interpreter.py) — pattern-matching по узлам AST,
   │                               значения берёт у Context
   ▼
Context (dsl/context.py)         — валидация запроса по манифесту,
   │                               обход цепочки провайдеров
   ▼
IndicatorProvider (dsl/providers/base.py)
   ├── InProcessProvider      — манифест + функция-резолвер в процессе
   ├── ManifestProvider       — валидация манифеста как отдельная ступень
   └── AsyncIndicatorProvider — асинхронный базовый класс
```

Пакет — workspace-член (`dsl/pyproject.toml`), тесты в `dsl/tests/`,
входят в дефолтный прогон pytest и CI.

## Синтаксис

### Приоритет операторов (от низкого к высокому)

| уровень | операторы | пример |
|---|---|---|
| 1 | `let … in` | `let x = sma(period=20) in x > close` |
| 2 | `or` | `a or b` |
| 3 | `and` | `a and b` |
| 4 | `not` | `not rising(close, 3)` |
| 5 | сравнения `== != < <= > >=` | `close >= high[1]` |
| 6 | `+ -` | `atr - atr[1]` |
| 7 | `* / %` | `2 * atr` |
| 8 | `^` (степень) | `x^2` |
| 9 | атомы: число, индикатор, скобки | `avsl(fast=70, slow=345)` |

Ключевые слова (весь список): `let`, `in`, `and`, `or`, `not`,
`rising`, `falling`. Идентификаторы: `[a-zA-Z_][a-zA-Z0-9_]*`;
числа — целые и с точкой; строковых литералов нет.

### Сравнения

- одиночные: `close > avsl(fast=70, slow=345)`;
- **цепочки** с ожидаемой семантикой: `a < b < c` ≡ `(a < b) and (b < c)`
  (узел `MultiComparison`, промежуточное значение вычисляется один раз);
- сравнение с `NaN` даёт `False` (IEEE) — на краю истории условие
  просто не срабатывает, исключения нет.

### let-выражения

```text
let короткое_имя = <выражение> in <выражение>
```

Связывание лексическое, вложенность разрешена, перекрытие имён —
внутреннее побеждает:

```text
let a = atr(period=14) in a > close and not (let a = atr(period=50) in a > close)
```

### rising / falling

```text
rising(<выражение-индикатор>, n)   # n баров подряд строго растёт
falling(<выражение-индикатор>, n)  # n баров подряд строго падает
```

`n` — целочисленный литерал. Внутрь передаётся выражение-индикатор;
произвольную арифметику передать нельзя (интерпретатор бросит
`EvaluationError`). Типовое применение — фильтр тренда:

```text
rising(avsl(fast=70, slow=345), 3) and close > avsl(fast=70, slow=345)
```

### Исторические смещения и атрибуты

```text
close[1]                       # значение close один бар назад
avsl(fast=70, slow=345)[1]     # линия AVSL баром назад
bb(period=20).upper            # атрибут 'upper' индикатора bb
avsl(fast=1, slow=34).upper[2] # атрибут, затем смещение
```

Смещение уходит провайдеру как `history` (целое ≥ 0): провайдер
обязан вернуть значение `history` баров назад. Логика «бар t» vs
«смещение» — забота вызывающего кода: в theory_runner контекст
сдвигается на бар, а DSL-офсеты резолвит `SeriesProvider`
(ключ `(имя, frozenset(params))` → `bar - offset`).

## Индикаторы, параметры, атрибуты, история

Что можно писать в выражении, целиком определяется **манифестом**
провайдера:

```python
"indicators": {
    "atr": {
        "parameters": {
            "period": {"type": "int", "min": 1, "max": 200,
                       "default": 14},   # default позволяет atr()
        },
        "attributes": [],                # доступ только целиком: atr(...)
    },
    "bb": {
        "parameters": {"period": {"type": "int", "min": 2, "max": 400}},
        "attributes": ["upper", "lower", "mid"],  # bb(period=20).upper
    },
}
```

- Запрос неизвестного индикатора / неверного параметра / недопустимого
  атрибута падает **до** вычисления — `DslValidationError` с сообщением
  вида `Unknown indicator: X`, `Invalid parameter 'Y' for indicator 'Z'`.
- Значения индикаторов — `float`; `bool`-результат дают только
  сравнение и `rising`/`falling`; верхнеуровневое выражение коэрсится
  в `bool` интерпретатором.

## Контекст и провайдеры

`Context(providers: list)` — цепочка ответственности: запрос валидируется
по манифестам и идёт провайдерам по порядку; `ProviderError` от одного
провайдера → попытка следующего; исчерпание цепочки → `EvaluationError`.

Интерфейс провайдера (`dsl/providers/base.py`):

| метод | назначение |
|---|---|
| `resolve(name, params, attributes, history)` | значение индикатора с текущего момента или со смещением `history` |
| `resolve_history(name, params, attributes, history)` | то же для запроса серии/глубины |
| `get_manifest()` | словарь манифеста (валидация имён/параметров) |

- **`InProcessProvider(manifest, resolver_func)`** — самая частая
  интеграция: словарь-манифест + функция
  `(name, params, attributes, history) -> float` (см. выше).
- **`AsyncIndicatorProvider`** — тот же контракт, но
  `resolve_async` / `resolve_history_async`; работает с
  `evaluate_dsl_async` и async-веткой интерпретатора.
- Свои провайдеры — наследование от `IndicatorProvider`; конвенция
  репозитория: провайдер бросает **только** `ProviderError`
  (иначе ломается цепочка ответственности).

## Язык в yaml-теориях

Условия входа из DSL вшиваются в yaml-теорию (`dsl/theory.py`,
`load_theory` с валидацией):

```yaml
name: avsl_cross_4h
universe: [BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT]
timeframe: 4h
warmup: 400
entry_long: "close > avsl(fast=70, slow=345) and close[1] <= avsl(fast=70, slow=345)[1] and rising(avsl(fast=70, slow=345), 3)"
entry_short: "close < avsl(fast=70, slow=345) and close[1] >= avsl(fast=70, slow=345)[1] and falling(avsl(fast=70, slow=345), 3)"
```

Дальше `experiments/infra/theory_runner.py` делает всё остальное
(данные, симуляция, метрики через `engine`, гейты G1'–G5',
`--register`). DSL здесь отвечает **только за сигнал**; риск-модель,
сайзинг и пороги — поля теории, не языка. Прогон:

```bash
.venv/Scripts/python.exe -m experiments.infra.theory_runner \
    --theory theories/avsl_cross_4h.yaml [--register]
# отчёт: runs/theory_avsl_cross_4h.json
```

Эталонный пример — `theories/avsl_cross_4h.yaml`: реплика
frozen `avsl_cross_s1`, реальный прогон PASS 5/5
(EV +0.261R, NW-Sharpe 1.67, DD 21.8%).

## Обработка ошибок

| исключение | когда |
|---|---|
| `DSLError` | база всей иерархии |
| `ParseError` | синтаксис: неожидаемый символ/токен, с позицией (line) |
| `EvaluationError` | рантайм: неизвестное имя вне манифеста, недопустимый путь атрибута, `rising` без индикатора, несвязанная let-переменная, арифметическая ошибка, исчерпание провайдеров |
| `ProviderError` | провайдер не смог вычислить запрос → контекст пробует следующего |
| `DslValidationError` | нарушение схемы манифеста. Наследует и `DSLError`, и `ValueError` — **контракт RAG repair loop**: текст сообщения (`Unknown indicator: X`, …) парсится как подсказка для авторемонта сгенерированных выражений; менять формулировки нельзя |

## API-референс

| объект | сигнатура | назначение |
|---|---|---|
| `Tokenizer().tokenize(code)` | `-> list[Token]` | лексер; `Token(type, value, line, column)` |
| `Parser(tokens).parse()` | `-> ASTNode` | рекурсивный спуск в AST |
| `Interpreter(context)` | `.visit(node) -> bool` (+ sync/async ветки) | вычисление AST |
| `evaluate_dsl(code, context)` | `-> bool` | «всё сразу», sync |
| `evaluate_dsl_async(code, context)` | `-> bool` | то же с async-провайдерами |
| `Context(providers)` | `list[IndicatorProvider]` | валидация + цепочка провайдеров |
| `InProcessProvider(manifest, resolver_func)` | см. «Быстрый старт» | интеграция в процессе |
| `dsl.providers.manifest` | `ParameterSchema`, `IndicatorSchema`, `Manifest`, `ManifestValidator` | схемы и валидатор манифеста |
| `dsl.theory.load_theory(path)` | `-> Theory` | yaml-теория с валидацией |
| `dsl.theory.scan_indicators(theory)` | `-> dict` | какие индикаторы/параметры встречаются в выражениях |
| `dsl.theory.SeriesProvider` | провайдер над предвычисленными сериями | офсет → `bar - offset`; NaN на краю → `False` |

## Тесты

```bash
.venv/Scripts/python.exe -m pytest dsl/tests -q
```

`dsl/tests/` — схема теории и сканер, семантика провайдера
(офсеты, NaN на краю), парсер/интерпретатор, манифест-валидация.
Входят в общий прогон репозитория и CI.

## Границы и контракты

- DSL описывает **условия**. Деньги, комиссии, позиции — не язык.
- Верхнеуровневый результат всегда коэрсится в `bool`: выражение
  «значение линии» само по себе условием не является (значение для
  линии стопа в theory_runner берётся из серии напрямую, минуя visit).
- `DslValidationError` — контракт с RAG repair loop: тексты ошибок —
  часть интерфейса.
- DSL-вердикт (PASS теории) — это **скрининг**; evidence-результат
  требует датированного пререга и frozen-пайплайна
  (`docs/THEORY.md`, `docs/BATTERY.md`).

## Архивные подробные доки

Развернутые англоязычные главы сохранены как справочник (грамматика,
индикаторы, let, провайдеры, примеры, отладка, API):
`dsl/docs/02-getting-started.md` … `dsl/docs/09-api.md`;
историческое ТЗ языка — `dsl/docs/TZ.md`. Содержание в целом
актуально, но этот README — операциональная истина по текущему
состоянию пакета.
