# -*- coding: utf-8 -*-
"""Fetch FX 4H OHLCV(tick-volume) from Dukascopy, 2003-2026.

One file per pair: data/duka/{PAIR}_4H.parquet (polars, UTC ts).
Volume = TICK count (Dukascopy has no traded volume for OTC FX) --
documented in PREREG_FX_AVSL_4H.md.
"""
from __future__ import annotations

from datetime import datetime

import polars as pl

import dukascopy_python
from dukascopy_python.instruments import (
    INSTRUMENT_FX_CROSSES_EUR_GBP,
    INSTRUMENT_FX_CROSSES_EUR_JPY,
    INSTRUMENT_FX_CROSSES_GBP_JPY,
    INSTRUMENT_FX_MAJORS_AUD_USD,
    INSTRUMENT_FX_MAJORS_EUR_USD,
    INSTRUMENT_FX_MAJORS_GBP_USD,
    INSTRUMENT_FX_MAJORS_NZD_USD,
    INSTRUMENT_FX_MAJORS_USD_CAD,
    INSTRUMENT_FX_MAJORS_USD_CHF,
    INSTRUMENT_FX_MAJORS_USD_JPY,
)

PAIRS = {
    "EURUSD": INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDUSD": INSTRUMENT_FX_MAJORS_AUD_USD,
    "USDCAD": INSTRUMENT_FX_MAJORS_USD_CAD,
    "USDCHF": INSTRUMENT_FX_MAJORS_USD_CHF,
    "NZDUSD": INSTRUMENT_FX_MAJORS_NZD_USD,
    "EURJPY": INSTRUMENT_FX_CROSSES_EUR_JPY,
    "GBPJPY": INSTRUMENT_FX_CROSSES_GBP_JPY,
    "EURGBP": INSTRUMENT_FX_CROSSES_EUR_GBP,
}


def fetch_pair(name: str, instr, out, start_year: int = 2003) -> None:
    fp = out / f"{name}_4H.parquet"
    if fp.exists():
        print(f"{name}: cached", flush=True)
        return
    parts = []
    year = start_year
    while year <= 2026:
        try:
            df = dukascopy_python.fetch(
                instr,
                dukascopy_python.INTERVAL_HOUR_4,
                dukascopy_python.OFFER_SIDE_BID,
                datetime(year, 1, 1),
                datetime(year + 1, 1, 1),
            )
            if len(df):
                idx = df.index
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_localize(None)
                parts.append({
                    "timestamp": idx.to_numpy(),
                    **{c: df[c].to_numpy(dtype="float64")
                       for c in ("open", "high", "low", "close",
                                 "volume")}})
            print(f"{name}: {year} rows {len(df)}", flush=True)
        except Exception as e:  # noqa: BLE001 -- log and continue
            print(f"{name}: {year} FAIL {type(e).__name__} {e}",
                  flush=True)
        year += 1
    if not parts:
        print(f"{name}: EMPTY", flush=True)
        return
    full = pl.concat([pl.DataFrame(d) for d in parts])
    ts = full["timestamp"]
    full = (full.with_columns(pl.col("timestamp")
                              .dt.replace_time_zone(None))
            .unique(subset="timestamp").sort("timestamp"))
    full.write_parquet(fp)
    print(f"{name}: SAVED {full.height} rows "
          f"{ts[0]} -> {ts[-1]}", flush=True)


def main() -> None:
    from pathlib import Path
    out = Path("data/duka")
    out.mkdir(parents=True, exist_ok=True)
    for name, instr in PAIRS.items():
        fetch_pair(name, instr, out)


if __name__ == "__main__":
    main()
