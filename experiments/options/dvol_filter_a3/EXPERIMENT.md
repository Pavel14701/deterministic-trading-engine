# A3 — DVOL-фильтр short vol (волна 1)

**Спека frozen до кода и прогона.** Однострелковый ран,
результат: `runs/a3_dvol_filter.log`. База: frozen strangle-runner
(`experiments/options/strangle_carry`, CLOSED как безусловный), фаза-0
read-out (`runs/vol_readout.log`).

## Гипотеза

VRP систематически концентрирован в high-DVOL режиме (фаза 0: q4_hi
+15.3pt против q2 +4.1). Если торговать short strangle **только когда
DVOL в верхнем квартиле своей истории**, decay VRP (2026: +1.4) и
дренаж хвостов обходятся: позиция входит в режим, где премия платит
за хвосты.

## Стратегия (frozen)

- Universe: frozen strangle-rolls (`strangle_rolls.json` + `strangle_subset.json`),
  крылья как в strangle_carry: short put @ m=0.90, short call @ m=1.10
  (ближайший страйк), hold to expiry, вход в roll_ts.
- **Фильтр (единственная новая степень свободы):** вход в roll только
  если DVOL-перцентильный ранг дня (по полной выборке dvol_BTC_1D,
  как в vol_readout) **>= 0.75 (q4_hi)**.
- Entry-цена: **реальный print-IV** (медиана trade-IV инструмента в
  +/-1d от roll) если есть, иначе proxy DVOL + frozen skew (та же
  SKEW_PUT-таблица и call-бакеты, что в strangle_carry).
- MTM: proxy sig = DVOL + skew на текущем споте, daily walk,
  settle по споту экспирации. HAIRCUT 0.25, NOTIONAL 0.10 — как
  frozen strangle.

## Гейты (все на filtered-поток)

| гейт | метрика | порог |
|---|---|---|
| G-A1 | raw Sharpe daily-потока (x sqrt365) | >= 1.0 |
| G-A2 | max DD equity | <= 20% |
| G-A3 | медиана IV-RV на вошедших legs и доля legs с IV>RV | > 2.0pt и >= 60% |
| G-A4 | worst leg | >= -15% |
| G-A5 | покрытие: вошедших legs | >= 25 (иначе FAIL по power, без пересмотра порога) |

PASS = все пять. NW-гейт не используется (малое n, sawtooth-потоки;
raw Sharpe governs — объявленная дегенеративная ветка по BATTERY §1).

## Read-out (не гейты)

безусловный поток vs filtered (тот же движок, фильтр снят) — прирост
режимом; per-year PnL; доля entry по реальным prints; split put/call.

## Kill-rule

FAIL закрывает A3-ветку (DVOL-фильтр на short strangle) без
перепараметризации. Порог фильтра (0.75) после рана не трогается.

## История версий

| версия | дата | изменение |
|---|---|---|
| v1.0.0 | 2026-09-26 | первый frozen one-shot прогон |
