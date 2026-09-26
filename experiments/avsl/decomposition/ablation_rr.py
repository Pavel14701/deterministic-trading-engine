# -*- coding: utf-8 -*-
"""E3 -- RR ablation (prereg 68953e0 + amendment BEFORE run, STATUS
2026-09-22).

Arms (stop_mode, tp):
  A: frozen   max(|c-line|, 2*ATR14), 5R          [baseline]
  B: atr1     1*ATR14 (floor off),   5R
  C1: frozen  1R
  C15: frozen 1.5R
  D: frozen   reverse-cross exit (trailing)
  E: atr3     3*ATR14 (floor off),   5R
Gates (frozen, on AVSL entries, PRIMARY and F3):
  A > B + 0.05R and A > C1 + 0.10R and A > C15 + 0.10R.
Every arm is ALSO run on the same 100 random-entry draws as E1
(per-asset count/side matched, seeds 0..99) -> per-arm random-
geometry EV (descriptive read-out that decomposes the null).

Run:  uv run python -m experiments.avsl.decomposition.ablation_rr
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    HORIZON,
    TAKER_FEE,
    WARMUP,
    repo_root,
)
from experiments.avsl.decomposition.ablation_entry import (
    MARGIN_R,
    N_DRAWS,
    SPLIT_FRAC,
    _env,
)
from experiments.avsl.cross_confirm.avsl_cross_confirm import _nw_z


NW_LAGS = 500

ARMS = (
    ("A", "frozen", 5.0),
    ("B", "atr1", 5.0),
    ("C1", "frozen", 1.0),
    ("C15", "frozen", 1.5),
    ("E", "atr3", 5.0),
)


def _risk(env: dict, t: int, is_long: bool, mode: str) -> float:
    cp, line, atr = env["cp"], env["line"], env["atr"]
    if mode == "frozen":
        return max(abs(cp[t] - line[t]), 2.0 * atr[t])
    if mode == "atr1":
        return atr[t]
    if mode == "atr3":
        return 3.0 * atr[t]
    raise ValueError(mode)


def _exit_revcross(env: dict, t: int, is_long: bool) -> int:
    """First OPPOSITE cross bar after t (exit at its close), capped
    at the HORIZON.  -1 if none within the data."""
    dirs = env["up"][env["cross_idx"] - 1]      # True=up cross
    want_up = not is_long                        # long exits on dn cross
    bars = env["cross_idx"][dirs == want_up]
    nxt = bars[bars > t]
    if nxt.size == 0:
        return -1
    return int(min(nxt[0], t + HORIZON))


def _trade(env: dict, t: int, is_long: bool, mode: str,
           tp_r: float, revcross: bool) -> dict | None:
    hp, lp, cp = env["hp"], env["lp"], env["cp"]
    risk = _risk(env, t, is_long, mode)
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    tp_px = entry + tp_r * risk if is_long else entry - tp_r * risk
    n = len(cp)
    k_exit = _exit_revcross(env, t, is_long) if revcross \
        else min(t + HORIZON, n - 1)
    if k_exit < 0:
        k_exit = n - 1
    pnl = 0.0
    hit = False
    # walk until the exit bar; conservative within-bar (stop wins)
    for k in range(t + 1, min(k_exit + 1, n)):
        if is_long:
            if lp[k] <= stop:
                pnl, hit = -1.0, True
                break
            if not revcross and hp[k] >= tp_px:
                pnl, hit = tp_r, True
                break
        else:
            if hp[k] >= stop:
                pnl, hit = -1.0, True
                break
            if not revcross and lp[k] <= tp_px:
                pnl, hit = tp_r, True
                break
    if not hit:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {
        "net": pnl - fee_r,
        "e0": int(env["b"][t]) - env["g0"],
        "long": is_long,
    }


def _segment_stats(trades: list[dict], split: int,
                   which: str) -> tuple:
    want_primary = which == "PRIMARY"
    sel = [t for t in trades
           if (t["e0"] < split) == want_primary]
    net = np.array([t["net"] for t in sel])
    order = np.argsort([t["e0"] for t in sel])
    return (float(net.mean()), len(sel),
            float(_nw_z(net[order], NW_LAGS)))


def _run_entries(envs, entries, mode, tp_r, revcross):
    out: list[dict] = []
    for s in ASSETS:
        e = envs[s]
        for t, is_long in entries[s]:
            tr = _trade(e, t, is_long, mode, tp_r, revcross)
            if tr is not None:
                out.append({**tr, "sym": s})
    return out


def main() -> None:
    repo = repo_root()
    envs = {s: _env(s, repo) for s in ASSETS}
    g0 = min(e["g0"] for e in envs.values())
    n_g = max(e["n_bars"] + e["g0"] for e in envs.values()) - g0
    split = int(n_g * SPLIT_FRAC)
    print(f"global grid n={n_g}, PRIMARY<{split}<=F3", flush=True)

    entries = {s: [(int(t), bool(e["up"][t - 1]))
                   for t in e["cross_idx"] if t >= WARMUP]
               for s, e in envs.items()}
    match = {}
    for s in ASSETS:
        tr = entries[s]
        n_long = sum(1 for _, L in tr if L)
        match[s] = {
            "n": len(tr),
            "p_long": n_long / len(tr) if tr else 0.5,
        }

    # ---- arms on the AVSL entries
    arm_ev: dict = {}
    for name, mode, tp in ARMS:
        rev = name == "D"
        trades = _run_entries(envs, entries, mode, tp, rev)
        arm_ev[name] = trades
        p = _segment_stats(trades, split, "PRIMARY")
        f = _segment_stats(trades, split, "F3")
        print(f"arm {name:>3}: PRIMARY EV={p[0]:+.3f}R (n={p[1]}, "
              f"z={p[2]:+.2f}) | F3 EV={f[0]:+.3f}R (n={f[1]}, "
              f"z={f[2]:+.2f})", flush=True)

    # sanity: arm A must match the E1 arm A numbers
    a_p = _segment_stats(arm_ev["A"], split, "PRIMARY")
    a_f = _segment_stats(arm_ev["A"], split, "F3")
    ok = abs(a_p[0] - 0.172) < 0.002 and abs(a_f[0] - 0.335) < 0.002
    print(f"sanity: arm A EV {a_p[0]:+.3f}/{a_f[0]:+.3f} vs E1 "
          f"+0.172/+0.335 -> {'MATCH' if ok else 'MISMATCH'}",
          flush=True)

    # ---- random-geometry baselines per arm (E1 procedure, seeds 0..99)
    # arm A's random baseline is the published E1 result -- reused.
    rnd: dict = {}
    for name, mode, tp in ARMS[1:]:
        rev = name == "D"
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
                    tr = _trade(envs[s], int(t), is_long, mode,
                                tp, rev)
                    if tr is not None:
                        draw.append(tr)
            for seg in ("PRIMARY", "F3"):
                b_ev[seg].append(_segment_stats(draw, split, seg)[0])
            if (seed + 1) % 50 == 0:
                print(f"  {name}: draw {seed + 1}/{N_DRAWS}",
                      flush=True)
        rnd[name] = {
            seg: (float(np.mean(v)), float(np.std(v)))
            for seg, v in b_ev.items()
        }
        print(f"null {name:>3}: PRIMARY {rnd[name]['PRIMARY'][0]:+.3f}"
              f"+-{rnd[name]['PRIMARY'][1]:.3f} | "
              f"F3 {rnd[name]['F3'][0]:+.3f}"
              f"+-{rnd[name]['F3'][1]:.3f}", flush=True)
    # published E1 null for arm A (same seeds/procedure)
    rnd["A"] = {"PRIMARY": (0.135, 0.044), "F3": (0.168, 0.068)}

    # ---- frozen gates
    print("\n==== E3 GATES (A > arm + margin, both segments) ====",
          flush=True)
    fails = []
    for arm, margin in (("B", MARGIN_R), ("C1", 2 * MARGIN_R),
                        ("C15", 2 * MARGIN_R)):
        for seg in ("PRIMARY", "F3"):
            ev_a = _segment_stats(arm_ev["A"], split, seg)[0]
            ev_x = _segment_stats(arm_ev[arm], split, seg)[0]
            ok = ev_a > ev_x + margin
            if not ok:
                fails.append((arm, seg))
            print(f"  A vs {arm:>3} {seg:>7}: {ev_a:+.3f} vs "
                  f"{ev_x:+.3f} (margin {margin:+.2f}) -> "
                  f"{'PASS' if ok else 'FAIL'}", flush=True)

    print("\n==== E3 VERDICT ====", flush=True)
    if fails:
        print(f"FAIL {fails}: per prereg, the killed components "
              "(floor-off stop / narrow TP) are NOT critical -- the "
              "null lives elsewhere in the geometry", flush=True)
    else:
        print("ALL GATES PASS: the wide-stop floor and the wide TP "
              "are both critical components of the geometry edge",
              flush=True)
    print("\nrandom-geometry decomposition (null per arm, mean+-sd):")
    for name in ("A", "B", "C1", "C15", "E"):
        for seg in ("PRIMARY", "F3"):
            mu, sd = rnd[name][seg]
            print(f"  {name:>3} {seg:>7}: {mu:+.3f}+-{sd:.3f}",
                  flush=True)


if __name__ == "__main__":
    main()

