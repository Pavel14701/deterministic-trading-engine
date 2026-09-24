"""R-OH-1: beta-hedge overlay on the frozen E8b OB frame.

Prereg 45392a1: stream = S1-sized OB accrual + overlay
  hedge(t) = -alpha * E(t) * r_BTC(t),  E(t) = sum_open s1_i * sign_i.
Arms alpha in {0, 0.25, 0.5, 1.0} (exploratory axis by design).
Gate: exists alpha > 0 with maxDD <= 20% AND total >= 0.8 * total(alpha=0).
One-shot.
"""
from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ANN,  # noqa: F401
    ASSETS,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.ob.ob_risk_overlay import (
    _env,
    base_trades,
    decorate,
    sizing_aux,
)
from experiments.ob.rob1_long_only import gate_sharpe


ALPHAS = (0.0, 0.25, 0.5, 1.0)
DD_BAR = 0.20
EV_KEEP = 0.80


def _btc_simple_returns(repo, g0_min: int, n_g: int) -> np.ndarray:
    ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, "BTC"))
    b = np.asarray(ts, np.int64) // 14_400_000
    c = np.asarray(cp, float)
    r = c[1:] / c[:-1] - 1.0  # return realized at bucket-close b[i+1]
    out = np.zeros(n_g)
    idx = np.searchsorted(b, np.arange(g0_min, g0_min + n_g)) - 1
    m = (idx >= 0) & (idx < len(r))
    out[m] = r[idx[m]]
    return out


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0_min = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0_min
    aux = sizing_aux(repo)
    trades = base_trades(envs)  # ALL blocks, both sides (per prereg)
    decorate(trades, envs, aux, g0_min)
    print(f"[rhedge] entries={len(trades)} grid n={n_g}", flush=True)

    stream = np.zeros(n_g)
    expo = np.zeros(n_g)  # E(t), S1 units
    for t in trades:
        w = t["s1"] * t["net"]
        hold = max(t["e1"] - t["e0"], 1)
        sign = 1.0 if t["long"] else -1.0
        stream[t["e0"]:t["e1"] + 1] += w / (hold + 1)
        expo[t["e0"]:t["e1"] + 1] += sign * t["s1"]
    rbtc = _btc_simple_returns(repo, g0_min, n_g)

    def stats(a: float) -> tuple[float, float, float]:
        s = stream - a * expo * rbtc
        cum = np.cumsum(s)
        sh, _degen = gate_sharpe(s)
        return (float(cum[-1]), float(portfolio_dd(s)), float(sh))

    tot0, dd0, sh0 = stats(0.0)
    print(f"alpha=0   : total={tot0:+.2f}  dd={dd0 * 100:.1f}%  "
          f"sh={sh0:+.2f}   (baseline)", flush=True)
    gate = False
    for a in ALPHAS[1:]:
        tot, dd, sh = stats(a)
        ok = dd <= DD_BAR and tot >= EV_KEEP * tot0
        gate |= ok
        print(f"alpha={a:<4}: total={tot:+.2f}  dd={dd * 100:.1f}%  "
              f"sh={sh:+.2f}  gate={'PASS' if ok else 'fail'}", flush=True)
    print("R-OH-1: " + ("PASS -> prereg R-OB-hedge, smallest alpha "
          "meeting the gate" if gate else
          "PARKED -> rank-one DD structural (5th independent test)"))


if __name__ == "__main__":
    main()
