# component_diagnostic — покомпонентная диагностическая прогностика (crypto 4H)

**Пререг:** `PREREG_COMPONENT_DIAG_2026-09-26.md` (frozen, commit
`074c847`, 2026-09-26 — до написания кода и до прогона).
**Статус:** measurement-only. Без гейтов, без смешивания компонент,
без изменений в `engine/passed/*`.

## Что измеряется

Предсказательное содержимое каждой компоненты **отдельно** против
форвардных лог-доходностей (h = 1, 3, 6, 12, 24 × 4H): IC (Spearman),
NW t-stat, decile spread (block bootstrap, seed 11), условный EV
frozen AVSL-леджера по тертилям компоненты на входе, перекрытие с
AVSL arm state, стабильность PRIMARY/F3.

| компонента | источник | покрытие |
|---|---|---|
| C1 Hurst (DFA-1, W=100/200) | price 4H | полная история |
| C2 funding (raw/z30/hi30) | `data/funding_binance` | с 2023-09 |
| C3 OI (chg_1/chg_24/z30) | `data/binance/oi_*_1h` | **только 2026-08-21..09-21** |
| C4 liquidations | — | SKIP: нет бесплатных данных |
| C5 taker imbalance (tbi_1/tbi_6) | klines `taker_buy_volume` | полная |
| C6 BTC lead-lag (lag 1/2/3) | BTC 4H ret | полная (алты) |

## Критерий follow-up (prereg §7, против multiple comparisons)

Все четыре: знак IC согласован ≥ 8/10 активов; знак согласован
PRIMARY/F3 (≥ 80%); decile-распределение монотонно (Spearman децилей
≥ 0.9, ≥ 50% ячеек); условный EV спред > 0.15R. Иначе —
`descriptive`, направление закрывается.

## История версий

| версия | дата | изменение |
|---|---|---|
| v1.0.0 | 2026-09-26 | первый frozen-прогон по пререгу 074c847; результат: `runs/component_diagnostic.log` |
