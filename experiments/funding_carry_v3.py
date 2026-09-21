"""Per-asset slow carry v3 -- pre-registered (STATUS.md, efcb6d5).

Per-asset hold-until-sign-flip carry on 3y of Binance funding
(the only multi-year source; OKX tradability to be re-validated
separately on the OKX 96d panel).  Params frozen from v2: trailing
3d mean daily funding, entry |sig| >= 2bp/day, exit on sign flip,
maker half round-trip (0.10%) at entry and exit.

PRIMARY eval = F1+F2 pooled (2023-09..2025-08), F3 = confirmation.
Gates: C-G1 Sharpe_NW >= 1 on >= 10/29 active assets; C-G2
portfolio Sharpe_NW >= 1; C-G3 portfolio maxDD <= 20%.
"""
from __future__ import annotations

import datetime as _dt
import json

from pathlib import Path

import numpy as np

from experiments.funding_carry import UNIVERSE
from experiments.funding_carry_v2 import (
    DEAD_ZONE,
    MAKER_RT,
    binance_daily_funding,
    build_panel,
    trailing_signal,
)


NW_LAGS = 5
ACTIVITY_FLOOR_DAYS = 60


def per_asset_stream(f_col: np.ndarray, s_col: np.ndarray) -> np.ndarray:
    """Daily net stream for one asset; v2 rules, frozen."""
    n = len(f_col)
    stream = np.zeros(n)
    pos = 0.0
    for i in range(n):
        if not np.isfinite(f_col[i]):
            continue
        cost_i = 0.0
        if pos == 0.0:
            if np.isfinite(s_col[i]) and s_col[i] >= DEAD_ZONE:
                pos = -1.0  # positive funding -> short perp (+ long spot)
                cost_i = MAKER_RT / 2
            elif np.isfinite(s_col[i]) and s_col[i] <= -DEAD_ZONE:
                pos = 1.0   # negative funding -> long perp (+ short spot)
                cost_i = MAKER_RT / 2
        elif pos < 0 and s_col[i] <= 0.0:
            pos = 0.0
            cost_i = MAKER_RT / 2
        elif pos > 0 and s_col[i] >= 0.0:
            pos = 0.0
            cost_i = MAKER_RT / 2
        stream[i] = -pos * f_col[i] - cost_i
    return stream


def sharpe_nw(v: np.ndarray) -> tuple[float, float, float]:
    """Annualized Sharpe and Newey-West-corrected Sharpe (lags 1..5)."""
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan"), float("nan"), 1.0
    base = float(v.mean() / v.std() * np.sqrt(365))
    rho = [float(np.corrcoef(v[:-k], v[k:])[0, 1])
           for k in range(1, NW_LAGS + 1) if v.size > k + 10]
    factor = float(np.sqrt(max(1.0, min(5.0,
                                        1.0 + 2.0 * float(np.sum(rho))))))
    return base, base / factor, factor


