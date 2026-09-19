# AI Baseline Report — first real-data run (OKX, 7 assets × 4 timeframes)

> **Status: ✅ first full pipeline run (2026-09-18).** Dataset → transformer training →
> backtest vs baselines. Artifacts: `runs/okx7/best.pt`, `runs/okx7/backtest.json`.
> Reproduce: `scripts/prepare_okx_dataset.py` → `scripts/train_okx.py` → `scripts/backtest.py`.

## Setup

- **Data**: OKX, 7 assets (BTC/ETH/SOL/XRP/DOGE/LTC/ADA-USDT), 4 timeframes (1m/5m/15m/1H),
  ~2 years, ~3.3M train rows; 71 features per bar (price + 84-indicator DSL registry subset
  + OB-context features); labels = causal ATR(t-1) TP/SL with `configs/ai.yaml → risk`
  (TP 2.0×ATR, SL 1.5×ATR, max hold 20 bars, commission 0.1% + slippage 0.05% per side).
- **Model**: EntryExitTransformer (TZ-06), seq_len=128, hidden 128, 4 layers,
  5 epochs, batch 64, max_ob 64; deterministic seed.
- **Baselines** (same per-bar features, sklearn / GBM): RandomForest, LogisticRegression,
  Ridge, MLP (64-32), LightGBM, XGBoost, random-signals floor at the transformer's
  signal rate.

## Results (test split, out-of-sample, with costs)

| Model | Trades | ret %/slice (mean) | Action acc | Macro-F1 |
|-------|-------:|-------------------:|-----------:|---------:|
| **transformer** | 204 315 | **-89.8** | **0.719** | **0.710** |
| rf | 155 030 | -88.9 | 0.673 | 0.661 |
| logreg | 131 540 | -83.8 | 0.594 | 0.606 |
| ridge | 134 126 | -84.3 | 0.584 | 0.589 |
| mlp | 146 075 | -86.4 | 0.652 | 0.650 |
| lgbm | 160 680 | -87.3 | 0.703 | 0.695 |
| xgb | 160 408 | -87.2 | 0.703 | 0.690 |
| random (floor) | 185 078 | -90.7 | 0.500 | 0.492 |

Per-base mean return, transformer: 1m −100, 5m −100, 15m −98.3, 1H −60.9
(random floor 1H: −64.2). Full per-(base, asset) detail: `backtest.json → models[*].by_slice`.

## Findings

1. **The transformer is the best classifier**: action acc 0.719 / macro-F1 0.710 vs
   random 0.50/0.49 — the action head learned real structure and consistently beats
   RF, MLP, LightGBM/XGBoost and linear models.
2. **No trading edge yet**: every model loses capital; the transformer is only ~0.9 pp
   better than the random floor on return. **Baseline gate (TZ-04 §4.6.1) is NOT passed** —
   the gate requires > 5–10% Sharpe/PF advantage over the best simple baseline.
3. **Cost churn is the dominant killer**: raw argmax signals fire ~200k trades;
   round-trip costs ≈ 0.3% × trade count ≫ gross alpha. Trade-level win rate on 1m
   is near zero because TP (2×ATR) rarely completes within max_hold=20 bars at 1m.
4. Older timeframes lose less (1H −61% vs 1m −100%) — same per-trade cost, far fewer trades.

## Improvement criteria & next attempts

Decision rule for every attempt: **keep the change only if it beats the current
best simple baseline by > 5–10% on Sharpe or PF out-of-sample with costs**
(baseline gate). Secondary gate: net return per slice > 0, trades per slice ≤ ~1% of bars.

Ordered by expected impact:

1. **Confidence thresholds instead of argmax** — enter only when softmax
   `p(entry) > 0.6–0.7`; expected to cut trades 10–100× and expose true alpha.
2. **Label sparsity via `min_rr`** — currently `min_rr: 1/3` is a no-op (RR is
   always ≈ 1.33 with TP 2×ATR / SL 1.5×ATR). Raising it to ~0.8–1.0 sparsifies
   entry labels. Note: this cleans labels, it does NOT cut inference trades by
   itself — combine with item 1.
3. **Cost-sensitivity study** — rerun the comparison with commission = 0 and
   commission = 0.02%: if the transformer's edge appears gross but dies net,
   the problem is trade frequency, not signal quality.
4. **Horizon alignment** — `max_bars_hold` / TP-SL multipliers must scale with the
   timeframe (1m with hold=20 bars makes TP 2×ATR unreachable); per-base risk configs.
5. **DSL-driven indicator-config search** — sweep indicator parameter sets through the
   DSL registry (cache-key already covers all params, TZ-03): e.g. ATR period ∈ {7, 14, 28},
   RSI/MACD/ADX variants, Entropy/Z-Score thresholds à la SIV (`dev_docs/strategy.md`).
   **Staged to keep it cheap** (a full prepare+train+backtest cycle is ~3 h, so never
   search brute-force):
   - stage 0 (minutes, no model): label statistics per candidate config —
     TP-first rate net of costs and expected RR; drop configs with negative
     label expectancy before any training;
   - stage 1 (~5 min): LightGBM as a proxy model, gate on acc/F1;
   - stage 2 (~20 min): short transformer run (1–2 epochs, 1–2 assets);
   - stage 3 (~3 h): full run only for survivors.
   Accept only gate-passing configs; prefer configs that raise per-trade edge
   rather than trade count.
   **Registered hypothesis (owner's field observation): AVSL fast/slow inversion —**
   long period < short period with large values ~134/52 makes the AVSL/AVSR levels
   wider and, empirically, better support/resistance. Cheap to test at stages 0–1;
   must pass the out-of-sample gate like any other candidate (personal observations
   are hypotheses, not facts).
6. **Per-base feature hygiene** — exclude neutral-filled HTF columns on younger bases
   (they are 10.0/0.0-filled in training and test); or train per-base heads.
7. **OB-encoder batching + <5 ms inference** (already on the TZ-06 list) — needed for
   the live contour, orthogonal to edge.
8. **Self-training round + calibration check** (TZ-06 pseudo-labelling) — verify
   `predict_p_win` calibration before using it as a filter in `infer --ml`.
