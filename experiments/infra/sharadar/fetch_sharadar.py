# -*- coding: utf-8 -*-
"""Sharadar fetcher + PIT-universe builder (READY, blocked on API key).

Requires SHARADAR_API_KEY env var (Prices Full History plan minimum).
Direct API (api.sharadar.com/v1.0) -- nasdaqdatalink/quandl libs do
NOT work with new keys.  Bulk downloads use the documented 302-zip
pattern; slice queries use ticker/from/to (no pagination).

Outputs:
  data/sharadar/tickers.parquet   -- ticker master (firstpricedate,
                                     lastpricedate, ...)
  data/sharadar/stocks_full.csv   -- full-history EOD (bulk zip)

PIT rule (for prereg, frozen there): a ticker is tradable on date d
iff firstpricedate <= d <= lastpricedate (delisted names keep their
history -> survivorship-free).  Liquidity ranking, if used, must be
trailing-only (252d median dollar volume at d).
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import polars as pl
import requests

BASE = "https://api.sharadar.com/v1.0"


def _key() -> str:
    k = os.environ.get("SHARADAR_API_KEY")
    if not k:
        raise SystemExit("set SHARADAR_API_KEY first")
    return k


def _out(repo: Path) -> Path:
    out = repo / "data" / "sharadar"
    out.mkdir(parents=True, exist_ok=True)
    return out


def fetch_tickers(repo: Path) -> pl.DataFrame:
    """Ticker master: firstpricedate/lastpricedate drive the PIT filter."""
    fp = _out(repo) / "tickers.parquet"
    if fp.exists():
        return pl.read_parquet(fp)
    r = requests.get(f"{BASE}/data/tickers/",
                     params={"api_key": _key(), "table": "tickers"},
                     timeout=120)
    r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content), infer_schema_length=10000)
    df.write_parquet(fp)
    print(f"tickers: {df.height} rows")
    return df


def fetch_stocks_bulk(repo: Path) -> Path:
    """Full-history EOD table via bulk 302-zip (documented pattern)."""
    fp = _out(repo) / "stocks_full.csv"
    if fp.exists():
        return fp
    r = requests.get(f"{BASE}/data/stocks/",
                     params={"api_key": _key(), "years": "full"},
                     timeout=1800, allow_redirects=True)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = z.namelist()[0]
    fp.write_bytes(z.read(name))
    print(f"stocks_full.csv: {fp.stat().st_size / 1e6:.0f} MB")
    return fp


def load_prices(repo: Path) -> pl.DataFrame:
    """Normalized EOD: adjusted OHLC (H/L scaled by closeadj/closeunadj)."""
    fp = _out(repo) / "stocks_adj.parquet"
    if fp.exists():
        return pl.read_parquet(fp)
    raw = pl.read_csv(fetch_stocks_bulk(repo), infer_schema_length=10000)
    ratio = pl.when(pl.col("closeunadj") > 0).then(
        pl.col("closeadj") / pl.col("closeunadj")).otherwise(1.0)
    df = raw.with_columns(
        (pl.col("open") * ratio).alias("open"),
        (pl.col("high") * ratio).alias("high"),
        (pl.col("low") * ratio).alias("low"),
        pl.col("closeadj").alias("close"),
    ).select("ticker", "date", "open", "high", "low", "close", "volume")
    df.write_parquet(fp)
    print(f"stocks_adj: {df.height} rows, "
          f"{df['ticker'].n_unique()} tickers")
    return df


def pit_universe(prices: pl.DataFrame, tickers: pl.DataFrame,
                 d) -> set[str]:
    """Tickers alive on date d (PIT, survivorship-free)."""
    alive = tickers.filter(
        (pl.col("firstpricedate") <= d)
        & ((pl.col("lastpricedate") >= d)
           | pl.col("lastpricedate").is_null()))
    return set(alive["ticker"].to_list())