def max_dd(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    eq = np.cumprod(1.0 + v)
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def eval_window(streams: np.ndarray, mat: np.ndarray,
                a: int, b: int) -> dict:
    sw = streams[a:b]
    fw = mat[a:b]
    out: dict = {"assets": {}, "portfolio": {}}
    count = 0
    for j in range(mat.shape[1]):
        mask = np.isfinite(fw[:, j])
        active = int(np.sum(mask & (sw[:, j] != 0.0)))
        sh, shnw, fac = sharpe_nw(sw[mask, j])
        out["assets"][UNIVERSE[j]] = {
            "sharpe": round(sh, 2), "sharpe_nw": round(shnw, 2),
            "nw_factor": round(fac, 2), "active_days": active,
        }
        if active >= ACTIVITY_FLOOR_DAYS and shnw >= 1.0:
            count += 1
    port = sw.mean(axis=1)
    psh, pshnw, _ = sharpe_nw(port)
    out["portfolio"] = {
        "ann_pct": round(float(port.mean() * 365) * 100, 2),
        "sharpe": round(psh, 2), "sharpe_nw": round(pshnw, 2),
        "max_dd_pct": round(max_dd(port) * 100, 2),
    }
    out["n_sharpe_nw_ge1"] = count
    return out


def main() -> None:
    print("=== per-asset slow carry v3 (pre-registered efcb6d5) ===",
          flush=True)
    mat, dates = build_panel(binance_daily_funding)
    sig = trailing_signal(mat)
    n = mat.shape[0]
    marks = [_dt.date(2023, 9, 1), _dt.date(2024, 9, 1),
             _dt.date(2025, 9, 1), _dt.date(2026, 9, 30)]
    idx = [0] + [next((i for i, d in enumerate(dates) if d >= m), n)
                 for m in marks[1:]]
    folds = [(idx[0], idx[1], "F1"), (idx[1], idx[2], "F2"),
             (idx[2], min(idx[3], n), "F3")]

    streams = np.zeros_like(mat)
    for j in range(mat.shape[1]):
        streams[:, j] = per_asset_stream(mat[:, j], sig[:, j])

    a0, b0 = folds[0][0], folds[1][1]
    prim = eval_window(streams, mat, a0, b0)
    print(f"\n-- PRIMARY: F1+F2 pooled ({dates[a0]} .. {dates[b0 - 1]})",
          flush=True)
    for name, st in sorted(prim["assets"].items(),
                           key=lambda kv: -kv[1]["sharpe_nw"])[:12]:
        print(f"  {name:11s} sharpe={st['sharpe']:7.2f}  "
              f"sharpe_nw={st['sharpe_nw']:7.2f}  "
              f"(nw x{st['nw_factor']:.2f}, active {st['active_days']}d)")
    print(f"  assets Sharpe_NW>=1 (active>={ACTIVITY_FLOOR_DAYS}d): "
          f"{prim['n_sharpe_nw_ge1']}/29")
    print(f"  portfolio: ann={prim['portfolio']['ann_pct']:+.2f}%  "
          f"sharpe={prim['portfolio']['sharpe']:.2f}  "
          f"sharpe_nw={prim['portfolio']['sharpe_nw']:.2f}  "
          f"maxDD={prim['portfolio']['max_dd_pct']:.2f}%")

    for a, b, name in folds:
        r = eval_window(streams, mat, a, b)
        print(f"\n-- {name} ({dates[a]} .. {dates[min(b, n) - 1]}): "
              f"assets>=1: {r['n_sharpe_nw_ge1']}/29  "
              f"ann={r['portfolio']['ann_pct']:+.2f}%  "
              f"sharpe_nw={r['portfolio']['sharpe_nw']:.2f}  "
              f"maxDD={r['portfolio']['max_dd_pct']:.2f}%")

    g1 = prim["n_sharpe_nw_ge1"] >= 10
    g2 = prim["portfolio"]["sharpe_nw"] >= 1.0
    g3 = prim["portfolio"]["max_dd_pct"] <= 20.0
    verdict = "PASS" if (g1 and g2 and g3) else "FAIL"
    print("\n=== gates (PRIMARY F1+F2) ===")
    print(f"  C-G1 Sharpe_NW>=1 on >=10/29: {prim['n_sharpe_nw_ge1']} "
          f"-> {'PASS' if g1 else 'FAIL'}")
    print(f"  C-G2 portfolio Sharpe_NW>=1: "
          f"{prim['portfolio']['sharpe_nw']:.2f} "
          f"-> {'PASS' if g2 else 'FAIL'}")
    print(f"  C-G3 maxDD<=20%: {prim['portfolio']['max_dd_pct']:.2f}% "
          f"-> {'PASS' if g3 else 'FAIL'}")
    print(f"OVERALL: {verdict}")

    out = {"primary": prim, "gates": {"C-G1": g1, "C-G2": g2,
                                      "C-G3": g3},
           "verdict": verdict}
    Path("runs/funding_carry_v3.json").write_text(json.dumps(out, indent=1))
    print("saved runs/funding_carry_v3.json", flush=True)


if __name__ == "__main__":
    main()

