# avsl — AVSL / Donchian entry-signal family (all CLOSED)

All: gross edge ≈ 0 net of costs.

Run: `uv run python -m experiments.avsl.<name> [args]`

| module | verdict | what it decided |
|---|---|---|
| `avsl_baseline` | ⚫ | AVSL×SMA cross, BTC 15m, pre-registered: EV negative; pocket did not replicate on holdout |
| `avsl_price_cross` | ⚫ | price×AVSL cross, normal + reverse arms: 1-2/4 assets positive only |
| `avsl_trailing` | ⚫ | 3 trailing-stop variants: none beat the static benchmark |
| `donchian_breakout` | ⚫ FAIL | DC breakout: 4H/6 majors — test positive 2/6 (kill ≤2); 1H/34-asset sweep — recov gate 16/34 < 17 (`donchian_1h_34_prereg.log`) → **Donchian family closed entirely** |
| `quattro_donchian` | ⚫ FAIL | DC20+SMA200+1.2ATR+2.75ATR trail: G3 recov 2/6, pooled PF 1.05. Declared post-hoc one-shot, no tuning |
