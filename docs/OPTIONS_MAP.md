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

## Приложение 2: очередь нетронутых треков (2026-09-26, frozen)

Развёртка приложения 1 в план: каждый пункт закрывается одним
раном. Структура карточки: данные -> prereg -> gates -> prior ->
стоимость -> блокер/решение. Дисциплина та же: пререг ДО кода,
один ран, failed = closed. Порядок запуска -- раздел "Очередь".

### Класс A: deployable beta (не alpha)

**A1. Covered calls (D1).**
Гипотеза: BTC long + систематическая продажа OTM calls даёт yield
поверх beta. Данные: есть. Движок: есть (strangle_runner без put
ноги). Prereg: BTC spot 1.0 notional; short call 30d, delta 0.20-0.30
(m ~ 1.10-1.15); monthly roll; haircut 25%; 2021-04..2026-09.
Gates: G-D1a Sharpe >= 0.8 (beta, не alpha); G-D1b DD <= 40%;
G-D1c Calmar портфеля > Calmar BTC buy-hold; G-D1d yield >= 2%
годовых. Read-out: cumulative vs BTC, yield by year, capped-upside
frequency. Prior 30%. Стоимость 2-3 ч. Если не бьёт buy-hold по
Calmar -- это BTC с косметикой, не стратегия.

### Класс B: event-driven

**B1. Wave 5 events.**
Гипотеза: IV crush вокруг известных событий; short vol T-1 -> T+1.
Данные: календаря НЕТ -- блокер. События-кандидаты: halvings,
ETH Merge/Shanghai, FOMC (~8/год), CPI (~12/год), Deribit monthly
expiry. Prereg: вход T-1, выход T+1, short strangle/straddle,
фильтр IV pct > 50, hold 2-3d. Gates: G-EV1 Sharpe >= 1.0;
G-EV2 DD <= 20%; G-EV3 n >= 30 событий; G-EV4 positive EV на 2 из 3
type. Prior 25-35%. Стоимость: 1д календарь + 1д ран. Календаря
нет -- не строить (p-hacking source).

**B2. Post-liquidation IV crush.**
Гипотеза: после каскада ликвидаций RV/IV spike -> crush; short vol
на T+1. Данные: liquidation data (Coinglass free tier?) -- НЕ
проверено. Prereg: trigger 24h liq > 3x trailing median; вход T+1
close, short strangle 7d; выход at expiry/+3d. Gates: G-LQ1
Sharpe >= 1.0; G-LQ2 n >= 20; G-LQ3 DD <= 25%. Prior 20-30%.
Стоимость 2-3д. Риск: событий мало, n < 20 -> insufficient.

### Класс C: order flow / microstructure

**C1. Dealer gamma estimation (GEX).**
Гипотеза: GEX предсказывает spot-поведение (positive GEX -> mean
reversion, negative -> trending). Данные: OI by strike+expiry --
Deribit API, НЕ скачано. Prereg: GEX = sum(gamma*OI*spot^2*0.01)
by strike; тотал GEX, zero-gamma level. Read-out: IC(GEX, fwd ret)
при h {1,3,6,24}ч; conditional AVSL EV по терцилям GEX. Gates
(если пререг): G-GEX1 IC > 0.05, t > 2; G-GEX2 EV spread > 0.15R;
G-GEX3 стабильность PRIMARY/F3. Prior 20-25%. Стоимость 2-3д
(fetch OI + compute). Риск: в equities сигнал известен, крипто-OI
структура другая -- возможен trap.

**C2. Options taker flow.**
Гипотеза: агрессивные покупки calls vs puts предсказывают spot.
Данные: ЕСТЬ -- в trades есть direction и iv. Prereg: flow =
(buy call vol - sell call vol) - (buy put vol - sell put vol),
агрегаты 1H/4H/24H; сигнал: extreme flow (>90 pct) -> direction.
Gates: G-OF1 IC > 0.05; G-OF2 EV spread > 0.15R; G-OF3 n >= 100
extreme events. Prior 15-25%. Стоимость 1-2д. Риск: vol-proxy
trap -- flow может коррелировать с RV.

### Класс D: cross-asset / relative

**D1. BTC/ETH IV spread.**
Гипотеза: DVOL_BTC - DVOL_ETH mean-reverting; торгуем экстремум
(|z| > 2, окно 60d): short vol на rich, long на cheap, delta-
hedged; hold до реверса или max 30d. Данные: ЕСТЬ. Gates:
G-IV1 Sharpe >= 1.0; G-IV2 n >= 30; G-IV3 DD <= 20%. Prior
20-25%. Стоимость 3-4д (hedge engine есть). Риск: корреляция
IV ~0.9, после costs spread может быть слишком узким.

**D2. BTC put skew / ETH call skew spread.**
Гипотеза: skew divergence B4-типа: long ETH call (m 1.10-1.15) +
short BTC put (m 0.85-0.90), vega-neutral, monthly roll. Gates:
G-SK1 Sharpe >= 1.0; G-SK2 vega-net ~ 0; G-SK3 PnL не объясняется
BTC direction. Prior 10% (ETH skew режимный). Стоимость 2д.
Решение: только если B/C закрыты и есть свободный ресурс.

### Класс E: инфраструктурные

**E1. Multi-expiry fetcher + полная term structure.**
Read-out, не стратегия: IV кривая по тенорам 7d/30d/60d/90d,
slope/curvature/dynamics, predictive content для spot и RV.
Gates нет. Prior 10% (wave-3: покрытие 2-5 пар/год). Стоимость
2д. Только если предыдущие треки закрыты.

**E2. Realistic cost model.**
Read-out: bid-ask by moneyness/TTM/DVOL-режим, market impact
proxy (size vs book depth). Нужны order book snapshots. Gates
нет. Полезно всем стратегиям, alpha не открывает. Стоимость 2д.
Делать в конце.

**E3. Event calendar.**
Инфра под B1: halving dates, FOMC schedule, CPI releases из
публичных источников. Gates нет. Стоимость 1д. Делать ДО B1 --
без календаря Wave 5 не открывается.

### Класс F: altcoin options

**F1. SOL / XRP options.**
Гипотеза: меньшая эффективность рынка -> больше dislocation.
Данные: Deribit SOL options с 2024+? НЕ проверено. Prereg:
аналог B1 (short put с фильтром) на SOL. Gates: G-A1 Sharpe >=
1.0; G-A2 n >= 50; G-A3 DD <= 25%. Prior 15%. Стоимость 2-3д.
Только если данные есть и предыдущие треки закрыты.

### Очередь запуска (frozen)

| # | трек | prior | стоимость | блокер |
|---|---|---|---|---|
| 1 | A1 covered calls | 30% | 2-3 ч | нет |
| 2 | E3 event calendar | N/A | 1д | нет |
| 3 | B1 wave 5 events | 25-35% | 1д run | календарь (= E3) |
| 4 | C2 options taker flow | 15-25% | 1-2д | нет |
| 5 | C1 dealer gamma (GEX) | 20-25% | 2-3д | OI fetch |
| 6 | D1 BTC/ETH IV spread | 20-25% | 3-4д | нет (engine есть) |

НЕ делать: D2 (10%), E1 (10%), F1 (данных нет, не проверено),
B2 (liq data не подтверждены), E2 (не alpha). Приоритет:
A1 почти наверняка бета, не alpha; B1 и C1 -- единственные с
шансом на новый кластер; C2 дёшев, но вероятен vol-proxy trap.

**Гейт очереди: сначала component diagnostic** -- единственная
открытая alpha-линия; всё выше -- параллельные треки, не
конкурируют за неё.
