# -*- coding: utf-8 -*-
"""Deribit public history API probe -- feasibility for the options
track (puts overlay / vol carry).  Read-only, no auth, no gates.

Measures: instrument volume by currency/year, trade availability on
OLD instruments, DVOL history depth, settlement history depth.
Writes nothing to data/ (probe only).
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as dt
import json
import time
import urllib.request

BASE = "https://history.deribit.com/api/v2/public"


def get(path: str, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{BASE}/{path}?{q}",
                                 headers={"User-Agent": "probe/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["result"]
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            raise RuntimeError(f"{path} -> {e.code}: {body}") from e
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def ts2d(ms: int) -> str:
    return dt.datetime.utcfromtimestamp(ms / 1000).date().isoformat()


def main() -> None:
    # 1. instrument universe (full pagination)
    for cur in ("BTC", "ETH"):
        names, keep_going, offset = [], True, 0
        while keep_going:
            r = get("public/get_instruments", currency=cur, kind="option",
                    expired="true", count=500, offset=offset)
            items = r if isinstance(r, list) else r.get("instruments", [])
            names += items
            keep_going = len(items) == 500
            offset += len(items)
            if offset > 300000:
                break
        exp = [i["expiration_timestamp"] for i in names]
        yrs: dict[int, int] = {}
        for e in exp:
            y = dt.datetime.utcfromtimestamp(e / 1000).year
            yrs[y] = yrs.get(y, 0) + 1
        print(f"{cur} expired options: {len(names)}; "
              f"first expiry {ts2d(min(exp))}, last {ts2d(max(exp))}")
        print("   by expiry year:", dict(sorted(yrs.items())))

        # 2. trades on the OLDEST instrument
        old = min(names, key=lambda i: i["expiration_timestamp"])
        tr = get("public/get_last_trades_by_instrument",
                 instrument_name=old["instrument_name"], count=5)
        n = tr.get("total", 0)
        print(f"   oldest {old['instrument_name']}: {n} trades stored")

        # 3. a mid-era instrument (first 2020 expiry)
        mid = [i for i in names
               if dt.datetime.utcfromtimestamp(
                   i["expiration_timestamp"] / 1000).year == 2020]
        if mid:
            m = mid[0]
            tr = get("public/get_last_trades_by_instrument",
                     instrument_name=m["instrument_name"], count=1)
            print(f"   2020-era {m['instrument_name']}: "
                  f"{tr.get('total', 0)} trades stored")

    # 4. DVOL depth
    r = get("public/get_volatility_index_data", currency="BTC",
            start_timestamp=0,
            end_timestamp=int(time.time() * 1000), resolution="1D")
    data = r.get("data", [])
    if data:
        t0 = data[0][0] / 1000 if data[0][0] > 1e11 else data[0][0]
        print(f"BTC DVOL daily: {len(data)} points from "
              f"{dt.datetime.utcfromtimestamp(t0).date()}")

    # 5. settlement history (options, old)
    r = get("public/get_settlement_history_by_currency", currency="BTC",
            type_="option", count=5)
    items = r.get("settlements", [])
    if items:
        print(f"BTC option settlements available; sample expiry "
              f"{ts2d(items[0]['expiry_timestamp'])} "
              f"mark={items[0].get('mark_price')}")

    print("probe done")


if __name__ == "__main__":
    main()
