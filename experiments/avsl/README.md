# avsl — AVSL / Donchian entry-signal family (all CLOSED)

All: gross edge ≈ 0 net of costs.

Run: `uv run python -m experiments.avsl.<name> [args]`

| module | verdict | what it decided |
|---|---|---|
| `avsl_baseline` | ⚫ | AVSL×SMA cross, BTC 15m, pre-registered: EV negative; pocket did not replicate on holdout |
| `avsl_price_cross` | ⚫ | price×AVSL cross, normal + reverse arms: 1-2/4 assets positive only. **+ ATR-stop RR audit (2026-09-21):** tight-stop variant (stop=1×ATR(14), TP 3/5/8R, `avsl_price_cross_atr.log`) tested as a "RR-profile" rescue hypothesis — **dead**: net>0 on train AND test in **0/10 assets in every (arm×TP) cell**; gross ≈ 0 with WR sitting exactly at break-even (25%/17%/12% vs 25%/16.7%/11.1%) = no post-entry drift; best cell (AVAX TRAIN 8R net +0.119, n=1634) ≈ 1.6σ, insignificant under 120-cell multiple testing, and AVAX TEST is negative on all TP. No new prereg per decision rule ("0-3/10 → beta, close") |
| `avsl_trailing` | ⚫ | 3 trailing-stop variants: none beat the static benchmark |
| `donchian_breakout` | ⚫ FAIL | DC breakout: 4H/6 majors — test positive 2/6 (kill ≤2); 1H/34-asset sweep — recov gate 16/34 < 17 (`donchian_1h_34_prereg.log`) → **Donchian family closed entirely** |
| `quattro_donchian` | ⚫ FAIL | DC20+SMA200+1.2ATR+2.75ATR trail: G3 recov 2/6, pooled PF 1.05. Declared post-hoc one-shot, no tuning |
| `avsl_cross_tf` | ⚫ FAIL per prereg — **but 4H anomaly on record** | High-TF single shot (1H+4H, stop = max(\|close−line\|, 2×ATR), TP 3/5/8R, horizon 500, normal arm). **1H FAIL**: WR3R 25.4/28.6% ≈ break-even → gross ≈ 0. **4H FAIL by 1.6pp**: G1 consistency 10/10 (train, 5R), 7-9/10 test; fees 0.02R; **но WR3R 28.4%/30.0% vs BE 25% = первый в проекте конфиг с gross-эджем значимо выше нуля в обоих сегментах (~3.5σ)**. Family closed per kill rule; revival only via new dated prereg. Evidence: `runs/avsl_cross_tf.log` |
| `avsl_cross_confirm` | ⚫ CLOSED FINAL — **сигнал реален, риск нет** | Confirm по полной батарее: **G6 NW-z +3.31/+3.85 (PASS — эдж не inflation), G1' Sharpe_NW 1.33/2.05 (PASS), G3 long+short оба + (PASS), G4 F3 3/3 (PASS), G5' bootstrap CI искл. 0 в обоих сегментах (PASS), G2' DD 61% vs кап 25% (FAIL — медвежий 2022, подтверждено двумя конструкциями)**. Первый статистически реальный сигнал за проект; убит риск-профилем при 1%/слот. Revival только как новая гипотеза (risk-overlay/sizing). Evidence: `runs/avsl_cross_confirm.log`, `runs/avsl_cross_confirm2.log` |
| `risk_overlay` | 🟢 S1 VOL-TARGET PASSES 5/5 | Pre-reg `b6005ca` (S1–S4, G1'–G5', risk-first). **S1** (size=clip(0.20/rv100, .25, 2.0)): Sharpe_NW **1.50/2.84**, DD **22%/12%**, EV +0.17/+0.33R, G4' 9/10 и 7/10, CI искл. 0 — все гейты зелёные, Sharpe ВЫШЕ базового. **S2** FAIL (DD 57/28%), **S3** FAIL (кап конкурентности уничтожает PRIMARY-эдж: Sh 0.22, EV +0.02R — кластерные входы и несут edge), **S4** FAIL (аналогично). Вердикт risk-first: единственный passer → **S1**. Капы конкурентности — запрещены для наследников. Evidence: `runs/risk_overlay.log`. **→ посажен в ядро: [`engine/passed/avsl_cross_s1.py`](../../engine/passed/avsl_cross_s1.py) + [полная дока](../../engine/passed/README.md)** |
| `ablation_entry` (E1) | 🟡 FAIL per prereg — **edge в geometry, не в entry** | Arm A (frozen) vs 100 random-entry draws с matched count/side-ratio: PRIMARY A +0.172R vs random +0.135±0.044 (81-й процентиль — FAIL E1a/E1b), F3 +0.335 vs +0.168 (100-й pct — PASS). Random 4H-геометрия сама по себе даёт +0.135/+0.168R — **RR-профиль и есть движок эджа**; entry добавляет lift только в F3. Arm C (+100 баров задержка): +0.227R PRIMARY (описательно, не гейт). Модуль PASS не аннулирован; E3 повышен в приоритете. Evidence: `runs/ablation_entry.log` |
| `ablation_rr` (E3) | 🟡 GATE FAIL только B/F3 — **wide TP — абсолютное требование, stop floor критичен только на PRIMARY** | C1 (TP 1R): **−0.020/+0.011** — мёртв; C15 (1.5R): +0.022/+0.020 — мёртв; null'ы тоже ~0 → **асимметрия TP = сам движок**. B (1×ATR): +0.037 PRIMARY (коллапс, null −0.013) но +0.293 F3 → floor критичен только на PRIMARY. **E (3×ATR): +0.175/+0.456 — не хуже frozen** (магии в 2×/line нет, важно «не слишком тесно»). **D (reverse-cross trailing): +0.447/+0.422 бьёт frozen в обоих сегментах**, но PRIMARY почти весь null (+0.415±0.124). Anti-cherry-pick: trailing-вариант = новый прег. Evidence: `runs/ablation_rr.log` (+`_d`) |
| `ablation_regime` (E5) | 🟡 descriptive — **edge НЕ универсален: low-vol + 2025+** | Срезы A-trades vs matched-null. **F3 entry-lift почти целиком из ≥2025** (+0.412 EV, lift +0.251, n=665 из 822), а 2023-24 на holdout **мёртв** (+0.007, lift −0.204) → «holdout-подтверждение» = «подтверждение текущим режимом», caveat для live-прега. **Low-ATR концентрация на F3: lift +0.502** (atr_lo, z 3.8) vs +0.067 (atr_hi); на PRIMARY знак обратный. Тренд: lift есть и в up (+0.19) и в down (+0.11) → не тренд-фолловер; фильтр не оправдан. Кандидат-фильтр «skip high-vol» = только новый прег. Evidence: `runs/ablation_regime.log` |
| `ablation_tf` (E2) | ✅ PASS — **эдж 4H-специфичен** | Та же frozen-система на 1D: **−0.018/+0.013** (n=166/138, z≈0) — мёртв; 1D-null +0.134±0.133/−0.071±0.154, entry на **11-м перцентиле** 1D-null на PRIMARY (cross-entry хуже random на 1D). Гейт 4H > 1D + 0.05R: PASS (+0.19R/+0.32R запаса). Не «TF-скейл drift capture» — движок именно 4H. Sanity: 4H воспроизвёл E1 бит-в-бит (MATCH). Caveat: 1D n мал, null ±0.13–0.15. Evidence: `runs/ablation_tf.log` |
| `ablation_sizing` (E4) | ✅ PASS — **vol-timing несёт информацию, не только de-lever** | A unsized: Sharpe 1.33/2.05, **DD 61%/38%**; B S1: **1.50/2.84, DD 22%/12%** (sanity бит-в-бит с frozen verdict); D 0.33: 1.33/2.05, DD 27%/14%; C permuted: 1.26±0.18 / 1.98±0.34. Гейт B > C + 0.2: PASS, но на PRIMARY **впритык** (B−C = +0.24 при требовании +0.20, шум C ±0.18) → vol-timing-информация на PRIMARY не установлена твёрдо, на F3 — да (+0.86). S1 оставляем frozen; в live-прег — read-out corr(realized vol, size). Evidence: `runs/ablation_sizing.log` |

