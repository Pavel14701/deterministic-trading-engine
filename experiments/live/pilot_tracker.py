# -*- coding: utf-8 -*-
"""Phase A paper-forward shadow pilot for the AVSL live-scale prereg.

STATUS.md, "AVSL LIVE-SCALE PREREG (2026-09-22, FROZEN BEFORE ANY
LIVE CODE)": paper pilot >= 90 days AND >= 50 closed trades; orders
simulated at taker on the live 4H grid; the frozen module
``engine.passed.avsl_cross_s1`` is recomputed on each closed 4H bar.
Sizing/venue/monitoring only -- the signal config moves NOT AT ALL.

Commands:
  seed     initialize the pilot state at the current cache head
  update   refresh cache -> parity gate -> record new entries ->
           resolve matured paper trades -> accrue equity -> brake
  snapshot weekly STATUS block: g-progress + read-outs r1..r4

Frozen pilot gates (Phase A): g1 parity zero mismatches; g2 all-in
cost <= 15 bp RT; g3 brake zero bypasses, snapshots without gaps;
g4 pilot DD <= 25%.  g5: the pilot does NOT judge EV significance.

Paper conventions (declared): fills at the frozen module's entry
convention (cross-bar close), taker 10 bp RT; a 4H bucket is
closed when a later bucket exists; trades whose exit bar is still
open stay PROVISIONAL and are re-priced on later updates; the
disaster brake pauses NEW entries while rolling 90d daily Sharpe
< 0; resumption (Sharpe > 0) writes a dated event -- a dated STATUS
note is still required by the prereg before real resumes.

State: runs/live_pilot/state.json.
"""

from __future__ import annotations

import argparse
import json

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    MSEC_4H,
    RISK_PCT,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from experiments.live.parity_check import (
    check as parity_ok,
    frozen_sha,
    load_state,
    refresh_cache,
    state_path,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _save(repo: Path, st: dict) -> None:
    p = state_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1), encoding="utf-8")


def _buckets(repo: Path, sym: str) -> tuple[np.ndarray, np.ndarray]:
    """(4H bucket ids, closes) for one asset."""
    ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, sym))
    return ts // MSEC_4H, cp


def _f3_rate(repo: Path) -> float:
    """Backtest F3 trades/day, computed once at seed."""
    from engine.passed.avsl_cross_s1 import evaluate

    r = evaluate()
    days = (r["n_g"] - r["split"]) / 6.0
    return float(r["F3"]["n"]) / days


def cmd_seed(repo: Path) -> None:
    p = state_path(repo)
    if p.exists():
        raise SystemExit("state already exists -- refusing to reseed")
    last_closed, start = {}, 0
    for sym in ASSETS:
        b, _cp = _buckets(repo, sym)
        last_closed[sym] = int(b[-1]) - 1
        start = max(start, int(b[-1]))
    # Post-mortem 2026-09-23 (STATUS): start was max(b[-1]) -- the
    # newest CACHED bucket, whose close was already determinable at
    # seed time.  Its entries could never be recorded by the seed,
    # so the first update flagged them as missed closed-bar entries
    # (PARITY FAIL, g1).  Correct convention: the pilot trades only
    # buckets whose close happens AFTER the seed -> start = b[-1]+1.
    start += 1
    st = {
        "frozen_sha": frozen_sha(repo),
        "created": _now(),
        "pilot_start_bucket": start,
        "last_closed": last_closed,
        "entries": {s: [] for s in ASSETS},
        "skipped": {s: [] for s in ASSETS},
        "trades": [],
        "events": [{"date": _now(), "kind": "seed"}],
        "parity_last": "never",
        "brake_active": False,
        "snapshots": [],
        "f3_rate": _f3_rate(repo),
    }
    _save(repo, st)
    print(f"seeded: pilot starts at bucket {start} ({st['created']}), "
          f"F3 reference rate {st['f3_rate']:.3f} trades/day")


def _recompute(repo: Path) -> dict[str, dict]:
    """Frozen-module recomputation per asset + closed-bucket cutoff."""
    out = {}
    for sym in ASSETS:
        b, cp = _buckets(repo, sym)
        d = collect_trades(sym, repo)
        out[sym] = {
            "g0": d["g0"], "b": b, "cp": cp,
            "cut": int(b[-1]) - 1, "trades": d["trades"],
        }
    return out


