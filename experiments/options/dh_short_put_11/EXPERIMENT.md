# 1.1 — Delta-hedged short put (волна 4)

**Спека frozen до кода пререга** (движок `_hedge.py` v1.0.0 уже
закоммичен и покрыт тестами -- инфраструктура, не стратегия).
Один прогон -> `runs/dh_short_put.log`.

## Гипотеза

Волна-1 показала: hold-to-expiry short vol не конвертирует VRP в
PnL (хвосты). Delta-hedge убирает направленную часть, оставляя
чистый вопрос: платит ли implied > realized за гамма-дренаж на
пути. Фаза-0: на входе IV-RV = +11.8pt медиана на put-ногах.

## Стратегия (frozen)

- Universe: frozen strangle-rolls, ТОЛЬКО put-нога m=0.90 (тот же
  выбор страйка, что в волне 1).
- Вход: только legs с реальным print-IV (медиана +/-1d, как
  `_runner.entry_iv`). Legs без prints -- пропускаются (считаются).
- Держим до экспирации, daily delta-hedge по `_hedge.delta_hedge`:
  путь = Binance 1H close между roll_ts и экспирацией, band 0.10,
  HAIRCUT 0.25 на опционную премию (конвенция _runner), underlying
  ребаланс без издержек (maker/perp, объявлено).
- IV вдоль пути константен = entry IV (объявленное упрощение;
  mark-to-IV-dynamics -- read-out, не гейт).
- Size: NOTIONAL 0.10 на ногу, PnL в % equity = pnl_подложки /
  spot(вход) * NOTIONAL * 100.

## Гейты

| гейт | метрика | порог |
|---|---|---|
| G-H1 | raw Sharpe daily-потока | >= 1.0 |
| G-H2 | max DD | <= 20% |
| G-H3 | медиана leg PnL и средний leg PnL | >= 0 оба |
| G-H4 | worst leg | >= -15% |
| G-H5 | покрытие: hedged legs | >= 25 (иначе FAIL по power) |

PASS = все пять. Raw Sharpe governs (дегенеративная ветка NW
объявлена, BATTERY §1).

## Read-out (не гейты)

IV-RV на входе vs hedged PnL по терцилям (конвертируется ли
премия); rebalance-каунты по годам; per-year PnL; доля skipped
legs; сравнение с unhedged-аналогом из волны 1 (read-out, не ран).

## Kill-rule

FAIL закрывает 1.1 в этой механике. Дельта-хедж на straddle (1.2)
и var-swap (1.3) -- отдельные строки карты, не рестарты.

## История версий

| версия | дата | изменение |
|---|---|---|
| v1.0.0 | 2026-09-26 | первый frozen one-shot прогон |
