# Quant Researcher — Project Checklist

> **STATUSES (added while reconciling with the TZs; the original text below is unchanged).**
> Legend: ⬜ not started · 🔨 in a TZ · ✅ already implemented in code.
> Mapping to TZs (`dev_docs/tz/`):
>
> - **Section 1** (look-ahead/ZigZag): online ZigZag and block validity → 🔨 TZ-04 §4.3 (SIV) +
>   TZ-03 §5 (look-ahead invariant); ✅ causal ATR and TP/SL from ATR(t-1) already in
>   `ai/src/features.py` (moves to TZ-04 §0 as the single execution engine).
> - **Section 2** (execution): entry at open[t+1], commissions/slippage, dynamic TP/SL, minimum lot
>   → 🔨 TZ-04 §4.1; ⬜ execution latency — after TZ-10.
> - **Section 3** (baselines): logistic regression / Random Forest / XGBoost →
>   🔨 TZ-04 §4.6 (the backtest report must contain a baseline comparison); the >5–10% on
>   Sharpe/PF criterion — in the TZ-04 acceptance criteria.
>
>   ⚠️ **SPECIAL ATTENTION — Baseline gate (the project's main filter).** Comparison with simple
>   methods is not "one of the items" but a **mandatory decision gate**: without it, no strategy
>   and no model is considered valid.
>   - The gate stands BEFORE all other result consumption: RAG precedents, real-data training and
>     the live contour do not open until the Transformer is compared with Buy & Hold, logistic
>     regression, RF/XGBoost on one test period.
>   - Decision rule: the complex model must beat the best simple one by
>     **> 5–10% on Sharpe or Profit Factor** (out-of-sample, with commissions). Otherwise —
>     **simplify / return to a simple model**, not "tune the Transformer".
>   - Why it matters: a complex model not beating a baseline = overfitting or leak, and each next
>     complexity iteration only masks the problem.
>   - Where it is implemented: TZ-04 §4.6 (engine + report), the TZ-06 §2.2 validation contour
>     (same test period); baked into TZ-04 and TZ-00 §5 acceptance.
> - **Section 4** (holding/drawdown): holding penalty → 🔨 TZ-02 (label generator; the "not in
>   loss" decision justified in TZ-06); MaxDD stop → 🔨 TZ-04 §4.4; error streaks and RL (PPO) →
>   ⬜ deferred.
> - **Section 5** (leakage/validation): TP/SL from data ≤ t → 🔨 TZ-04 §4.1.5; temporal validation
>   → 🔨 TZ-06 §2.2 (also closes the seq_len=128 window-overlap leak); Walk-Forward and cross-asset
>   → 🔨 TZ-04 §4.6.
> - **Section 6** (reproducibility): YAML config, seed, logs → 🔨 TZ-04 §4.5–4.7, TZ-06.
> - **Section 7** (production): inference → 🔨 TZ-05; white API + local GPU node →
>   🔨 TZ-09/TZ-10 (GPU deps on the local only); jit/ONNX, feature drift, fallback → ⬜ after the
>   respective TZs.

---

This checklist records the current **weak points** (vs the industry standard) and a step-by-step
plan to fix them.
Goal: make the system resilient to overfitting, realistic in execution, and ready for live trading.

---

## 1. Устранение Look‑ahead Bias (перерисовка ZigZag)

### ❌ Сейчас
- ZigZag строится на всей истории сразу → экстремумы могут смещаться с появлением новых данных.
- Order Blocks, найденные на истории, **невалидны** в реальном времени, потому что последний пик/впадина могли перерисоваться.

### ✅ Что нужно сделать
- [ ] Реализовать **онлайн‑версию ZigZag** (инкрементальное обновление без перерисовки).
- [ ] В функции `identify_order_blocks` использовать только те экстремумы, которые **зафиксированы** (т.е. не могут измениться в будущем).
- [ ] Добавить проверку: блок считается валидным, если его `end_idx` < текущий индекс и расстояние до следующего экстремума > порога.
- [ ] Написать юнит‑тест, который сравнивает исторический ZigZag и онлайн‑версию на синтетических данных.

**Пример кода для проверки** (в будущем):

```python
# Вместо вызова zigzag_peaks_valleys(all_high, all_low) один раз,
# нужно вызывать обновление на каждом новом баре и фиксировать экстремумы.
class OnlineZigZag:
    def update(self, high, low):
        # обновление состояния, фиксация окончательных вершин
        pass
```

---

## 2. Реалистичное исполнение и учёт издержек

### ❌ Сейчас
- Вход по `close` свечи, выход проверяется по `high/low` той же свечи (невозможно в реальности).
- Не учитываются комиссии, проскальзывание, задержки исполнения.
- TP/SL – фиксированные проценты, не зависят от рыночных условий.

### ✅ Что нужно сделать
- [ ] В функции `generate_labels_from_strategy` **вход** осуществлять на следующей свече (`open` следующего бара).
- [ ] **Выход** проверять на следующей свече (или позже), а не на текущей.
- [ ] Добавить параметры `commission_pct`, `slippage_pct` и вычитать их из прибыли при расчёте `outcome`.
- [ ] Вместо фиксированного TP/SL использовать динамический уровень (например, `entry ± n * ATR`), чтобы адаптироваться к волатильности.
- [ ] В бэктесте учитывать **минимальный размер лота** и округление.

**Пример модификации**:

```python
# Новая версия _process_exit должна проверять выход на следующем баре
def _process_exit_next_bar(i, position, next_open, next_high, next_low, ...):
    # Выход по TP/SL на следующей свече
    pass
```

---

## 3. Добавление бенчмарка и простых моделей (Baseline)

### ❌ Сейчас
- Только сложный Transformer, нет сравнения с простыми методами.

### ✅ Что нужно сделать
- [ ] Обучить **логистическую регрессию** на тех же признаках (цены + индикаторы) для предсказания действия.
- [ ] Обучить **Random Forest** или **XGBoost** на агрегированных признаках (например, последние значения индикаторов).
- [ ] Сравнить их метрики (Accuracy, F1, Profit Factor) с Transformer на тестовом периоде.
- [ ] Если сложная модель не превосходит простую на >5-10% по Sharpe или Profit Factor – вернуться к простой модели или упростить архитектуру.

---

## 4. Учёт времени удержания и просадок (Risk of Ruin)

### ❌ Сейчас
- Loss функция не штрафует за длительное удержание позиции.
- Нет контроля над максимальной просадкой (drawdown).

### ✅ Что нужно сделать
- [ ] В `outcome` включить **временной фактор**: например, штрафовать пропорционально числу баров удержания.
- [ ] Добавить в функцию потерь (loss) **штраф за серии ошибок** (например, если модель ошибается 3 раза подряд, увеличивать loss для следующего предсказания).
- [ ] Внедрить **метрику максимальной просадки** в валидации и останавливать обучение, если она превышает порог.
- [ ] Рассмотреть использование **Reinforcement Learning** (например, PPO) вместо supervised learning, чтобы оптимизировать итоговый PnL, а не поточечную точность.

**Пример**:

```python
# В dual_loss можно добавить компонент, штрафующий за длительные позиции
time_penalty = torch.mean((action_targets == 1).float() * (seq_len - ...)) * lambda_time
```

---

## 5. Устранение Data Leakage и валидация по времени

### ❌ Сейчас
- `outcome` вычисляется на основе TP/SL, которые известны на момент входа → модель может подглядывать в будущее.
- Валидация случайным сплитом (перемешивание) – нарушает временную структуру.

### ✅ Что нужно сделать
- [ ] Гарантировать, что TP/SL рассчитываются **только** по данным, доступным до момента входа (например, использовать ATR предыдущих баров).
- [ ] Валидацию выполнять **только по времени**: обучать на данных до 2023 года, тестировать на 2024–2025.
- [ ] Добавить **Walk‑Forward** валидацию (обучение на скользящем окне) для оценки стабильности стратегии.
- [ ] Провести **тест на нейтральных активах** (обучать на SPY, тестировать на QQQ или акциях Китая), чтобы проверить обобщающую способность.

---

## 6. Документирование и воспроизводимость

### ❌ Сейчас
- Конфигурации разбросаны по коду (OrderBlockConfig, параметры обучения).
- Отсутствует единый конфиг‑файл для воспроизведения экспериментов.

### ✅ Что нужно сделать
- [ ] Вынести все гиперпараметры (индикаторы, окна, архитектура, обучение) в один **YAML/JSON** конфиг.
- [ ] Добавить **seed** для всех случайных операций (numpy, torch, random) для воспроизводимости.
- [ ] Записывать логи экспериментов (метрики, конфиг, дата) в отдельную папку.
- [ ] Написать **README** с инструкцией по запуску полного пайплайна (от сырых данных до финальной модели).

---

## 7. Производственная готовность (Production)

### ❌ Сейчас
- Модель обучается офлайн, нет API для инференса.

### ✅ Что нужно сделать
- [ ] Написать скрипт для **инференса** модели на новых данных (батч или стриминг).
- [ ] Оптимизировать инференс (например, использовать `torch.jit.script` или ONNX для скорости).
- [ ] Добавить мониторинг дрейфа признаков (проверять, что распределение новых данных не отличается от обучающих).
- [ ] Реализовать fallback‑стратегию (например, переключение на простую MA) при аномалиях.

---

## 📊 Индикаторы успеха (после выполнения чек‑листа)

- [ ] Модель показывает **положительный Profit Factor** > 1.5 на аут‑оф‑семпл (Out‑of‑Sample) с учётом комиссий.
- [ ] Максимальная просадка (Max Drawdown) не превышает 20% от пикового капитала.
- [ ] Коэффициент Шарпа (Sharpe) > 1.0 (годовой).
- [ ] Модель **не уступает** простым бенчмаркам (логистическая регрессия, Buy & Hold) по совокупным метрикам.
- [ ] Воспроизводимость: повторный запуск с тем же seed даёт идентичные результаты.

---

## 🛠️ Задачи для ближайшего спринта (приоритет 1)

1. **Переписать генерацию лейблов** с учётом входа на следующей свече.
2. **Добавить комиссии и проскальзывание** в бэктест.
3. **Заменить валидацию** на строгую временную (без перемешивания).
4. **Внедрить онлайн‑ZigZag** (без перерисовки).

---

## 🔗 Ресурсы

- [ ] Статья про Look‑ahead Bias в трейдинге
- [ ] Пример Walk‑Forward валидации на Python
- [ ] Библиотека `backtrader` или `vectorbt` для бэктестинга с комиссиями
