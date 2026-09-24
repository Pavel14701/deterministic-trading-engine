# -*- coding: utf-8 -*-
"""Assemble DVOL daily files from per-year raw JSON chunks."""
import datetime as dt
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/deribit"
TMP = Path(os.environ.get("TEMP", r"C:\Users\Pashtet\AppData\Local\Temp"))


def merge(cur: str) -> None:
    rows = []
    for p in sorted(TMP.glob(f"dvol_{cur.lower()}_2*.json")):
        r = json.loads(p.read_text())
        rows += r.get("result", {}).get("data", [])
    seen: set = set()
    out = [x for x in rows if not (x[0] in seen or seen.add(x[0]))]
    out.sort(key=lambda x: x[0])
    (OUT / f"dvol_{cur}_1D.json").write_text(json.dumps(out))
    print(cur, len(out), "pts",
          dt.datetime.utcfromtimestamp(out[0][0] / 1000).date(), "..",
          dt.datetime.utcfromtimestamp(out[-1][0] / 1000).date(),
          "| last close", out[-1][4])


merge("BTC")
merge("ETH")
