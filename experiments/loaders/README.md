# loaders — data loaders & dataset builders (INFRA)

No gates; safe to re-run — every cache is a resumable page-cache.

Run: `uv run python -m experiments.loaders.<name> [args]`

| module | what it produces | notes |
|---|---|---|
| `load_okx` | `data/okx21/raw_{SYM}-USDT_{TF}.parquet` — OKX OHLCV, 34 assets, 15m/1H/4H/1D | resumable, depth grows run over run |
| `load_yf` | `data/yf/` — Yahoo fallback in the okx21 schema | 15m→60d, 1h→730d limits |
| `load_binance` | `data/binance/kl_*` (1H klines **with taker_buy_volume**, ~6.8y) and `data/binance/oi_*` (OI, **merge-append**: run WEEKLY, hard limit 30d, to accumulate) | the TTF v1 / ProSP v2 feature source; OI accumulation track |

Symbol note: TON → GRAM rebrand on Binance USDT-M (TONUSDT is
SETTLING, GRAMUSDT is a new contract from 2026-07-02).  The TON-era
klines remain in `kl_TONUSDT_1h.parquet`; `load_binance` maps
TON-USDT → GRAMUSDT (`SYMBOL_ALIASES`) for all new collection.

Fetcher libs live in `engine/infra/marketdata/` (`okx_fetch`,
`binance_fetch`); dataset builders live in `engine/datasets/` (`okx`,
`mtf`, `stops`).