## Теория метода (E1–E5, 2026-09-22) — карта эджа

```
Движок:    4H grid + wide-TP asymmetry   (E2, E3)
Амплиф.:   AVSL cross, только 4H         (E1, E2)
Режим:     low-vol + 2025+               (E5)
Sizing:    de-lever + vol-timing         (E4, на PRIMARY погранично)
```

**Стандарты (binding для всех будущих треков):**
- **Null per-geometry**: сигнал обязан бить matched random-geometry
  null (тот же count, side ratio, geometry; 100 draws, seeds 0..99):
  EV > null + 0.05R **и** ≥ 95-й перцентиль.
- **Wide TP обязателен**: тест на 1R/1.5R TP пуст по построению (E3).
- **4H grid — арена по умолчанию**; другой TF требует своего null (E2).
- Старые kill'ы (z-score, Donchian, OB) выданы при узких TP —
  **ненадёжны**; re-test при wide-TP = новый прег, не «revival».

**Риски для live (read-outs, не фильтры):** режимный развал
(2023-24-like), vol-разворот; rolling Sharpe 90d, ATR percentile,
corr(vol, size); disaster-brake — через прег.

## Re-testы dead pool при wide-TP (E6–E8, прег 51448f7)

| тест | вердикт | суть |
|---|---|---|
| E6 z-score MOM (z28 4H) | ❌ FAIL (kill) | PRIMARY: +0.155 vs null +0.061±0.025, 100-й pct, всё PASS — но F3: +0.077 vs null +0.085, **41-й pct**, CI накрывает 0 → lift режимный без holdout-поддержки (хуже AVSL, у которого ≥2025 спасает). Старый kill подтверждён и в новом фрейме. Evidence: `runs/retest_e6.log` |
| E7 Donchian(20)+EMA200 | 🟡 FAIL по батарее, **но не kill** — сигнал настоящий | **E-a/E-b PASS на ОБОИХ сегментах**: +0.221 vs null +0.096 (100-й pct) / +0.185 vs +0.096 (**98-й pct на holdout**), CI>0. Падает только риск: DD 29%/38% при S1 (вход в 3.2× плотнее AVSL, кластеры в трендах). Паттерн AVSL-истории наоборот: сигнал есть, sizing-оверлей нужен. → зарегистрирован путь: risk-only overlay прег для Donchian-4H; при PASS 5/5 — второй подтверждённый трек и первая репликация МЕТОДА. Evidence: `runs/retest_e7.log` |
| E8 OB-retest | ⏸ POSTPONED | По прегу: порт детектора блоков на 4H требует проверки 1:1 на общей подвыборке до запуска; не выполнено — отложен, не аппроксимирован |

