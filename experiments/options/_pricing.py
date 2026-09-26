# -*- coding: utf-8 -*-
"""Shared options pricing helpers (Black-76 world, r=0). 

vol_pct convention matches strangle_carry/puts_overlay: IV in vol
points (e.g. 55.81), T in years, prices in underlying units.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs(S: float, K: float, T: float, vol_pct: float,
       is_call: bool) -> float:
    """Black-76-style spot price (r=0), vol_pct in points."""
    if T <= 0:
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    sig = max(vol_pct, 1e-9) / 100.0
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / sq
    d2 = d1 - sq
    if is_call:
        return float(S * _cdf(d1) - K * _cdf(d2))
    return float(K * _cdf(-d2) - S * _cdf(-d1))


def bs_greeks(S: float, K: float, T: float, vol_pct: float,
              is_call: bool) -> dict[str, float]:
    """Black-Scholes greeks (r=0, q=0).

    Returns delta, gamma, vega (per 1 vol POINT), theta (per DAY),
    and the auxiliary d1.  Put theta includes the r=0 simplification
    (no carry terms).
    """
    if T <= 0:
        return {"delta": (1.0 if S > K else 0.0) if is_call
                else (-1.0 if S < K else 0.0),
                "gamma": 0.0, "vega": 0.0, "theta": 0.0, "d1": float("nan")}
    sig = max(vol_pct, 1e-9) / 100.0
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / sq
    d2 = d1 - sq
    nd1 = _pdf(d1)
    delta = _cdf(d1) if is_call else _cdf(d1) - 1.0
    gamma = nd1 / (S * sq)
    vega = S * nd1 * math.sqrt(T) / 100.0          # per 1 vol point
    theta = -(S * nd1 * sig) / (2.0 * math.sqrt(T)) / 365.0  # per day
    return {"delta": float(delta), "gamma": float(gamma),
            "vega": float(vega), "theta": float(theta),
            "d1": float(d1)}


def load_prints(folder: Path) -> tuple[list[dict], int, int]:
    """All trades from a deribit prints folder.

    Returns (trades, n_files_ok, n_files_corrupt).  A trade dict is
    augmented with instrument_name / timestamp / iv passthrough;
    entries without a usable iv are dropped (counted separately is
    the caller's job via 'iv' key presence).
    """
    trades: list[dict] = []
    ok = bad = 0
    for f in sorted(Path(folder).glob("*.json")):
        try:
            d = json.loads(f.read_text())["result"]["trades"]
        except Exception:
            bad += 1
            continue
        ok += 1
        trades.extend(d)
    trades.sort(key=lambda x: x["timestamp"])
    return trades, ok, bad
