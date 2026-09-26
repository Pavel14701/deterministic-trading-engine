# -*- coding: utf-8 -*-
"""E4 -- SIZING ablation on the frozen bar stream (prereg 68953e0).

Arms:
  A unsized (1.0)   B S1 vol-target (frozen)   D constant 0.33
  C PERMUTED S1 sizes: B's per-trade sizes shuffled across the trade
  order, seeds 0..99 -- breaks the vol-size link, keeps the marginal
  size distribution.
Metrics: Sharpe_NW, DD on the account stream (PRIMARY / F3).
Gate (frozen): B Sharpe_NW > mean(C) + 0.2 on PRIMARY and F3.
Kill: B ~ C -> vol-target timing carries no information (pure
de-lever).  EV/trade is sizing-invariant and not a gate here.

Run:  uv run python -m experiments.avsl.decomposition.ablation_sizing
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    SPLIT_FRAC,
    collect_trades,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)


N_PERM = 100
MARGIN_SHARPE = 0.2
CONST_SIZE = 0.33


def _stream(trades: list[dict], sz: np.ndarray,
            n_g: int) -> np.ndarray:
    """Portfolio accrual stream with per-trade sizes (engine
    semantics: size x netR spread linearly over [e0, e1])."""
    s = np.zeros(n_g + 1)
    for tr, size in zip(trades, sz, strict=True):
        hold = max(tr["e1"] - tr["e0"], 1)
        s[tr["e0"]:tr["e1"] + 1] += size * tr["net"] / (hold + 1)
    return s[:n_g]


def _metrics(stream: np.ndarray, split: int) -> dict:
    return {
        seg: (nw_sharpe(stream[lo:hi]),
              portfolio_dd(stream[lo:hi]))
        for seg, lo, hi in (("PRIMARY", 0, split),
                            ("F3", split, len(stream)))
    }


def main() -> None:
    repo = repo_root()
    per = {s: collect_trades(s, repo) for s in ASSETS}
    g0 = min(d["g0"] for d in per.values())
    n_g = max(d["n_bars"] + d["g0"] for d in per.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    trades: list[dict] = []
    for s, d in per.items():
        trades.extend({**tr, "sym": s} for tr in d["trades"])
    trades.sort(key=lambda t: (t["e0"], t["sym"]))
    n_tr = len(trades)
    print(f"global 4H grid n={n_g}, split@{split}, "
          f"trades={n_tr}", flush=True)

    sizes_by = {}
    for s in ASSETS:
        cp4h = resample_4h(*read_1h(repo, s))[3]
        sizes_by[s] = s1_sizes(cp4h)
    b_sizes = np.array([sizes_by[t["sym"]][t["e0"]]
                        for t in trades])

    arms: dict[str, np.ndarray] = {
        "A unsized": _stream(trades, np.ones(n_tr), n_g),
        "B S1": _stream(trades, b_sizes, n_g),
        "D 0.33": _stream(trades, np.full(n_tr, CONST_SIZE), n_g),
    }

    c_sharpes: dict = {"PRIMARY": [], "F3": []}
    for seed in range(N_PERM):
        rng = np.random.default_rng(seed)
        perm = rng.permutation(b_sizes)
        stream = _stream(trades, perm, n_g)
        m = _metrics(stream, split)
        for seg in ("PRIMARY", "F3"):
            c_sharpes[seg].append(m[seg][0])
        if (seed + 1) % 25 == 0:
            print(f"  perm {seed + 1}/{N_PERM}", flush=True)

    print("\narm            PRIMARY              F3", flush=True)
    metrics: dict = {}
    for name, stream in arms.items():
        row = _metrics(stream, split)
        metrics[name] = row
        print(f"{name:>10}  Sh {row['PRIMARY'][0]:+.2f} "
              f"DD {row['PRIMARY'][1]:.0%}    "
              f"Sh {row['F3'][0]:+.2f} DD {row['F3'][1]:.0%}",
              flush=True)
    for seg in ("PRIMARY", "F3"):
        v = np.array(c_sharpes[seg])
        print(f"{'C perm':>10}  Sharpe {v.mean():+.2f}"
              f"+-{v.std():.2f}", flush=True)
        metrics[f"C_{seg}"] = (float(v.mean()), float(v.std()))

    print("\n==== E4 GATE (B > mean(C) + 0.2, both segments) ====",
          flush=True)
    verdict = "PASS"
    for seg in ("PRIMARY", "F3"):
        b = metrics["B S1"][seg][0]
        cm, csd = metrics[f"C_{seg}"]
        gate = b > cm + MARGIN_SHARPE
        verdict = verdict if gate else "FAIL"
        print(f"  {seg}: B {b:+.2f} vs C {cm:+.2f}+-{csd:.2f} "
              f"(margin +{MARGIN_SHARPE:.1f}) -> "
              f"{'PASS' if gate else 'FAIL'}", flush=True)
    print(f"\nE4 VERDICT: {verdict}", flush=True)
    if verdict == "FAIL":
        print("Kill interpretation per prereg: vol-target timing "
              "carries no information beyond de-levering.",
              flush=True)


if __name__ == "__main__":
    main()
