# Карта опционных стратегий (registered backlog, 2026-09-26)

Реестр направлений по **источнику эджа**. Статусы: READY (данные +
движок есть), FETCH (нужны данные), BUILD (нужен движок), EVENT
(нужен календарь). Дисциплина: каждая стратегия — отдельный пререг
до прогона, один ран, FAIL = семья закрыта. Multiple-comparison
бюджет: волна = ≤3 активных пререга одновременно.

Контекст фазы 0 (`runs/vol_readout.log`, `docs/JOURNAL.md` 2026-09-26):
VRP +8.8pt затухает (2026: +1.4), концентрация в q4_hi (+15.3);
put-skew нестабилен по годам (2021 отрицательный), call wing
стабильно cheap; prints покрывают 72% frozen legs.

## Класс 1: VRP (IV vs RV)

| # | Стратегия | Статус | Prior | Примечание |
|---|---|---|---|---|
| 1.4 | A3: DVOL-фильтр short vol | **CLOSED (FAIL G-A1, 2026-09-26)** | — | фильтр смягчает (-41%→-15%) но знак не меняет |
| 1.5 | IV−RV timer | **CLOSED (не валидирован, 2026-09-26)** | — | не монотонен: t3−t1 = −1.6pt |
| 1.1 | Delta-hedged short put | **CLOSED (FAIL G-H1/H3, 2026-09-26)** | — | IV−RV +8.5pt полностью съеден гамма-дренажем |
| 1.2 | Delta-hedged short straddle | ЗАМОРОЖЕНО (механика 1.1 опровергнута) | 10% | тот же гамма-дренаж |
| 1.3 | Var-swap replication | ЗАМОРОЖЕНО (механика 1.1 опровергнута) | 10% | |
| 1.6 | Gamma scalping | BUILD | 30% | microstructure |

## Класс 2: Skew (форма smile)

| # | Стратегия | Статус | Prior | Примечание |
|---|---|---|---|---|
| 2.1 | B2: risk reversal | **CLOSED (FAIL G-B1/B5, 2026-09-26)** | — | call-leg −16.2%: cheap ≠ positive carry |
| 2.2 | B1: short put + DVOL filter | ЗАМОРОЖЕНО до новой механики (A3/B2 FAIL) | 15% | без хеджа не открывать |
| 2.3 | Call overwriting | CLOSED (фаза-0 + B2: call sale только ускоряет тету-дренаж в минус) | — | |
| 2.4 | Butterfly (kurtosis) | BUILD (multi-leg) | 30% | |
| 2.5 | Skew momentum | BUILD | 25% | |
| 2.6 | Skew term structure | FETCH (multi-expiry) | 30% | волна 3 |

## Класс 3: Term structure

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 3.1 | Calendar spread | FETCH (~2–3ч) | 30% |
| 3.2 | Roll-down harvest | FETCH | 30% |
| 3.3 | Front-back IV slope | FETCH | 25% |
| 3.4 | Event-vol | EVENT | 35% |
| 3.5 | Expiry-week pinning | FETCH + OI | 20% |

## Класс 4: Cross-asset (BTC vs ETH)

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 4.1 | **B4: BTC puts / ETH calls** | READ-OUT DONE, пререг отложен | 15% | rich-зона ETH put m0.60–0.75 только 2023+ (+10..15pt); после FAIL 1.1 нужен явный механизм |
| 4.2 | BTC vol / ETH vol spread | FETCH | 35% |
| 4.3 | Cross-skew divergence | FETCH | 35% |
| 4.4 | Vega-neutral short vol | FETCH + BUILD | 30% |
| 4.5 | ETH calls only | FETCH | 35% |

## Класс 5: Greeks-neutral

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 5.1 | Pure vega (delta-hedged) | BUILD (hedging ~100 строк) | 30% |
| 5.2 | Gamma scalping high-RV | BUILD | 25% |
| 5.3 | Vega-gamma neutral | BUILD | 25% |
| 5.4 | Realized-vs-implied skew arb | BUILD | 30% |
| 5.5 | Box spread | arb, likely dead | 5% |

Требование: skew-consistent Greeks (не голый BS), иначе attribution врёт.

## Класс 6: Directional с опционами

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 6.1 | Covered calls | beta, не alpha | 30% |
| 6.2 | Long call в AVSL trend | BUILD (signal+options) | 20% |
| 6.3 | Long put hedge | CLOSED (FAIL ранее) | — |
| 6.4 | Synthetic long (call/put) | READY | 25% |
| 6.5 | Collar | READY | 30% |

## Класс 7: Event-driven

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 7.1 | Pre-halving vol | EVENT (календарь ~1д) | 40% |
| 7.2 | ETH upgrades | EVENT | 35% |
| 7.3 | FOMC / CPI | EVENT | 30% |
| 7.4 | Expiry pinning | FETCH | 25% |
| 7.5 | Post-liquidation IV crush | EVENT + liq data | 35% |

Мало событий = слабая статистика; каждый — отдельный пререг, питание
гейтов не пересматривать.

## Класс 8: Structured / exotic-like

| # | Стратегия | Статус | Prior |
|---|---|---|---|
| 8.1 | Risk-reversal collar | READY | 35% |
| 8.2 | Ratio spread | BUILD | 25% |
| 8.3 | Broken wing butterfly | BUILD | 30% |
| 8.4 | Seagull | BUILD | 30% |
| 8.5 | Jade lizard | READY | 30% |

## Порядок волн

1. **Волна 1 (сейчас, без fetch):** A3 (1.4), B2 (2.1), timer (1.5).
2. **Волна 2:** ETH fetch → skew table → B4 (4.1–4.3).
3. **Волна 3:** multi-expiry fetch → 3.1, 3.3, 2.6.
4. **Волна 4:** hedging engine → 1.1, 1.3, 5.1–5.4.
5. **Волна 5:** event calendar → 7.1, 7.3.

## Опасение (зафиксировано)

30+ стратегий × сегменты = multiple comparison. При α=0.05 и 60
тестах ~3 ложных позитива. Решение: пререг до прогона, один ран,
frozen гейты, failed = closed. Никаких «попробуем ещё вариант».
