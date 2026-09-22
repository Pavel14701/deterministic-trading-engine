"""Portfolio admission policies over a capped slot stream.

Finding (robustness checks): first-come-first-served capping rejects
BETTER trades (rejected mean r_pess +0.484 vs accepted +0.441) - pure
capacity loss, and reject rate drifts 16%->24% as candidate density
grows.

Policies on the same 1040-trade WF-B stream (cap = 2 concurrent, one
crypto cluster):
  FCFS         - current: slots full -> reject.
  REPLACE-low  - slots full -> if new score > worst open score, close
                 worst and take new; replaced trade contributes 0
                 (conservative: mid-flight close assumed to give back).
  REPLACE-high - same, but replaced trade keeps its full isolated
                 r_pess (optimistic bound).
Realized equity is event-based (R credited at exit) -> DD not flattered
by daily aggregation.  The policy comparison experiment lives in
``experiments.admission_policies``.
"""

from __future__ import annotations

from typing import Any

import numpy as np


CAP = 2


def run_policy(policy: str, trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay one admission policy over the WF-B trade stream.

    Returns ``{"n", "ev", "dd", "replaced"}``: entered trades, event
    equity (R at exits), event-basis max drawdown, replaced count.
    """
    open_pos: list[dict[str, Any]] = []
    entered: list[dict[str, Any]] = []
    replaced: list[dict[str, Any]] = []
    for r in trades:
        open_pos = [x for x in open_pos if x["ts_exit"] > r["ts_entry"]]
        if len(open_pos) < CAP:
            open_pos.append(r)
            entered.append(r)
        elif policy.startswith("REPLACE"):
            worst = min(open_pos, key=lambda x: x["s"])
            if r["s"] > worst["s"]:
                open_pos.remove(worst)
                open_pos.append(r)
                entered.append(r)
                replaced.append(worst)
    # event equity: contributions at exits; replaced contribute 0 (low):
    # mid-flight close assumed to give back; full r_pess if REPLACE-high
    ev = []
    for r in entered:
        if any(r is x for x in replaced):
            replaced_r = 0.0 if policy == "REPLACE-low" else r["r_pess"]
            ev.append((r["ts_exit"], replaced_r))
        else:
            ev.append((r["ts_exit"], r["r_pess"]))
    ev.sort(key=lambda x: x[0])
    eq = np.cumsum([x[1] for x in ev])
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))
    dd = float(np.max(peak[1:] - eq))
    return {"n": len(entered), "ev": float(eq[-1]),
            "dd": dd, "replaced": len(replaced)}


