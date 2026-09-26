# -*- coding: utf-8 -*-
"""E3: event calendar builder (infra for Wave 5).

Sources: hard-coded public dates (halvings, ETH upgrades, FOMC
scheduled meetings 2021-2025) + computed Deribit monthly expiries
(last Friday of month).  Output:
data/events/event_calendar_2021_2026.json

NOTE: FOMC dates are the public scheduled meetings; re-verify
against federalreserve.gov before any live use.
"""

from __future__ import annotations

__version__ = "1.0.0"

import datetime as dt
import json

from engine.passed.avsl_cross_s1 import repo_root


def last_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 1)
    nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def main() -> None:
    ev: list[dict] = []

    def add(name: str, otype: str, d: dt.date) -> None:
        ev.append(dict(name=name, type=otype,
                       ts=int(dt.datetime(d.year, d.month, d.day,
                                          12, 0,
                                          tzinfo=dt.timezone.utc)
                              .timestamp() * 1000)))

    # crypto-native
    add("BTC halving", "halving", dt.date(2024, 4, 20))
    add("BTC halving", "halving", dt.date(2020, 5, 11))
    add("ETH Merge", "upgrade", dt.date(2022, 9, 15))
    add("ETH Shanghai", "upgrade", dt.date(2023, 4, 12))
    add("ETH Dencun", "upgrade", dt.date(2024, 3, 13))

    # FOMC scheduled decisions (public schedule)
    fomc = {
        2021: ["01-27", "03-17", "04-28", "06-16", "07-28",
               "09-22", "11-03", "12-15"],
        2022: ["01-26", "03-16", "05-04", "06-15", "07-27",
               "09-21", "11-02", "12-14"],
        2023: ["02-01", "03-22", "05-03", "06-14", "07-26",
               "09-20", "11-01", "12-13"],
        2024: ["01-31", "03-20", "05-01", "06-12", "07-31",
               "09-18", "11-07", "12-18"],
        2025: ["01-29", "03-19", "05-07", "06-18", "07-30",
               "09-17", "10-29", "12-10"],
    }
    for y, mds in fomc.items():
        for md in mds:
            m, d = md.split("-")
            add("FOMC", "fomc", dt.date(y, int(m), int(d)))

    # Deribit monthly expiries (last Friday), 2021-04..2026-09
    for (y, m) in [(2021, m) for m in range(4, 13)] + \
                  [(y, m) for y in range(2022, 2026)
                   for m in range(1, 13)] + \
                  [(2026, m) for m in range(1, 10)]:
        add("Deribit monthly expiry", "expiry", last_friday(y, m))

    ev.sort(key=lambda e: e["ts"])
    out = repo_root() / "data/events/event_calendar_2021_2026.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        dict(version=__version__, n=len(ev), events=ev), indent=1),
        encoding="utf-8")
    by_type: dict[str, int] = {}
    for e in ev:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print(f"written {out}: {len(ev)} events {by_type}")


if __name__ == "__main__":
    main()
