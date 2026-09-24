# -*- coding: utf-8 -*-
"""Deribit public history fetcher -- step 1 of the options track.

Read-only, no auth.  Checkpointed: each stage skips work already on
disk, so the script is resumable.  Data cached under data/deribit/.

Stages:
  instruments : full expired-option instrument lists (BTC, ETH)
  dvol        : daily DVOL index (BTC, ETH)
  trades      : per-instrument trade dumps (subset only, given by
                --instruments-file with one instrument name per line)

Usage:
  python -m experiments.options.deribit_fetch instruments
  python -m experiments.options.deribit_fetch dvol
  python -m experiments.options.deribit_fetch trades --file list.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/deribit"
BASE = "https://history.deribit.com/api/v2/public"
BASE_WWW = "https://www.deribit.com/api/v2/public"
PAUSE = 0.25          # conservative anon pacing (limit is per-IP)
RETRIES = 8
HDRS = {"User-Agent": "fetch/0.1",
        "Accept": "application/json",
        "Accept-Encoding": "identity"}


def get(base: str, path: str, **params):
    """GET via curl subprocess, default headers (urllib and custom
    Accept headers are both rejected at the edge)."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{base}/{path}?{q}"
    cmd = ["curl", "-s", "--max-time", "300", url]
    for attempt in range(RETRIES):
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=320)
        if p.returncode == 0 and p.stdout.strip():
            try:
                return json.loads(p.stdout)["result"]
            except (json.JSONDecodeError, KeyError):
                pass  # retry (missing 'result' = error response)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"curl failed rc={p.returncode}: "
                       f"{p.stderr[:200]} {p.stdout[:200]}")


def ts2d(ms: float) -> str:
    return dt.datetime.utcfromtimestamp(ms / 1000).date().isoformat()


def _curl_to_file(url: str, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    cmd = ["curl", "-s", "--max-time", "600", "-o", str(tmp), "-w",
           "%{http_code}", url]
    time.sleep(20)        # quiet period: heavy calls back-to-back
    for attempt in range(RETRIES):   # trigger server throttling
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=620)
        if p.returncode == 0 and p.stdout.strip() == "200":
            tmp.replace(path)
            return
        time.sleep(20 + 10 * attempt)
    raise RuntimeError(f"curl failed rc={p.returncode} "
                       f"http={p.stdout.strip()!r}")


def stage_instruments(currency: str | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for cur in ((currency,) if currency else ("BTC", "ETH")):
        raw = OUT / f"_inst_{cur}.json"
        p = OUT / f"instruments_{cur}.json"
        if p.exists():
            print(f"instruments {cur}: cached, "
                  f"{len(json.loads(p.read_text()))} instruments")
            continue
        if not raw.exists():
            print(f"fetching expired {cur} options (one big call) ...",
                  flush=True)
            t0 = time.time()
            _curl_to_file(f"{BASE}/public/get_instruments?currency={cur}"
                          f"&kind=option&expired=true", raw)
            print(f"  downloaded in {time.time() - t0:.0f}s", flush=True)
        r = json.loads(raw.read_text(encoding="utf-8"))
        if isinstance(r, list):
            items = r
        elif isinstance(r, dict):
            items = r.get("result") or r.get("instruments") or []
        else:
            items = []
        slim = [{k: i.get(k) for k in
                 ("instrument_name", "expiration_timestamp",
                  "strike", "option_type", "settlement_period",
                  "creation_timestamp")}
                for i in items]
        p.write_text(json.dumps(slim))
        exp = [i["expiration_timestamp"] for i in slim]
        yrs: dict[int, int] = {}
        for e in exp:
            y = dt.datetime.utcfromtimestamp(e / 1000).year
            yrs[y] = yrs.get(y, 0) + 1
        print(f"  {len(slim)} instruments; first expiry "
              f"{ts2d(min(exp))}; by year {dict(sorted(yrs.items()))}",
              flush=True)
        raw.unlink()          # 76MB of raw JSON: keep only the slim list


def stage_dvol(currency: str | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    for cur in ((currency,) if currency else ("BTC", "ETH")):
        p = OUT / f"dvol_{cur}_1D.json"
        if p.exists():
            print(f"dvol {cur}: cached, "
                  f"{len(json.loads(p.read_text()))} points")
            continue
        # www host only; chunk by calendar year; DVOL inception is
        # 2021-03, earlier windows return an error -> skipped
        data: list = []
        start_year = 2021
        for y in range(start_year, dt.datetime.utcnow().year + 1):
            t0 = int(dt.datetime(y, 1, 1).timestamp() * 1000)
            t1 = min(int(dt.datetime(y + 1, 1, 1).timestamp() * 1000),
                     now)
            try:
                r = get(BASE_WWW, "public/get_volatility_index_data",
                        currency=cur, start_timestamp=t0,
                        end_timestamp=t1, resolution="1D")
                data += r.get("data", []) if isinstance(r, dict) else []
            except RuntimeError as e:
                print(f"  dvol {cur} {y}: skipped ({e})", flush=True)
            time.sleep(PAUSE)
        # dedupe by ts, keep first
        seen, out = set(), []
        for row in data:
            if row[0] not in seen:
                seen.add(row[0])
                out.append(row)
        p.write_text(json.dumps(out))
        if out:
            t0 = out[0][0] / 1000
            print(f"dvol {cur}: {len(out)} daily points from "
                  f"{dt.datetime.utcfromtimestamp(t0).date()}", flush=True)


def stage_trades(list_file: Path) -> None:
    names = [ln.strip() for ln in list_file.read_text().splitlines()
             if ln.strip()]
    tdir = OUT / "trades"
    tdir.mkdir(parents=True, exist_ok=True)
    done = 0
    for i, name in enumerate(names):
        p = tdir / f"{name}.json"
        if p.exists():
            continue
        all_trades, keep_going, start = [], True, None
        while keep_going:
            kw = dict(instrument_name=name, count=1000,
                      include_old="true", sorting="asc")
            if start is not None:
                kw["start_seq"] = start
            r = get(BASE, "public/get_last_trades_by_instrument", **kw)
            trades = r.get("trades", [])
            all_trades += trades
            keep_going = len(trades) == 1000
            if trades:
                start = trades[-1]["trade_seq"] + 1
            time.sleep(PAUSE)
        p.write_text(json.dumps(all_trades))
        done += 1
        if done % 25 == 0 or i == len(names) - 1:
            print(f"[{i + 1}/{len(names)}] fetched, last {name} "
                  f"({len(all_trades)} trades)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage",
                    choices=["instruments", "dvol", "trades"])
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--currency", default=None,
                    help="restrict stage to one currency (BTC|ETH)")
    a = ap.parse_args()
    if a.stage == "instruments":
        stage_instruments(a.currency)
    elif a.stage == "dvol":
        stage_dvol(a.currency)
    else:
        if a.file is None:
            raise SystemExit("trades stage needs --file")
        stage_trades(a.file)


if __name__ == "__main__":
    main()
