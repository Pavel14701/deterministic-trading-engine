# Данные

| Источник | Покрытие | Файлы | Фетчер |
|---|---|---|---|
| **Binance 1H klines** | 10 мейджоров + ~29 кэш-активов, полная история | `data/binance/kl_*_1h.parquet` | `experiments/loaders/load_binance.py` |
| **OKX 1H** | 34 актива (зеркала Binance-кэша) | `data/okx/` | `experiments/loaders/load_okx.py` |
| **Dukascopy FX 4H** | 10 пар, 2003–2026, ~39k баров/пара, tick-volume | `data/duka/` | `experiments/fx/duka_fetch.py` |
| **Deribit options** | BTC puts/calls prints + DVOL | `data/deribit/` | `experiments/options/deribit_fetch.py`, `fetch_puts_trades.sh` |
| **Yahoo Finance** | дневки stocks 12 мейджоров + SPY/DXY | `data/yf/` | `experiments/loaders/load_yf.py` |
| **Sharadar equities** | не скачано (ключ не куплен); контракт проверен | `data/sharadar/` | `experiments/sharadar/fetch_sharadar.py` |

## Квирки, которые нельзя забыть

- **yf hourly = 730 дней cap** → FX hourly через yf инфеибельно;
  поэтому Dukascopy (уроки TEST B).
- **Sharadar stocks**: CSV, `closeadj`/`closeunadj` — H/L скейлятся
  отношением; PIT через `firstpricedate`/`lastpricedate` (делистнутые
  сохраняют историю).
- **tick-volume vs vol=ones**: контроль на FX 4H показал одинаковый
  результат — объём-прокси не является объяснением провала transfer.
- **Binance → 4H**: детерминированный ресемпл (first/max/min/last/sum),
  `MSEC_4H = 14_400_000`; теплап WARMUP 400.
- **Кэши resumable** (page-cache); повторный запуск фетчера
  докачивает, а не перезакачивает.
