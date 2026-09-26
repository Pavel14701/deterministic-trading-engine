# Реестр экспериментов

Легенда: 🟢 PASS/SURVIVOR · 🟡 PASS-латент/диагност. · ⚫ CLOSED ·
⚪ INVALID (результат недействителен) · 🔧 INFRA (без гейтов) ·
⏸ BLOCKED (готов, не запускается).  Полные тексты вердиктов —
`docs/JOURNAL.md`; логи — `runs/`.

# Реестр экспериментов

> **2026-09-25: каталог перестроен по семьям гипотез.**  Маппинг
> старых путей (на них ссылаются журнал и frozen-докстринги):
>
> | старый путь | новый путь |
> |---|---|
> | `experiments/avsr/*` | `experiments/avsl/{channel_breakout, risk_overlay_mirror, portfolio_layer}.py` |
> | `experiments/avsr/corr_check.py` | `experiments/debug/corr_check.py` |
> | `experiments/avsl/donchian_*.py`, `quattro_donchian.py` | `experiments/donchian/` |
> | `experiments/avsl/{_dd_diag, grid_alignment_check, sharpe_postmortem, battery_v2_calibration}.py` | `experiments/debug/` |
> | `experiments/diagnostics/*` | `experiments/debug/` |
> | `experiments/loaders/*` | `experiments/infra/loaders/` |
> | `experiments/sharadar/*` | `experiments/infra/sharadar/` |
> | `experiments/live/*` | `experiments/infra/live/` |

Легенда: 🟢 PASS/SURVIVOR · 🟡 PASS-латент/диагност. · ⚫ CLOSED ·
⚪ INVALID (результат недействителен) · 🔧 INFRA (без гейтов) ·
⏸ BLOCKED (готов, не запускается).  Полные тексты вердиктов —
`docs/JOURNAL.md`; логи — `runs/`.

## Семьи

### avsl — семейство AVS (индекс: `experiments/avsl/README.md`)

Ядро семьи: screen → 4H-аномалия → confirm (сигнал реален, NW-z
+3.31/+3.85, убит DD 61%) → risk-overlay (**S1 PASS 5/5 → passed**)
→ декомпозиция E1–E5 (движок = 4H-сетка + wide-TP, AVSL —
усилитель) → live-scale расширение (⚫ DD-гейты).  Второй слой
семьи (бывш. avsr/): `risk_overlay_mirror` ⚫ (0/4),
`channel_breakout` 🟡 **LATENT PASS 5/5** (Sh 1.13/4.96, DD 24/10%),
`portfolio_layer` ⚫ (PF-G4: структурная 2022–23 дыра).  Фильтры
F1–F7 ⚫; p_* попытки продвижения ⚫; re-test z-score/Donchian/OB ⚫.

### donchian — Donchian breakout (переехал из avsl/)

`donchian_breakout` ⚫ (4H/6 мейджоров: 2/6; 1H/34: recov 16/34 <
17 — семья закрыта полностью), `quattro_donchian` ⚫ (G3 2/6, PF
1.05), `donchian_overlay` ⚫ (entry null-подтверждён, риск не
чинится сайзингом → CLOSED FINAL).

### ob — Order-Block

Детектор + engineering (R1–R3 пресеты) 🔧; E8-retest ⚫ KILL
(0-й перцентиль на 5872 сделках); семья закрыта
(индекс: `experiments/ob/README.md`).

### zscore — z-score входы (индекс: `experiments/zscore/README.md`)

`mfe_mae` 🔧; сигнальная семья ⚫ KILL (режимный lift без
holdout-поддержки, E6).

### ttf — taker-flow divergence

`ttf_v1_check` ⚫ CLOSED (T-G1 0/6, портфель −4.75; gross<0 —
анти-сигнал; turnover 0.4 RT/день не оплачивается).

### carry — funding-carry (индекс: `experiments/carry/README.md`)

`funding_carry_v3` 🟢 PASS с затуханием (13.5→3.75→1.45%/год,
crowding); `p4_carry`/`p4_universe` 🟡 (PASS переклассифицирован в
upper bound); `p4_exec` ⚫ execution-blocked (EX-G2);
`prosp_v2` ⚫ signal-dead (Brier хуже константы, 0/8 фолдов);
`funding_carry`, `funding_carry_v2`, `barrier_prob`, `carry_v3_ci`
— предшественники/диагностика.

### options — Deribit

`strangle_carry` ⚫ SHORT-STRANGLE VOL CARRY CLOSED (VRP +8.6 pts
< хвостовой drain, минус каждый год); `puts_overlay`,
`puts_feasibility`, `puts_subset`, `puts_depth` ⚫ (tails не
оплачиваются премией); `deribit_fetch`, `deribit_probe`,
`dvol_merge`, `skew_probe`, `fetch_puts_trades.sh` 🔧 (skew-таблица
измерена и frozen); `strangle_subset` ⚫.

### fx — FX transfer (пререги у корня)

| модуль | статус | вердикт |
|---|---|---|
| `duka_fetch.py` | 🔧 | Dukascopy 10 пар 2003–2026, ~39k 4H-баров — скачано |
| `fx_avsl_4h.py` | ⚫ | **FAIL one-shot** (Sh 0.01/−0.66; control vol=ones не лучше → прокси не спасает) |
| `fx_avsl_d1.py` | ⚪ + 🔧 | прогон отозван (invalid transfer, timescale ×6); модуль жив как библиотека для stocks-теста |

### stocks — equities transfer

| модуль | статус | вердикт |
|---|---|---|
| `avsl_d1_screen.py` | 🔧/⚪ | screen (12/58); использовать только как библиотеку collect/factor |
| `avsl_d1_transfer.py` | ⚫ | FAIL one-shot (лонги EV +0.27R, EV_orth t+5.2; шорты яд) |
| `longleg_concentration.py` | 🟡 диагност. | декада-однороден (2000s t+2.8), ликвидность-концентрирован (small ≈ 0); UNRESOLVED |

## Инфраструктура (без гейтов)

- `infra/loaders/` — `load_binance`, `load_okx`, `load_yf` 🔧,
  resumable (индекс: `infra/loaders/README.md`)
- `infra/sharadar/` — `fetch_sharadar` ⏸ READY, заблокирован
  решением (ключ не покупается, 2026-09-25); контракт API проверен
  на test-api-key
- `infra/live/` — `parity_check`, `pilot_tracker` 🔧: гейт паритета
  сигнал↔модуль, disaster brake; Phase A paper ≥90д/≥50 сделок
  (индекс: `infra/live/README.md`)

## Отладка и диагностика (без гейтов, вердиктов не дают)

`debug/corr_check` (corr AVSL↔channel 0.63), `debug/battery_v2_calibration`
(калибровка батареи, найденные баги исправлены до вердиктов),
`debug/grid_alignment_check`, `debug/sharpe_postmortem`,
`debug/_dd_diag`, `debug/svd_cached_universe` (rank-one подтверждён:
PC1 66.8%, один фактор > MP), `debug/svd_factors`,
`debug/avs_ob_portfolio_check`, `debug/lam1_crash_check`,
`debug/rsvd2_check`, `debug/ssa_avsl_check`.

## panel — champion-stack (историческое)

Вся папка HISTORICAL: результаты до фикса симулятора D.13g
(gap-through-stop) НЕвалидны как позитивные результаты; kept для
археологии протокола (индекс: `experiments/panel/README.md`).
⚠ IMPORT-UNSAFE: у модулей исполняемый код на уровне модуля
(нет `__main__`-гварда) — при импорте запускается пайплайн/трейнинг.
Архив не трогаем; НЕ импортировать, только читать.

