# -*- coding: utf-8 -*-
"""Parity gate for the AVSL live-scale Phase A pilot.

Prereg: STATUS.md, "AVSL LIVE-SCALE PREREG (2026-09-22, FROZEN
BEFORE ANY LIVE CODE)" -- PARITY hard gate: on every closed 4H bar
the live signal must equal the frozen module's recomputation on the
same bars; ANY mismatch -> STOP + post-mortem before resume.

Implementation: the paper pilot's "live" path is incremental -- at
each update ``pilot_tracker`` records new entries from the freshly
appended kline cache.  This script is the independent check:
recompute the frozen module on the FULL refreshed series (the
engine self-check path) and demand that

  1. the frozen module file is byte-identical to the sha pinned at
     seed time (mutation guard);
  2. every entry recorded by the tracker inside the pilot window
     still exists with the same bucket and side (no repaint);
  3. the tracker missed no closed-bar entry the recomputation sees;
  4. recomputation is deterministic (run twice, compared).

Only CLOSED 4H buckets are considered (a bucket is closed when a
later bucket exists in the series).  Any violation -> exit 1.

Run:
  uv run python -m experiments.live.parity_check             # with fetch
  uv run python -m experiments.live.parity_check --no-fetch  # cache only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys

from pathlib import Path

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    collect_trades,
    read_1h,
    repo_root,
    resample_4h,
)


def state_path(repo: Path) -> Path:
    return repo / "runs" / "live_pilot" / "state.json"


def load_state(repo: Path) -> dict:
    p = state_path(repo)
    if not p.exists():
        print("PARITY FAIL: no pilot state "
              "(run `pilot_tracker seed` first)")
        raise SystemExit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def frozen_sha(repo: Path) -> str:
    src = (repo / "engine" / "passed" / "avsl_cross_s1.py").read_bytes()
    return hashlib.sha256(src).hexdigest()


def refresh_cache(repo: Path) -> None:
    """Append fresh 1H klines via the existing loader (kl only).

    The loader is experiments.loaders.load_binance and takes FULL
    Binance symbols (BTCUSDT), not the bare ASSETS tags; a bare tag
    falls through its symbol filter and silently triggers a fetch of
    its entire default universe (fixed 2026-09-23, STATUS).
    """
    subprocess.run(
        [sys.executable, "-m", "experiments.loaders.load_binance",
         *(s + "USDT" for s in ASSETS), "kl"],
        check=False, cwd=str(repo),
    )


def last_closed_bucket(repo: Path, sym: str) -> int:
    """Latest 4H bucket that is fully formed in the cache."""
    ts, _hp, _lp, _cp, _vol = resample_4h(*read_1h(repo, sym))
    return int(ts[-1]) // 14_400_000 - 1


def recompute_entries(repo: Path) -> dict[str, set[tuple[int, bool]]]:
    """Full-series frozen recomputation, closed buckets only:
    {(abs_bucket, is_long)} per asset."""
    out: dict[str, set[tuple[int, bool]]] = {}
    for sym in ASSETS:
        d = collect_trades(sym, repo)
        cut = last_closed_bucket(repo, sym)
        out[sym] = {
            (d["g0"] + t["e0"], bool(t["long"]))
            for t in d["trades"]
            if d["g0"] + t["e0"] <= cut
        }
    return out


def check(repo: Path | None = None, do_fetch: bool = True) -> bool:
    repo = repo or repo_root()
    st = load_state(repo)
    if frozen_sha(repo) != st["frozen_sha"]:
        print("PARITY FAIL: engine/passed/avsl_cross_s1.py changed "
              "since seed -- frozen module mutated")
        return False
    if do_fetch:
        refresh_cache(repo)
    full1 = recompute_entries(repo)
    full2 = recompute_entries(repo)
    for sym in ASSETS:
        if full1[sym] != full2[sym]:
            print(f"PARITY FAIL: {sym} nondeterministic recomputation")
            return False
    start = int(st["pilot_start_bucket"])
    fails: list[str] = []
    for sym in ASSETS:
        live = {
            (int(b), bool(s))
            for b, s in st["entries"].get(sym, [])
        }
        want = {e for e in full1[sym] if e[0] >= start}
        if live - want:
            fails.append(f"{sym}: repaint/phantom entries "
                         f"{sorted(live - want)[:3]}")
        if want - live:
            fails.append(f"{sym}: missed closed-bar entries "
                         f"{sorted(want - live)[:3]}")
    if fails:
        for f in fails:
            print("PARITY FAIL:", f)
        return False
    n = sum(len(v) for v in st["entries"].values())
    print(f"PARITY OK: tracker == full recomputation "
          f"(pilot window, {n} entries)")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="skip the loader refresh, use the cache as-is")
    args = ap.parse_args()
    raise SystemExit(0 if check(do_fetch=not args.no_fetch) else 1)


if __name__ == "__main__":
    main()
