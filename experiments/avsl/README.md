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