Семейная мультипликативность: исполнено 2/3, 0 PASS — бюджет ложных
срабатываний не потрачен.

### Donchian-4H risk-overlay (прег до кода, commit до прогона) — ❌ CLOSED FINAL

| конфиг | PRIMARY | F3 | гейты |
|---|---|---|---|
| S1 (=engine) | Sh 1.42, DD 29%, EV +0.22 | Sh 1.53, DD 38%, EV +0.18 | FAIL (DD) — sanity бит-в-бит с E7 |
| S2 (0.15/rv, 0.15–1.5) | Sh 1.50, **DD 20%**, EV +0.22 — всё PASS | Sh 1.50, **DD 30%**, EV +0.18 | FAIL (DD, 5 п.п. не хватило) |
| S3 (S1+cap) | взято 156/9530; Sh 1.41, DD 3%, EV +0.89 | **Sh 0.63, EV −0.02**, pos 5 | FAIL |
| S4 (S2+cap) | Sh 1.44, DD 2% | Sh 0.60, EV −0.08 | FAIL |
| S5 (S2 × 0.5 при ATR_pct>80) | Sh 1.55, DD 19% — всё PASS | Sh 1.18, **DD 31%** | FAIL (DD) |

**Трек закрыт финально по прегу** (entry остаётся null-confirmed). Три новых факта метода:
1. **Токсичность cap реплицировалась** на Donchian (S3/S4 убивают F3, как на AVSL) — теперь общий закон: кластеры несут holdout-эдж на обоих entries.
2. **Donchian DD не чинится sizing'ом**: S2/S5 чинят PRIMARY (19–20%), F3 вязнет на 30–31% — holdout-DD идёт из кластерных тренд-входов 2025+ с **низкой** realized vol на входе (та же переменная, что несёт lift из E5, defeats сайзер). Сигнал и риск связаны через одну переменную.
3. **Граница метода измерена**: entry-lift переносится между entries (AVSL, Donchian), risk-совместимость — нет. Null-подтверждение необходимо, но недостаточно; второй гейт — управляемость DD сайзингом.

Evidence: `runs/donchian_overlay.log`. Подтверждённые треки: AVSL-cross 4H S1.
