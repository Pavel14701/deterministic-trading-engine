"""Position state machine over the policy's candidate signals.

The dataset builder simulates every candidate in isolation; live, one
slot is occupied at a time.  This machine walks signals chronologically
and decides which trades actually happen.

Transition specification (documented decisions, see STATUS.md):

- a signal decided at bar ``d`` fills at ``d + 1`` (generator rule);
- while a position is open (until its ``exit_idx``), ALL new signals
  are skipped (``in_position``); opposite-side signals too, unless
  ``allow_reverse`` is set: an opposite signal at bar ``d < exit_idx``
  force-closes the open trade at bar ``d`` (flagged
  ``force_exit_idx``; its isolated ``r_net``/``exit_idx`` are STALE -
  the caller MUST recompute its P&L up to ``d`` before use) and opens
  the new side at ``d + 1``.  Without recomputation the stats would
  double-count overlapping exposure, so the flag is the contract;
- same-bar exit + signal (decision bar == exit bar) is skipped unless
  ``same_bar_reentry`` - the SL-first pessimism rule means the
  position is still "held" during that bar;
- after an exit, ``cooldown`` further decision bars are blocked
  (cooldown=0 keeps equivalence with the isolated simulator);
- several signals on one bar: highest ``priority`` wins (deterministic);
- a trade whose ``exit_idx == -1`` (data ended while open) occupies
  the slot until the end of data.
"""

from __future__ import annotations

from typing import Any, Iterable


def run_state_machine(
    signals: Iterable[dict[str, Any]],
    cooldown: int = 0,
    allow_reverse: bool = False,
    same_bar_reentry: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Return ``(taken, skipped)``; skipped carry a ``reason`` field."""
    order = sorted(
        signals,
        key=lambda s: (s["decision_idx"], -s.get("priority", 0.0), s["side"]),
    )
    taken: list[dict] = []
    skipped: list[dict] = []
    busy_until = -2  # exit bar of the open position (-2 = none; never a bar)
    busy_side: str | None = None
    open_ended = False

    for sig in order:
        d = int(sig["decision_idx"])
        if open_ended:
            skipped.append(sig | {"reason": "data_ended_open"})
            continue
        if d == busy_until and not same_bar_reentry:
            skipped.append(sig | {"reason": "same_bar_after_exit"})
            continue
        if d <= busy_until:
            reverse = (
                busy_side is not None and allow_reverse
                and sig["side"] != busy_side
            )
            if reverse:
                # true reverse: force-close the open trade at bar d; its
                # isolated r_net/exit_idx are stale (see module docstring)
                if taken:
                    taken[-1]["force_exit_idx"] = d
                taken.append(sig)
                busy_until = int(sig.get("exit_idx", -1))
                busy_side = sig["side"]
                open_ended = busy_until < 0
            else:
                skipped.append(sig | {"reason": "in_position"})
            continue
        if d < busy_until + cooldown:
            skipped.append(sig | {"reason": "cooldown"})
            continue
        taken.append(sig)
        busy_until = int(sig.get("exit_idx", -1))
        busy_side = sig["side"]
        open_ended = busy_until < 0
    return taken, skipped
