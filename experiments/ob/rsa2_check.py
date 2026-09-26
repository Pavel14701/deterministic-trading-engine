# -*- coding: utf-8 -*-
"""R-SSA-2 feasibility gate -- runner for the prereg frozen in
STATUS (2026-09-24, commit 225b2ca).  SSA-denoised close with wick
shape preserved (variant C) feeds the R2 OB detector; everything
else (retest entries, stop 3xATR, TP {3,5,8}R primary 5R, horizon
500, fee) is the frozen E8b frame computed on RAW OHLC.

Arms: A = raw OHLC -> detector; B = SSA-OHLC -> detector.
Gate: PASS iff B.EV >= A.EV AND B.maxDD < A.maxDD (pooled,
equal-risk cum-R stream).  Read-outs per prereg incl. the SSA->raw
retest-event lag.  One-shot: no W/k search.

Run:  uv run python -m experiments.ob.rsa2_check
"""

from __future__ import annotations

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    read_1h,
    repo_root,
    resample_4h,
)
from experiments.avsl.retest_entry import WARMUP
from experiments.debug.ssa_avsl_check import (
    SSA_W,
    ssa_denoise_line,
)
from experiments.ob.ob_risk_overlay import TP_PRIMARY, _trade_tp
from ta.src.volatility.atr import atr_ind


def _events(hp: np.ndarray, lp: np.ndarray, cp: np.ndarray,
            ts: np.ndarray, vol: np.ndarray) -> tuple[np.ndarray,
                                                      np.ndarray]:
    """R2-detector retest events for the given OHLC (prereg: this is
    the ONLY thing that differs between arms)."""
    from experiments.ob.research_presets import R2
    from ta.src.custom.market_structure import identify_order_blocks

    df = pl.DataFrame({
        "date": pl.from_epoch(ts, time_unit="ms"),
        "high": hp, "low": lp, "close": cp, "volume": vol,
    })
    blocks = identify_order_blocks(df, cfg=R2)
    pos = {d: i for i, d in enumerate(df["date"].to_list())}
    ev = sorted((pos[r["retest"]], r["block_type"] == "demand")
                for r in blocks.iter_rows(named=True)
                if r["retest"] in pos)
    return (np.array([e[0] for e in ev], dtype=np.int64),
            np.array([e[1] for e in ev], dtype=bool))


def _simulate(env: dict, idx: np.ndarray, side: np.ndarray
              ) -> tuple[list[dict], int]:
    """Frozen E8b sim on RAW OHLC at the arm's event bars."""
    trades: list[dict] = []
    n_ev = len(idx)
    for t, is_long in zip(idx, side, strict=True):
        if t < WARMUP:
            continue
        d = _trade_tp(env, int(t), bool(is_long), TP_PRIMARY)
        if d is None:
            continue
        trades.append(d)
    return trades, n_ev


def _stats(trades: list[dict], n_ev: int) -> dict:
    if not trades:
        return {"n_ev": 0, "n_tr": 0, "ev": 0.0, "win": 0.0,
                "tot": 0.0, "dd": 0.0, "n_long": 0}
    net = np.array([t["net"] for t in trades])
    cum = np.concatenate([[0.0], np.cumsum(net)])
    return {
        "n_ev": n_ev,
        "n_tr": len(trades),
        "ev": float(net.mean()),
        "win": float((net > 0).mean()),
        "tot": float(net.sum()),
        "dd": float((np.maximum.accumulate(cum) - cum).max()),
        "n_long": int(sum(t["long"] for t in trades)),
    }


def main() -> None:
    repo = repo_root()
    pooled = {"A": [], "B": []}
    n_events = {"A": 0, "B": 0}
    lags: list[float] = []
    print(f"{'asset':>5} | {'A: ev/tr win DD':>28} | "
          f"{'B: ev/tr win DD':>28}")
    for sym in ASSETS:
        ts, hp, lp, cp, vol = resample_4h(*read_1h(repo, sym))
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        b = ts // 14_400_000
        env = {"hp": hp, "lp": lp, "cp": cp, "atr": atr, "ts": ts,
               "vol": vol, "b": b, "g0": int(b[0]),
               "n_bars": int(b[-1]) - int(b[0]) + 1}

        # variant C: SSA on close, wick offsets preserved; t<SSA_W raw
        cp_ssa = ssa_denoise_line(cp)
        cp_ssa[:SSA_W] = cp[:SSA_W]
        hp_ssa = cp_ssa + (hp - cp)
        lp_ssa = cp_ssa - (cp - lp)

        idx_a, side_a = _events(hp, lp, cp, ts, vol)
        idx_b, side_b = _events(hp_ssa, lp_ssa, cp_ssa, ts, vol)

        tr_a, n_a = _simulate(env, idx_a, side_a)
        tr_b, n_b = _simulate(env, idx_b, side_b)
        n_events["A"] += n_a
        n_events["B"] += n_b
        pooled["A"].extend(tr_a)
        pooled["B"].extend(tr_b)

        # signal lag: SSA retest event -> nearest raw retest event
        for t in idx_b[idx_b >= WARMUP]:
            if len(idx_a):
                lags.append(float(np.min(np.abs(idx_a - t))))

        sa, sb = _stats(tr_a, n_a), _stats(tr_b, n_b)
        print(f"{sym:>5} | {sa['ev']:+.3f}/{sa['n_tr']}/"
              f"{sa['win']:.2f}/{sa['dd']:5.1f}R | "
              f"{sb['ev']:+.3f}/{sb['n_tr']}/{sb['win']:.2f}/"
              f"{sb['dd']:5.1f}R")

    res = {"A": _stats(pooled["A"], n_events["A"]),
           "B": _stats(pooled["B"], n_events["B"])}
    lag_med = float(np.median(lags)) if lags else float("nan")
    n_ls = {arm: (r["n_long"], r["n_tr"] - r["n_long"])
            for arm, r in res.items()}
    print(f"\nPOOLED A: events={n_events['A']} trades={res['A']['n_tr']} "
          f"EV={res['A']['ev']:+.4f} win={res['A']['win']:.3f} "
          f"totalR={res['A']['tot']:+.1f} maxDD={res['A']['dd']:.1f}R "
          f"L/S={n_ls['A'][0]}/{n_ls['A'][1]}")
    print(f"POOLED B: events={n_events['B']} trades={res['B']['n_tr']} "
          f"EV={res['B']['ev']:+.4f} win={res['B']['win']:.3f} "
          f"totalR={res['B']['tot']:+.1f} maxDD={res['B']['dd']:.1f}R "
          f"L/S={n_ls['B'][0]}/{n_ls['B'][1]}")
    print(f"signal lag: median {lag_med:.0f} bars "
          f"({lag_med * 4:.0f}h) over {len(lags)} SSA events")
    ok = res["B"]["ev"] >= res["A"]["ev"] and res["B"]["dd"] < res["A"]["dd"]
    print("GATE:", "PASS" if ok else
          "FAIL -> R-SSA-2 PARKED, denoising direction closed for OB")


if __name__ == "__main__":
    main()
