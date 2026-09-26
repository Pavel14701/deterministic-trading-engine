# Реестр экспериментов

Легенда: 🟢 PASS/SURVIVOR · 🟡 PASS-латент/диагност. · ⚫ CLOSED ·
⚪ INVALID (результат недействителен) · 🔧 INFRA (без гейтов) ·
⏸ BLOCKED (готов, не запускается).  Полные тексты вердиктов —
`docs/JOURNAL.md`; логи — `runs/`.

## avsl — AVSL/Donchian входная семья (индекс: `experiments/avsl/README.md`)

Ключевые вердикты: baseline/price-cross/trailing/Donchian —
gross ≈ 0 нетто; `avsl_cross_tf` — 4H-аномалия на записи;
`avsl_cross_confirm` — сигнал реален (NW-z +3.31/+3.85), убит DD 61%;
`risk_overlay` — 🟢 **S1 PASS 5/5 → посажен в passed**;
`ablation_entry/rr/regime/sizing/tf` (E1–E5) — 🟡 движок = 4H-сетка +
wide-TP, AVSL — усилитель, только 4H; фильтры F1–F7 — ⚫; re-test
(z-score, Donchian overlay, OB-retest) — ⚫ KILL.
Live-scale: `avsl_extended_universe` ⚫ (edge есть, DD-гейты нет).

| статус | модули |
|---|---|
| 🟢 | `risk_overlay` (S1 → passed) |
| 🟡 | `ablation_entry`, `ablation_rr`, `ablation_regime`, `ablation_sizing`, `ablation_tf`, `ps1_forensic`, `grid_alignment_check` |
| ⚫ | `avsl_baseline`, `avsl_price_cross`, `avsl_trailing`, `avsl_15m_wide_tp`, `avsl_cross_confirm` (закрыт после промоушена), `avsl_cross_confirm2`, `avsl_cross_tf`, `avsl_extended_universe`, `donchian_breakout`, `donchian_overlay`, `quattro_donchian`, `retest_entry`, `filter_f1_htf` … `filter_f7_structure`, `p_long_only`, `p_short_revival`, `p_s1_1`, `sharpe_postmortem`, `shorts_hypotheses`, `tp1_revcross`, `tp1_checks`, `tp1_mirror`, `_dd_diag` |
| 🔧 | `battery_v2_calibration`, `avsl_baseline` (инфра-часть) |

## avsr — AVS-зеркало и канал

| модуль | статус | вердикт |
|---|---|---|
| `channel_breakout.py` | 🟡 LATENT | **AVS-channel S1 PASS 5/5** (Sh 1.13/4.96, DD 24/10%, EV +0.22/+0.39R); R = ширина канала |
| `corr_check.py` | 🟡 диагност. | corr(AVSL, channel) ≈ 0.63; 50/50: DD 26.7R vs 34.1/38.0R |
| `portfolio_layer.py` | ⚫ | PF-G4 FAIL: 12m-дыра 2022–23 структурна; NW lags≥500 дегенеративен на sawtooth |
| `risk_overlay_mirror.py` | ⚫ | AVSR-mirror 0/4 (PRIMARY копия AVSL, F3-ноги нет) |

## carry — funding-carry цепочка (индекс: `experiments/carry/README.md`)

`funding_carry_v3` 🟢 PASS с затуханием (13.5→3.75→1.45%/год,
crowding); `p4_carry`/`p4_universe` 🟡 (PASS переклассифицирован в
upper bound); `p4_exec` ⚫ execution-blocked (EX-G2);
`prosp_v2` ⚫ signal-dead (Brier хуже константы, 0/8 фолдов);
`funding_carry`, `funding_carry_v2`, `barrier_prob`, `carry_v3_ci`,
`p4_carry` — предшественники/диагностика.

## diagnostics — разовые проверки

`svd_cached_universe` ⚫ rank-one подтверждён (PC1 66.8%, один
фактор > MP); `svd_factors` 🔧; `avs_ob_portfolio_check`,
`lam1_crash_check`, `rsvd2_check`, `ssa_avsl_check` — 🟡 диагност.

## fx — FX transfer (индекс: нет; см. пререги у корня)

| модуль | статус | вердикт |
|---|---|---|
| `duka_fetch.py` | 🔧 | Dukascopy 10 пар 2003–2026, ~39k 4H-баров — скачано |
| `fx_avsl_4h.py` | ⚫ | **FAIL one-shot** (Sh 0.01/−0.66; control vol=ones не лучше → прокси не спасает) |
| `fx_avsl_d1.py` | ⚪ + 🔧 | прогон отозван (invalid transfer, timescale ×6); модуль жив как библиотека для stocks-теста |

## live — live-scale инфраструктура AVSL (индекс: `experiments/live/README.md`)

`parity_check.py`, `pilot_tracker.py` 🔧 — гейт паритета
сигнал↔модуль, disaster brake; Phase A paper ≥90д/≥50 сделок.

## loaders — данные (индекс: `experiments/loaders/README.md`)

`load_binance.py`, `load_okx.py`, `load_yf.py` 🔧; всё resumable.

## ob — Order-Block (индекс: `experiments/ob/README.md`)

Детектор + engineering (R1–R3 пресеты) 🔧; E8-retest ⚫ KILL
(0-й перцентиль на 5872 сделках); вся семья закрыта.

## options — Deribit

`strangle_carry` ⚫ SHORT-STRANGLE VOL CARRY CLOSED (VRP +8.6 pts
< хвостовой drain, минус каждый год); `puts_overlay`,
`puts_feasibility`, `puts_subset`, `puts_depth` ⚫ (tails не
оплачиваются премией); `deribit_fetch`, `deribit_probe`,
`dvol_merge`, `skew_probe` 🔧 (skew-таблица измерена и frozen);
`strangle_subset` ⚫; `fetch_puts_trades.sh` 🔧.

## panel — champion-stack (историческое)

Вся папка HISTORICAL: результаты до фикса симулятора D.13g
(gap-through-stop) НЕвалидны как позитивные результаты; kept для
археологии протокола (индекс: `experiments/panel/README.md`).
⚠ IMPORT-UNSAFE: у модулей исполняемый код на уровне модуля
(нет `__main__`-гварда) — при импорте запускается пайплайн/трейнинг.
Архив не трогаем; НЕ импортировать, только читать.

## sharadar — equities PIT

`fetch_sharadar.py` ⏸ READY, заблокирован решением (ключ не
покупается, 2026-09-25); контракт API проверен на test-api-key.

## stocks — equities transfer

| модуль | статус | вердикт |
|---|---|---|
| `avsl_d1_screen.py` | 🔧/⚪ | screen (12/58); использовать только как библиотеку collect/factor |
| `avsl_d1_transfer.py` | ⚫ | FAIL one-shot (лонги EV +0.27R, EV_orth t+5.2; шорты яд) |
| `longleg_concentration.py` | 🟡 диагност. | декада-однороден (2000s t+2.8), ликвидность-концентрирован (small ≈ 0); UNRESOLVED |

## ttf — taker-flow divergence

`ttf_v1_check.py` ⚫ CLOSED (T-G1 0/6, портфель −4.75; gross<0 —
анти-сигнал; turnover 0.4 RT/день не оплачивается).

## zscore — z-score входы (индекс: `experiments/zscore/README.md`)

`mfe_mae` 🔧; сигнальная семья ⚫ KILL (режимный lift без
holdout-поддержки, E6).
