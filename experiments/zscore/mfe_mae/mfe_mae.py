"""MFE/MAE post-mortem on the taken z-score event trades.

Diagnostic, not a strategy run: replays the exact frozen event path
(same cursor, same next-bar-open fills, same risk unit k_sl*atr at
the signal bar) and, for every taken trade, measures the maximal
favorable / adverse excursion in risk units R.

Two windows per trade:
- "life"  : entry bar .. actual exit bar (as traded);
- "h120"  : entry bar .. entry+120 bars (fixed horizon, censored at
  end of data).

Known censoring: within "life" MAE is capped at ~1R for losers by
the SL construction; MFE is the informative quantity ("was there
movement to capture with a different exit?").  XSEC-1 has no event
trades and is excluded.  Gross of all costs by definition.

Run:  python -m experiments.zscore.mfe_mae.mfe_mae   ->  runs/zscore_mfe.json
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import json
import time

import numpy as np

from engine.sim.engine import sim
from experiments._repo import REPO
from experiments.zscore.entry.runner import (
    MAJORS,
    STRATEGIES,
    load_asset,
    positions,
)


OUT = REPO / "runs" / "zscore_mfe.json"
SPLIT_TS = 1_716_811_200_000     # PRIMARY | F3 (same grid as the run)
HORIZON = 120
QUANTILES = (0.50, 0.75, 0.90, 0.95)


def event_trades_with_windows(
    asset: dict[str, np.ndarray], st: object
) -> list[dict]:
    """Same entry/cursor logic as runner.run_event_asset, but keeps
    entry/exit indices, side and the risk unit."""
    pos = positions(asset, st)
    o, h, lo, c = (asset["open"], asset["high"], asset["low"],
                   asset["close"])
    atr, ts = asset["atr24"], asset["ts"]
    n = len(pos)
    trades: list[dict] = []
    cursor = 0
    for i in range(1, n):
        if pos[i] == pos[i - 1] or pos[i] == 0 or i < cursor:
            continue
        i0 = i + 1
        if i0 >= n or not np.isfinite(atr[i]):
            continue
        side = "long" if pos[i] == 1 else "short"
        fill = o[i0]
        sl = fill - st.k_sl * atr[i] if side == "long" \
            else fill + st.k_sl * atr[i]
        tp = fill + st.k_tp * atr[i] if side == "long" \
            else fill - st.k_tp * atr[i]
        r_opt, r_pess, exit_idx = sim(
            o, h, lo, c, i0, side, sl, tp, 48, atr[i]
        )
        if exit_idx < 0:
            break
        cursor = exit_idx + 1
        trades.append({
            "ts": int(ts[i0]),
            "side": side,
            "fill": float(fill),
            "unit": float(st.k_sl * atr[i]),
            "i0": i0,
            "exit": int(exit_idx),
            "r_opt": float(r_opt),
            "r_pess": float(r_pess),
        })
    return trades


def excursions(
    asset: dict[str, np.ndarray], tr: dict, horizon: int | None
) -> tuple[float, float]:
    """MFE, MAE in R for one trade over the given window."""
    h, lo = asset["high"], asset["low"]
    i0 = tr["i0"]
    end = tr["exit"] if horizon is None else min(i0 + horizon, len(h) - 1)
    sign = 1.0 if tr["side"] == "long" else -1.0
    mfe = float(np.max(sign * (h[i0:end + 1] - tr["fill"]))) / tr["unit"]
    mae = float(np.max(sign * (tr["fill"] - lo[i0:end + 1]))) / tr["unit"]
    return mfe, mae


def main() -> None:
    t0 = time.time()
    assets = {}
    for m in MAJORS:
        a = load_asset(m)
        if a is not None:
            assets[m] = a
    print(f"loaded {len(assets)}/{len(MAJORS)} assets")

    report: dict = {"horizon": HORIZON, "split_ts": SPLIT_TS,
                    "strategies": {}}
    for st in STRATEGIES:
        if st.kind != "event":
            continue
        rows = []
        for name, a in assets.items():
            for tr in event_trades_with_windows(a, st):
                mfe_life, mae_life = excursions(a, tr, None)
                mfe_h, mae_h = excursions(a, tr, HORIZON)
                rows.append({
                    "primary": tr["ts"] < SPLIT_TS,
                    "r_opt": tr["r_opt"], "r_pess": tr["r_pess"],
                    "mfe_life": mfe_life, "mae_life": mae_life,
                    "mfe_h": mfe_h, "mae_h": mae_h,
                })
        cols = ("r_opt", "r_pess",
                "mfe_life", "mae_life", "mfe_h", "mae_h")
        out: dict = {}
        for fold, key in (("PRIMARY", True), ("F3", False),
                          ("ALL", None)):
            sub = [r for r in rows
                   if key is None or r["primary"] == key]
            out[fold] = {
                "n": len(sub),
                "wr_pess": float(np.mean(
                    [r["r_pess"] > 0 for r in sub])) if sub else None,
                **{c: {f"p{int(q * 100)}": float(np.quantile(
                        [r[c] for r in sub], q)) for q in QUANTILES}
                   for c in cols if sub},
            }
        report["strategies"][st.name] = out
        p = out["PRIMARY"]
        print(f"\n{st.name}  (PRIMARY n={p['n']}, F3 n={out['F3']['n']}, "
              f"WR_pess(P)={p['wr_pess']:.3f})")
        # quantile table per the post-mortem template
        for fold in ("PRIMARY", "F3"):
            print(f"  {fold}:")
            for c in ("mfe_life", "mae_life", "mfe_h", "mae_h"):
                q = out[fold][c]
                print("    {:>8s}  p50 {:5.2f}  p75 {:5.2f}  "
                      "p90 {:5.2f}  p95 {:5.2f}".format(
                          c, q["p50"], q["p75"], q["p90"], q["p95"]))

    OUT.write_text(json.dumps(report, indent=1))
    print(f"\ndone in {time.time() - t0:.1f}s -> {OUT}")


if __name__ == "__main__":
    main()
