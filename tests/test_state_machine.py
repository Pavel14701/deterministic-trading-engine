"""Stage D.1 transition tests: pure state machine, documented rules."""

import numpy as np
import pytest

from ai.state_machine import run_state_machine


def sig(idx, side, r=1.0, exit_offset=5, prio=0.0):
    return {
        "cand": f"{idx}_{side}",
        "decision_idx": idx,
        "side": side,
        "priority": prio,
        "r_net": r,
        "exit_idx": idx + exit_offset,
    }


def test_long_flat_sl_same_bar_then_flat():
    # one long trade: slot busy until exit bar, then free
    taken, _skipped = run_state_machine([sig(10, "long", r=-1.0, exit_offset=3)])
    assert [t["cand"] for t in taken] == ["10_long"]
    assert taken[0]["exit_idx"] == 13  # closed intrabar at bar 13


def test_reverse_signal_ignored_while_in_position():
    taken, skipped = run_state_machine(
        [sig(10, "long", exit_offset=5), sig(12, "short")]
    )
    assert [t["cand"] for t in taken] == ["10_long"]
    assert skipped[0]["reason"] == "in_position"


def test_allow_reverse_opens_opposite_side():
    taken, _ = run_state_machine(
        [sig(10, "long", exit_offset=5), sig(12, "short", exit_offset=4)],
        allow_reverse=True,
    )
    assert [t["side"] for t in taken] == ["long", "short"]


def test_same_bar_sl_plus_reverse_not_reentered():
    # SL closes at bar 13; a reverse signal decided at bar 13 (same bar)
    # must NOT open a position - SL-first pessimism means we are still
    # in the trade during that bar
    taken, skipped = run_state_machine(
        [sig(10, "long", exit_offset=3), sig(13, "short")]
    )
    assert [t["cand"] for t in taken] == ["10_long"]
    assert skipped[0]["reason"] == "same_bar_after_exit"


def test_cooldown_blocks_then_allows():
    sigs = [sig(10, "long", exit_offset=3), sig(14, "short"), sig(16, "short")]
    taken, skipped = run_state_machine(sigs, cooldown=3)
    assert skipped[0]["reason"] == "cooldown"  # bar 14 < 13 + 3
    assert [t["cand"] for t in taken] == ["10_long", "16_short"]


def test_same_bar_signals_priority_wins():
    taken, _ = run_state_machine(
        [sig(10, "long", prio=0.3), sig(10, "short", prio=0.9)]
    )
    assert [t["cand"] for t in taken] == ["10_short"]


def test_equivalence_with_isolated_simulator():
    # non-overlapping signals with cooldown=0: the machine must take
    # every trade and preserve its isolated r_net exactly
    rng = np.random.default_rng(7)
    sigs, cursor = [], 0
    for i in range(50):
        idx = cursor
        r = float(rng.normal(0.2, 1.0))
        exit_offset = int(rng.integers(1, 20))
        sigs.append(sig(idx, "long" if i % 2 else "short", r=r, exit_offset=exit_offset))
        cursor = idx + exit_offset + 1  # decision strictly after exit bar
    taken, skipped = run_state_machine(sigs)
    assert not skipped
    assert [t["r_net"] for t in taken] == [s["r_net"] for s in sigs]
    # total EV identical to the isolated backtest sum
    assert np.mean([t["r_net"] for t in taken]) == pytest.approx(
        float(np.mean([s["r_net"] for s in sigs]))
    )
