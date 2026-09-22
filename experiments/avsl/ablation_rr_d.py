# -*- coding: utf-8 -*-
"""E3 arm D -- reverse-cross trailing exit (prereg 68953e0).

Omitted from the first ablation_rr pass by implementation error; run
here separately with the SAME frozen procedure (same AVSL entries,
same 100 random draws, seeds 0..99).  D is descriptive (not gated).

Run:  uv run python -m experiments.avsl.ablation_rr_d
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    WARMUP,
    repo_root,
)
from experiments.avsl.ablation_rr import (
    N_DRAWS,
    _env,
    _run_entries,
    _segment_stats,
    _trade,
)


SPLIT_FRAC = 2 / 3


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)

    entries = {s: [(int(t), bool(e["up"][t - 1]))
                   for t in e["cross_idx"] if t >= WARMUP]
               for s, e in envs.items()}
    match = {}
    for s in ASSETS:
        tr = entries[s]
        n_long = sum(1 for _, L in tr if L)
        match[s] = {"n": len(tr),
                    "p_long": n_long / len(tr) if tr else 0.5}

    trades = _run_entries(envs, entries, "frozen", 5.0, True)
    p = _segment_stats(trades, split, "PRIMARY")
    f = _segment_stats(trades, split, "F3")
    print(f"arm D: PRIMARY EV={p[0]:+.3f}R (n={p[1]}, z={p[2]:+.2f}) "
          f"| F3 EV={f[0]:+.3f}R (n={f[1]}, z={f[2]:+.2f})",
          flush=True)

    b_ev = {"PRIMARY": [], "F3": []}
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        draw: list[dict] = []
        for s in ASSETS:
            m = match[s]
            if m["n"] == 0:
                continue
            bars = rng.choice(
                np.arange(WARMUP, envs[s]["n_bars"] - 1),
                size=m["n"], replace=False,
            )
            for t in bars:
                is_long = bool(rng.random() < m["p_long"])
                tr = _trade(envs[s], int(t), is_long,
                            "frozen", 5.0, True)
                if tr is not None:
                    draw.append(tr)
        for seg in ("PRIMARY", "F3"):
            b_ev[seg].append(_segment_stats(draw, split, seg)[0])
        if (seed + 1) % 50 == 0:
            print(f"  D: draw {seed + 1}/{N_DRAWS}", flush=True)
    for seg in ("PRIMARY", "F3"):
        v = np.array(b_ev[seg])
        print(f"null   D {seg:>7}: {v.mean():+.3f}+-{v.std():.3f}",
              flush=True)


if __name__ == "__main__":
    main()
