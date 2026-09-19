"""Position state machine over the policy's candidate signals (Stage D.1).

The dataset builder simulates every candidate in isolation; live, one
slot is occupied at a time.  This machine walks signals chronologically
and decides which trades actually happen.

Transition specification (documented decisions, see STATUS.md D.1):

- a signal decided at bar ``d`` fills at ``d + 1`` (generator rule);
- while a position is open (until its ``exit_idx``), ALL new signals
  are skipped (``in_position``); opposite-side signals too, unless
  ``allow_reverse`` is set (then the signal at bar >= exit bar closes
  the old position and opens the new one at its own fill bar);
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
    busy_until = -1  # exit bar of the open position (-1 = none)
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
            if busy_side is not None and allow_reverse and sig["side"] != busy_side:
                taken.append(sig)  # reverse closes the old, opens new
                busy_until = int(sig.get("exit_idx", -1))
                busy_side = sig["side"]
                open_ended = busy_until < 0
            else:
                skipped.append(sig | {"reason": "in_position"})
            continue
        if not same_bar_reentry and d == busy_until:
            skipped.append(sig | {"reason": "same_bar_after_exit"})
            continue
        if d < busy_until + cooldown:
            skipped.append(sig | {"reason": "cooldown"})
            continue
        taken.append(sig)
        busy_until = int(sig.get("exit_idx", -1))
        busy_side = sig["side"]
        open_ended = busy_until < 0
    return taken, skipped
