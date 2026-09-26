"""P4 universe snapshot (prereg STATUS 2026-09-21, frozen rule):
Binance USDT-M perps NOT in the current 30-name carry UNIVERSE,
listing age >= 180d at pull date, median daily quote volume over
the pull window >= $5M, top 30 by that volume.  No manual
adds/drops, ever.

Convention declared here (prereg says "the pull window"): the
pull window = trailing 30 days of daily klines ending at the
pull date.  The snapshot JSON is the frozen universe; the gate
runner consumes it verbatim.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as _dt
import json
import time

import niquests

from experiments import REPO
from experiments.carry.funding_carry_v1.funding_carry import UNIVERSE
from experiments.infra.loaders.load_binance import SYMBOL_ALIASES


BASE = "https://fapi.binance.com"
MIN_AGE_D = 180
MIN_MED_VOL = 5_000_000.0
TOP_N = 30
WINDOW_D = 30
OLD = {
    SYMBOL_ALIASES.get(u, u.replace("-", "")) for u in UNIVERSE
} | {"PEPEUSDT"}


def _get(url: str, params: dict) -> dict | list:
    for attempt in range(4):
        try:
            r = niquests.get(url, params=params, timeout=30.0)
            r.raise_for_status()
            return r.json()
        except niquests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed")


def main() -> None:
    pull = _dt.date.today()
    info = _get(f"{BASE}/fapi/v1/exchangeInfo", {})
    perps = [
        s for s in info["symbols"]
        if s["contractType"] == "PERPETUAL"
        and s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    ]
    cutoff = _dt.datetime.now(_dt.timezone.utc).timestamp() - MIN_AGE_D * 86400
    cand = [
        s["symbol"] for s in perps
        if s["symbol"] not in OLD
        and s["onboardDate"] / 1000 <= cutoff
    ]
    print(f"candidates (non-universe, age>={MIN_AGE_D}d): {len(cand)}",
          flush=True)
    scored = []
    for k, sym in enumerate(cand):
        kl = _get(f"{BASE}/fapi/v1/klines",
                  {"symbol": sym, "interval": "1d", "limit": WINDOW_D})
        vols = [float(row[7]) for row in kl]  # quote asset volume
        med = float(np_med(vols)) if len(vols) >= WINDOW_D // 2 else 0.0
        scored.append((sym, med))
        if k % 50 == 0:
            print(f"  {k}/{len(cand)}", flush=True)
        time.sleep(0.05)
    eligible = sorted(
        (x for x in scored if x[1] >= MIN_MED_VOL),
        key=lambda x: -x[1],
    )
    chosen = eligible[:TOP_N]
    snap = {
        "pull_date": pull.isoformat(),
        "rule": {"exclude": sorted(OLD), "min_age_d": MIN_AGE_D,
                 "window_d": WINDOW_D, "min_median_quote_vol": MIN_MED_VOL,
                 "top_n": TOP_N},
        "n_candidates": len(cand),
        "n_eligible": len(eligible),
        "universe": [
            {"symbol": s, "median_quote_vol_30d": round(v, 0)}
            for s, v in chosen
        ],
    }
    out = REPO / "data" / f"p4_universe_{pull.isoformat()}.json"
    out.write_text(json.dumps(snap, indent=1))
    print(f"universe frozen: {len(chosen)} symbols -> {out.name}")
    for s, v in chosen:
        print(f"  {s:16s} ${v / 1e6:8.1f}M/day")


def np_med(vols: list[float]) -> float:
    import numpy as np
    return float(np.median(vols))


if __name__ == "__main__":
    main()
