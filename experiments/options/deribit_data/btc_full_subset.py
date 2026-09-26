# -*- coding: utf-8 -*-
"""B1 precondition PASSED -> full BTC monthly chain subset.
Frozen rule: settlement_period=month, all strikes with
strike/spot(T-30d) in [0.6, 1.4], puts+calls.
Output: data/deribit/btc_full_subset.json + btc_full_names.txt
"""
from __future__ import annotations


__version__ = "1.0.0"
import json
import urllib.request

import numpy as np

from engine.passed.avsl_cross_s1 import repo_root


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tinv"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    ctx_spot = None
    from experiments.options._runner import load_ctx
    ctx = load_ctx()
    ts1, cp1 = ctx["ts1"], ctx["cp1"]

    def spot(ts):
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    instruments = json.loads(
        (repo_root() / "data/deribit/instruments_BTC.json").read_text())
    monthly = [m for m in instruments
               if m.get("settlement_period") == "month"]
    subset = {}
    for m in monthly:
        exp = m["expiration_timestamp"]
        ref = spot(exp - 30 * 86_400_000)
        mm = m["strike"] / ref
        if not (0.6 <= mm <= 1.4):
            continue
        subset[m["instrument_name"]] = dict(
            strike=m["strike"], expiration_timestamp=exp,
            option_type=m["option_type"])
    names = sorted(subset)
    out = repo_root() / "data/deribit"
    (out / "btc_full_subset.json").write_text(
        json.dumps(subset), encoding="utf-8")
    (out / "btc_full_names.txt").write_text(
        chr(10).join(names) + chr(10), encoding="utf-8")
    print(f"written {len(names)} instruments of {len(instruments)} "
          f"({len(monthly)} monthly)")


if __name__ == "__main__":
    main()
