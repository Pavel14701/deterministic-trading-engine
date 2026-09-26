# Карта опционных стратегий (registered backlog, 2026-09-26)

> **СТАТУС 2026-09-26:** alpha-трек закрыт (conditional P&L diagnostic, 0 ALIVE).
> Статусы/priors строк ниже НЕактуальны для prioritization; действующий
> frozen-инвентарь оставшегося -- в приложении в конце файла.


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
| 3.1 | Calendar spread (term slope) | READ-OUT DONE, структуры нет | 10% | slope +1.1pt мед., знак нестабилен (n=22); предиктивность rho=-0.32 есть, но не находит VRP |
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

## Приложение: инвентарь несделанного (2026-09-26, frozen)

Зафиксировано после закрытия трека (conditional P&L diagnostic,
0 ALIVE). Это КАРТА НЕСДЕЛАННОГО: каждый пункт -- либо в
опровергнутом механизме, либо требует данных/инфры, которых нет,
либо prior <=15%. Открытие любого пункта = новая строка с новым
пререгом, НЕ рестарт.

### A. Не тестированные стратегии

| Стратегия | Prior | Почему не делали / что нужно |
|---|---|---|
| Covered calls (D1) | 30% (beta) | Не alpha-претензия; нужен тест vs BTC buy-hold |
| Event-driven (halving, upgrades, FOMC) | 25-35% | Нет календаря; строить под диаг = p-hacking |
| Options flow / dealer gamma | 20-25% | Нет order-flow данных |
| Altcoin options (SOL, XRP) | 15% | Нет данных; Deribit fetch возможен |
| Long options в trend | 15% | Нужен direction edge, которого нет |
| Realized vs implied skew | 15% | После 1.1 -- тот же gamma drain |
| Expiry pinning / max pain | 15% | Нет OI by strike |
| Risk reversal с фильтром (B2 v2) | 15% | Обе ноги favorable, но 1.1 + 0 ALIVE |
| Short put с фильтром (B1 v2) | 10-15% | Put rich только 2023+, режимная |
| Ratio spreads / jade lizard / seagull / collar | 10-15% | Комбинации опровергнутых компонент |
| Call overwriting / short call only | 10% | Продажа дешёвой премии; U2: все терцили отрицательны |
| Butterfly / iron condor / broken wing | 10% | То же |
| Cross-asset BTC/ETH (B4) | 10% | ETH skew режимный, пересечение богатых зон = 1 год из 6 |
| Vol-of-vol / dispersion | 10% | Нужны инфра + данные |
| Gamma scalping | 10% | 1.1 показал gamma drain |
| Delta-hedged straddle (1.2) / var-swap (1.3) | 10% | Заморожены после 1.1 |
| Calendar spreads | 10% | Wave-3 read-out: структуры нет |
| Deribit vs other venues arb | 5% | Нет данных других venue |

### B. Не сделанные диагностики

PCA/факторы IV поверхности; динамика поверхности как предиктор;
dealer gamma exposure; options taker imbalance; полная кривая
term structure (3+ теноров); skew term structure; implied
correlation; arbitrage-проверки поверхности; jump/tail-hedging
cost; модель транзакционных издержек (реальные филлы/spread,
сейчас только haircut 25%); live/paper торговля.

### C. Не построенная инфраструктура

Real-time options feed; execution simulator с order book;
delta-hedging по real prints (сейчас BS-delta); multi-expiry
fetcher; event calendar; cross-venue data.

### D. Решение

Опционный трек как источник **alpha** закрыт (четыре независимых
опровержения: 1.1, wave-3 slope, eth_skew режимность, conditional
0 ALIVE). Осталось: D1 (beta overlay, отдельное решение), события
(только при готовом календаре + механизме, отличном от
vol-предикторов), flow/dealer-gamma (только при появлении данных).
Ресурсы трека сохранены: hedge engine (300 тестов), ETH trades
327k, DVOL/RV-инфраструктура, все логи one-shot ранов.
