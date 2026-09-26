"""P4-EX: execution model on the P4 panel (prereg 75ff2ee).

v3 accounting AS-IS (funding accrues per the frozen per_asset_stream
convention: entry day collects, exit day doesn't), plus the frozen
execution layer: maker fill P=0.5 i.i.d. (seed=7), missed entry
retries next day (funding skipped), missed exit keeps the position
(funding accrues), any fill after >=1 miss pays TAKER_EXTRA=20bp
(both legs fallback), BASIS_RT=0.50% charged at each completed
round trip.
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import datetime as _dt
import json

import numpy as np

from experiments import REPO
from experiments.carry.funding_carry_v3.carry_v3_ci import ann_ci
from experiments.carry.funding_carry_v2.funding_carry_v2 import DEAD_ZONE, MAKER_RT
from experiments.carry.funding_carry_v3.funding_carry_v3 import max_dd, sharpe_nw
from experiments.carry.p4.p4_carry import build_panel, trailing_signal


P_FILL = 0.5
TAKER_EXTRA = 0.002
BASIS_RT = 0.005
SEED = 7
CONF_DAYS = 365
BLOCK = 30
B = 10_000


def exec_stream(f_col: np.ndarray, s_col: np.ndarray,
                rng: np.random.Generator) -> np.ndarray:
    n = len(f_col)
    stream = np.zeros(n)
    pos = 0.0
    missed = False
    for i in range(n):
        if not np.isfinite(f_col[i]):
            continue
        cost = 0.0
        if pos == 0.0:
            if (np.isfinite(s_col[i]) and abs(s_col[i]) >= DEAD_ZONE
                    and rng.random() < P_FILL):
                pos = -1.0 if s_col[i] > 0 else 1.0
                cost = MAKER_RT / 2 + (TAKER_EXTRA if missed else 0.0)
                missed = False
            elif np.isfinite(s_col[i]) and abs(s_col[i]) >= DEAD_ZONE:
                missed = True  # stay flat, retry next day
        else:
            flip = ((pos < 0 and s_col[i] <= 0)
                    or (pos > 0 and s_col[i] >= 0))
            if flip and np.isfinite(s_col[i]):
                if rng.random() < P_FILL:
                    cost = (MAKER_RT / 2 + BASIS_RT
                            + (TAKER_EXTRA if missed else 0.0))
                    pos = 0.0
                    missed = False
                else:
                    missed = True  # keep position, funding accrues
        stream[i] = -pos * f_col[i] - cost
    return stream


def main() -> None:
    snap = sorted((REPO / "data").glob("p4_universe_*.json"))[-1]
    syms = [u["symbol"] for u in json.loads(snap.read_text())["universe"]]
    mat, dates, _keep = build_panel(syms)
    sig = trailing_signal(mat)
    rng = np.random.default_rng(SEED)
    streams = np.zeros_like(mat)
    for j in range(mat.shape[1]):
        streams[:, j] = exec_stream(mat[:, j], sig[:, j], rng)
    n = mat.shape[0]
    a_conf = next((i for i, d in enumerate(dates)
                   if d >= dates[-1] - _dt.timedelta(days=CONF_DAYS)), 0)
    port = streams.mean(axis=1)
    segs = {"PRIMARY": (0, n), "CONF-12m": (a_conf, n)}
    res = {}
    for name, (a, b) in segs.items():
        _sh, shnw, fac = sharpe_nw(port[a:b])
        res[name] = {"ann_pct": round(float(port[a:b].mean() * 365) * 100, 2),
                     "ann_capital_adj": round(float(port[a:b].mean() * 365)
                                              * 50, 2),
                     "sharpe_nw": round(shnw, 2), "nw_factor": round(fac, 2),
                     "max_dd_pct": round(max_dd(port[a:b]) * 100, 2)}
        print(f"{name}: ann={res[name]['ann_pct']:+.2f}%  "
              f"(capital-adj {res[name]['ann_capital_adj']:+.2f}%)  "
              f"sharpe_nw={shnw:+.2f}  maxDD={res[name]['max_dd_pct']:.2f}%",
              flush=True)
    rng_ci = np.random.default_rng(SEED)
    for name, (a, b) in segs.items():
        _p, lo, hi = ann_ci(port[a:b], rng_ci)
        res[name]["ci95"] = [round(lo, 2), round(hi, 2)]
        print(f"{name}: CI95=[{lo:+.2f}, {hi:+.2f}]", flush=True)

    # stability read-out: rolling 6m ann windows
    w = 182
    wins = [port[i:i + w].mean() * 365 * 100 for i in range(n - w)]
    wins = np.array(wins)
    print(f"rolling 6m ann: positive {int((wins > 0).sum())}/{len(wins)} "
          f"windows, worst {wins.min():+.2f}%, best {wins.max():+.2f}%",
          flush=True)

    g1 = res["PRIMARY"]["sharpe_nw"] >= 1.0
    g2 = res["CONF-12m"]["sharpe_nw"] >= 0.7
    g3 = res["PRIMARY"]["max_dd_pct"] <= 15.0
    g4 = res["PRIMARY"]["ci95"][0] > 0.0
    for name, ok in (("EX-G1", g1), ("EX-G2", g2), ("EX-G3", g3),
                     ("EX-G4", g4)):
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    verdict = ("PASS -> deployable-subject-to-paper-trading"
               if (g1 and g2 and g3 and g4) else
               "CLOSED as execution-blocked (funding-stream PASS = upper "
               "bound; no re-run)")
    print(f"P4-EX: {verdict}", flush=True)
    out = {"results": res, "rolling6m": {"pos": int((wins > 0).sum()),
                                         "n": len(wins),
                                         "worst": round(float(wins.min()), 2)},
           "gates": {"EX-G1": g1, "EX-G2": g2, "EX-G3": g3, "EX-G4": g4},
           "verdict": verdict}
    (REPO / "runs" / "p4_exec.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