def _update(repo: Path, do_fetch: bool) -> None:
    st = load_state(repo)
    if frozen_sha(repo) != st["frozen_sha"]:
        raise SystemExit("FROZEN MODULE CHANGED -- pilot invalidated")
    if do_fetch:
        refresh_cache(repo)
    # Post-mortem 2026-09-24 (STATUS): the parity gate used to run
    # HERE, before recording.  It demands every closed in-scope
    # entry to be already in state -- but the entries closed by
    # THIS update's fetch are recorded only LATER in this function,
    # so the pilot's first real entry could never pass the gate
    # (observed: XRP 124317 -> PARITY FAIL on a healthy state).
    # Correct order per the parity docstring (#3): record first,
    # then check the recorded state against the full recomputation.
    # On genuine mismatch the abort still marks the state below.

    rec = _recompute(repo)
    sizes = {sym: s1_sizes(rec[sym]["cp"]) for sym in ASSETS}
    start = int(st["pilot_start_bucket"])
    new_entries, new_resolved = 0, 0
    for sym in ASSETS:
        r = rec[sym]
        if r["cut"] > int(st["last_closed"][sym]):
            st["last_closed"][sym] = r["cut"]
        by_e0 = {r["g0"] + t["e0"]: t for t in r["trades"]}
        known = {e[0] for e in st["entries"][sym]}
        skipped = {e[0] for e in st["skipped"][sym]}
        for e0abs, t in sorted(by_e0.items()):
            if not (start <= e0abs <= r["cut"]):
                continue
            if e0abs in known or e0abs in skipped:
                continue
            if st["brake_active"]:
                st["skipped"][sym].append([int(e0abs), bool(t["long"])])
                st["events"].append({
                    "date": _now(), "kind": "brake_skip",
                    "sym": sym, "bucket": int(e0abs),
                })
                continue
            st["entries"][sym].append([int(e0abs), bool(t["long"])])
            new_entries += 1
            i0 = int(e0abs) - r["g0"]
            resolved = r["g0"] + int(t["e1"]) <= r["cut"]
            st["trades"].append({
                "sym": sym, "e0": int(e0abs),
                "e1": int(r["g0"] + t["e1"]),
                "long": bool(t["long"]),
                "size": float(sizes[sym][i0]),
                "gross": float(t["gross"]),
                "net": float(t["net"]),
                "fee": float(t["fee"]),
                "hold": max(int(t["e1"]) - int(t["e0"]), 1),
                "resolved": resolved,
            })
    # pass 2: finalize previously provisional trades
    for tr in st["trades"]:
        if tr["resolved"]:
            continue
        r = rec[tr["sym"]]
        t = next((x for x in r["trades"]
                  if r["g0"] + x["e0"] == tr["e0"]
                  and bool(x["long"]) == tr["long"]), None)
        if t is None:
            continue
        e1abs = r["g0"] + int(t["e1"])
        was = tr["resolved"]
        tr["e1"] = e1abs
        tr["hold"] = max(e1abs - tr["e0"], 1)
        tr["gross"], tr["net"], tr["fee"] = (
            float(t["gross"]), float(t["net"]), float(t["fee"]))
        if e1abs <= r["cut"]:
            tr["resolved"] = True
            if not was:
                new_resolved += 1
    _save(repo, st)   # persist FIRST: parity_ok reads state.json
    if not parity_ok(repo, do_fetch=False):
        st["parity_last"] = "FAIL " + _now()
        st["events"].append({"date": _now(),
                             "kind": "parity_fail",
                             "new_entries": new_entries,
                             "new_resolved": new_resolved})
        _save(repo, st)
        raise SystemExit("PARITY FAIL -- STOP per prereg g1")
    st["parity_last"] = "OK " + _now()
    st["events"].append({"date": _now(), "kind": "update",
                         "new_entries": new_entries,
                         "new_resolved": new_resolved})
    _save(repo, st)
    n_open = sum(1 for t in st["trades"] if not t["resolved"])
    n_skip = sum(len(v) for v in st["skipped"].values())
    print(f"update: +{new_entries} entries, +{new_resolved} resolved, "
          f"{n_open} provisional, {n_skip} brake-skipped")


def _equity(st: dict) -> np.ndarray:
    """Global 4H accrual stream over RESOLVED pilot trades (1% risk
    convention of the frozen module, unscaled by RISK_PCT)."""
    if not st["trades"]:
        return np.zeros(1)
    lo = int(st["pilot_start_bucket"])
    hi = max(t["e1"] for t in st["trades"])
    s = np.zeros(hi - lo + 2)
    for t in st["trades"]:
        if not t["resolved"]:
            continue
        w = t["size"] * t["net"] / (t["hold"] + 1)
        a = max(t["e0"] - lo, 0)
        b = min(t["e1"] - lo, hi - lo)
        s[a:b + 1] += w
    return s[:hi - lo + 1]


