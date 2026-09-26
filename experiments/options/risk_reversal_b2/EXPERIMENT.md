# B2 — Risk reversal: short put 0.90 / long call 1.10 (волна 1)

**Спека frozen до кода и прогона.** Однострелковый ран,
результат: `runs/b2_risk_reversal.log`.

## Гипотеза

Обе ноги благоприятны по фазе-0: put wing rich в 2022+ (продаём с
премией за хвост), call wing стабильно cheap по всем годам (покупаем
дёшево). Risk reversal = tilted long без уплаты полной premium за
direction.

## Стратегия (frozen)

- Universe/крылья: те же frozen rolls, put @ m=0.90 **short**,
  call @ m=1.10 **long**, hold to expiry, вход в roll_ts. Без
  DVOL-фильтра (это отдельный A3-тест).
- Entry/MTM/HAIRCUT/NOTIONAL: как в A3-преге (print-IV медиана +/-1d,
  fallback proxy, HAIRCUT 0.25, NOTIONAL 0.10, daily walk, settle по
  споту экспирации).

## Гейты

| гейт | метрика | порог |
|---|---|---|
| G-B1 | raw Sharpe daily-потока | >= 1.0 |
| G-B2 | max DD | <= 20% |
| G-B3 | worst leg (сумма пары ног за цикл) | >= -15% |
| G-B4 | PnL 2022 года | >= -20% |
| G-B5 | структура: медианный нетто-кредит пары (put credit - call debit) >= 0 И доля entry по реальным prints >= 50% |

PASS = все пять. Raw Sharpe governs (NW-дегенеративная ветка
объявлена, см. BATTERY §1).

## Read-out (не гейты)

per-year PnL; split put-leg / call-leg; доля real-prints по сторонам;
распределение net credit по DVOL-квартилям (для будущего совмещения
с A3-фильтром — БЕЗ запуска такого совмещения в этом ране).

## Kill-rule

FAIL закрывает B2-ветку. Вариации страйков/соотношения ног — новая
строка карты, не рестарт.

## История версий

| версия | дата | изменение |
|---|---|---|
| v1.0.0 | 2026-09-26 | первый frozen one-shot прогон |
