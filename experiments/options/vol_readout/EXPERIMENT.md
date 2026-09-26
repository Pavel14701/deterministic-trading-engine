# vol_readout — фаза 0: VRP, стабильность skew, prints-vs-proxy (BTC, Deribit)

**Спека frozen до прогона** (read-out, БЕЗ гейтов и БЕЗ стратегий;
один прогон, результат: `runs/vol_readout.log`).
Код: `vol_readout.py` v1.0.0 + `experiments/options/_pricing.py`.

## Вопросы

1. **VRP**: есть ли систематическое IV>RV и где оно живёт
   (год, DVOL-режим, TTM)? Ежедневный срез DVOL−RV30 и срез по print'ам
   (iv−rv30 на момент print'а — уже со вшитым skew).
2. **Skew stability**: put-skew (+13.8 pts на 0.7-0.9 по frozen-таблице)
   и call-skew (−2.9 near ATM) — постоянны по годам или это артефакт
   одного периода? Если нестабильны — все skew-стратегии фазы 1 под
   вопросом.
3. **Model risk**: какая доля frozen legs strangle-раннера имеет реальные
   prints (±1d от roll) vs цены через DVOL+skew proxy. Верхняя граница
   модельного риска для будущих delta-hedged фаз.
4. **Greeks**: движок `bs_greeks` (delta/gamma/vega/theta), юнит-тесты
   против учебных значений (`engine/tests/core/test_bs_greeks.py`).

## Frozen параметры

- RV30 = std последних 30 дневных лог-доходностей Binance 1H → daily
  closes, аннаулизация √365, в vol points.
- DVOL = close дневной свечи (index 4 json-массива).
- TTM бакеты: <45d / 45-90d / >90d; DVOL-перцентиль: квартили по полной
  выборке.
- Moneyness-бакеты: сетка 5%; put-сторона m∈[0.60,1.00], call m∈[0.60,1.45].
- Медианы, не средние, где указано; n>=10 для ячеек таблицы skew.
- Prints: `strangle_trades` + `puts_trades` + `puts_trades2`; битые файлы
  считаются и логируются (не правятся).
- Real-prints критерий для leg: ≥1 print инструмента в ±1 день от roll_ts.

## Что это НЕ

Не стратегия, не гейты, не изменение frozen-модулей. Результат — карта
для фазы 1 (short put / risk reversal / DVOL-фильтр): если VRP нет или
skew нестабилен — фаза 1 отменяется.

## История версий

| версия | дата | изменение |
|---|---|---|
| v1.0.0 | 2026-09-26 | первый frozen one-shot прогон |