def _daily(v: np.ndarray) -> np.ndarray:
    n = (len(v) // 6) * 6
    return v[:n].reshape(-1, 6).sum(axis=1)


def _readouts(st: dict, repo: Path) -> dict:
    from ta.src.volatility.atr import atr_ind

    out: dict = {}
    # r1: rolling 90d daily Sharpe + disaster brake
    daily = _daily(_equity(st) * RISK_PCT)
    out["n_days"] = int(daily.size)
    if daily.size >= 91:
        w = daily[-90:]
        sd = float(w.std(ddof=1))
        out["r1_sharpe90"] = float(w.mean()) / sd * np.sqrt(365) \
            if sd > 0 else float("nan")
        was = st["brake_active"]
        if out["r1_sharpe90"] < 0 and not was:
            st["brake_active"] = True
            st["events"].append({"date": _now(), "kind": "brake_on"})
        elif out["r1_sharpe90"] >= 0 and was:
            st["brake_active"] = False
            st["events"].append({
                "date": _now(), "kind": "brake_off",
                "note": "dated STATUS note required before any real "
                        "resumption (prereg)",
            })
    else:
        out["r1_sharpe90"] = float("nan")
    out["brake_active"] = st["brake_active"]
    # g4: pilot DD on the daily account stream
    eq = np.cumprod(1.0 + daily)
    out["pilot_dd"] = float(np.max(
        1.0 - eq / np.maximum.accumulate(eq))) if daily.size else 0.0
    # r2: ATR percentile (500-bar) at the last closed bar, per asset
    pcts = []
    for sym in ASSETS:
        _ts, hp, lp, cp, _vol = resample_4h(*read_1h(repo, sym))
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        win = atr[max(0, len(atr) - 501):-1]
        win = win[np.isfinite(win)]
        if win.size and np.isfinite(atr[-2]):
            pcts.append(float((win <= atr[-2]).mean() * 100))
    out["r2_atr_pct"] = float(np.median(pcts)) if pcts else float("nan")
    out["r2_regime"] = ("low" if out["r2_atr_pct"] < 50 else "high")
    # r3: corr(|daily ret|, mean active S1 size) -- monitoring proxy
    r3 = float("nan")
    if daily.size >= 21:
        lo = int(st["pilot_start_bucket"])
        nd = daily.size
        sizes_sum = np.zeros(nd)
        sizes_cnt = np.zeros(nd)
        for t in st["trades"]:
            if not t["resolved"]:
                continue
            a = max(t["e0"] - lo, 0) // 6
            b = min(t["e1"] - lo, nd * 6 - 1) // 6
            for d in range(a, min(b, nd - 1) + 1):
                sizes_sum[d] += t["size"]
                sizes_cnt[d] += 1
        mean_size = np.where(sizes_cnt > 0, sizes_sum /
                             np.maximum(sizes_cnt, 1), np.nan)
        ok = np.isfinite(mean_size) & np.isfinite(daily)
        if ok.sum() >= 21 and np.nanstd(mean_size[ok]) > 0:
            r3 = float(np.corrcoef(np.abs(daily[ok]),
                                   mean_size[ok])[0, 1])
    out["r3_corr_vol_size"] = r3
    # r4: closed-trade rate vs the backtest F3 reference
    from datetime import date

    days = max((date.today()
                - date.fromisoformat(st["created"])).days, 0)
    closed = sum(1 for t in st["trades"] if t["resolved"])
    out["days_elapsed"] = days
    out["closed_trades"] = closed
    out["r4_rate"] = closed / days if days else float("nan")
    out["r4_ref"] = st["f3_rate"]
    return out


def cmd_snapshot(repo: Path) -> None:
    st = load_state(repo)
    ro = _readouts(st, repo)
    st["snapshots"].append({"date": _now(), **{
        k: v for k, v in ro.items()}})
    _save(repo, st)
    print(f"PILOT SNAPSHOT {ro['days_elapsed']}d "
          f"(Phase A target: >=90d AND >=50 closed trades)")
    print(f"  parity_last   {st['parity_last']}")
    print(f"  r1 shp90      {ro['r1_sharpe90']:+.2f}   "
          f"brake {'ACTIVE' if ro['brake_active'] else 'idle'}")
    print(f"  r2 ATR pct    {ro['r2_atr_pct']:.0f} "
          f"({ro['r2_regime']}-vol)")
    print(f"  r3 corr       {ro['r3_corr_vol_size']:+.2f}")
    print(f"  r4 trades/day {ro['r4_rate']:.3f} "
          f"(F3 ref {ro['r4_ref']:.3f}), "
          f"closed {ro['closed_trades']}")
    print(f"  g4 pilot DD   {ro['pilot_dd']:.1%} (gate <= 25%)")
    print(f"  snapshots     {len(st['snapshots'])} "
          f"(last {st['snapshots'][-1]['date']})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("seed", "update", "snapshot"))
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    repo = repo_root()
    if args.cmd == "seed":
        cmd_seed(repo)
    elif args.cmd == "update":
        _update(repo, do_fetch=not args.no_fetch)
    else:
        cmd_snapshot(repo)


if __name__ == "__main__":
    main()


