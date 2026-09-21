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
