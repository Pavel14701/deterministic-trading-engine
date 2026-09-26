# -*- coding: utf-8 -*-
"""AVSL cross at high TFs -- pre-registered single shot (STATUS
2026-09-21, gates frozen BEFORE run; see STATUS block
"AVSL CROSS HIGH-TF").

Entry: close crosses AVSL(70,345), normal arm only.  Stop =
max(|close - line|, 2*ATR14) at the entry bar (structural +
volatility floor -- the docstring now matches the code).  TP
{3,5,8}R, horizon 500 bars, MTM exit, conservative within-bar (stop
wins), entry at close of the cross bar, fee 10bp round trip,
overlapping trades allowed.  Segments: train = first 2/3 of bars,
test = last 1/3.  TFs: 1H (Binance klines) and 4H (deterministic
resample of the same 1H).  Nothing else.

Run:  uv run python -m experiments.avsl.cross_tf.avsl_cross_tf
"""

from __future__ import annotations
__version__ = "1.0.0"  # evidence-версия: вердикт получен этим кодом

__version__ = "1.0.0"

import numpy as np
import polars as pl

from experiments import REPO
from experiments.avsl.baseline.avsl_baseline import TPS, WARMUP, _fast_line
from ta.src.volatility.atr import atr_ind


ASSETS = (
    "BTC", "AVAX", "BNB", "DOGE", "ETH",
    "LINK", "LTC", "NEAR", "SOL", "XRP",
)
TAKER_FEE = 0.0005
HORIZON = 500
K_STOP = 2.0            # ATR floor on the structural stop
MSEC_4H = 14_400_000
MIN_N = 30              # below this an asset counts as not-positive
G1_NEED = 5             # of 10 assets, per segment, same TP
G2_WR = 0.30            # pooled WR at TP=3R must beat this (BE 25%)
G3_FEE = 0.10           # median fee_r cap
SEGS = ("TRAIN", "TEST")


def _read_1h(sym: str):
    df = pl.read_parquet(REPO / f"data/binance/kl_{sym}USDT_1h.parquet")
    return (
        df["ts"].to_numpy().astype(np.int64),
        df["high"].to_numpy().astype(np.float64),
        df["low"].to_numpy().astype(np.float64),
        df["close"].to_numpy().astype(np.float64),
        df["volume"].to_numpy().astype(np.float64),
    )


def _resample_4h(ts, hp, lp, cp, vol):
    bucket = ts // MSEC_4H
    df = pl.DataFrame({"b": bucket, "ts": ts, "hp": hp, "lp": lp,
                       "cp": cp, "vol": vol})
    g = df.group_by("b", maintain_order=True).agg(
        pl.first("ts"), pl.max("hp"), pl.min("lp"),
        pl.last("cp"), pl.sum("vol"),
    )
    return (
        g["ts"].to_numpy().astype(np.int64),
        g["hp"].to_numpy().astype(np.float64),
        g["lp"].to_numpy().astype(np.float64),
        g["cp"].to_numpy().astype(np.float64),
        g["vol"].to_numpy().astype(np.float64),
    )


def _sim(hp, lp, cp, t, is_long, stop, tp_r):
    """Same semantics as prior AVSL sims, horizon 500, entry at
    close of the cross bar, conservative within-bar (stop wins)."""
    risk = cp[t] - stop if is_long else stop - cp[t]
    if risk <= 0:
        return None
    entry = cp[t]
    tp = entry + tp_r * risk if is_long else entry - tp_r * risk
    n = len(cp)
    for k in range(t + 1, min(t + 1 + HORIZON, n)):
        if is_long:
            if lp[k] <= stop:
                return -1.0
            if hp[k] >= tp:
                return tp_r
        else:
            if hp[k] >= stop:
                return -1.0
            if lp[k] <= tp:
                return tp_r
    sign = 1.0 if is_long else -1.0
    return sign * (cp[min(t + HORIZON, n - 1)] - entry) / risk


def _trades(sym: str, tf: str) -> dict:
    """Per-asset trade list: {(seg, tp): [(pnl, fee_r), ...]}."""
    ts, hp, lp, cp, vol = _read_1h(sym)
    if tf == "4H":
        ts, hp, lp, cp, vol = _resample_4h(ts, hp, lp, cp, vol)
    line = _fast_line(lp, cp, vol, 2.0)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    split = int(len(cp) * 2 / 3)
    out = {(seg, tp): [] for seg in SEGS for tp in TPS}
    n_cross = 0
    for t in cross_idx:
        if t < WARMUP:
            continue
        n_cross += 1
        seg = "TRAIN" if t < split else "TEST"
        is_long = bool(up[t - 1])
        risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
        if not np.isfinite(risk) or risk <= 0:
            continue
        stop = cp[t] - risk if is_long else cp[t] + risk
        fee_r = 2 * TAKER_FEE * cp[t] / risk
        for tp_r in TPS:
            pnl = _sim(hp, lp, cp, t, is_long, stop, tp_r)
            if pnl is not None:
                out[seg, tp_r].append((pnl, fee_r))
    return {"out": out, "n_cross": n_cross, "n_bars": len(cp),
            "split": split}


def _stats(trades):
    if not trades:
        return None
    pnls = np.array([p for p, _ in trades])
    fees = np.array([f for _, f in trades])
    return {
        "n": len(pnls),
        "gross": float(pnls.mean()),
        "net": float((pnls - fees).mean()),
        "win": float(np.mean(pnls > 0)),
        "fee_med": float(np.median(fees)),
    }


def _run_tf(tf: str) -> bool:
    print(f"\n=== TF {tf} ===", flush=True)
    all_tr = {}
    for sym in ASSETS:
        d = _trades(sym, tf)
        all_tr[sym] = d["out"]
        print(f"  {sym:>5}: bars={d['n_bars']:>6} "
              f"crosses={d['n_cross']:>4} split@{d['split']}",
              flush=True)

    tf_pass = True
    for seg in SEGS:
        for tp_r in TPS:
            st = {s: _stats(all_tr[s][seg, tp_r]) for s in ASSETS}
            cells = " | ".join(
                f"{s} n={st[s]['n']:>3} g={st[s]['gross']:+.2f} "
                f"net={st[s]['net']:+.2f} w={st[s]['win']:.0%}"
                f"{'' if st[s]['n'] >= MIN_N else '(lo-n)'}"
                for s in ASSETS
            )
            pos = sum(1 for s in ASSETS
                      if st[s]["net"] > 0 and st[s]["n"] >= MIN_N)
            fees = [st[s]["fee_med"] for s in ASSETS
                    if st[s]["n"] >= 5]
            med_fee = float(np.median(fees)) if fees else float("inf")
            gate1 = pos >= G1_NEED
            tf_pass = tf_pass and gate1
            print(f"  {seg} TP={tp_r:.0f}R: pos={pos}/10 "
                  f"med_fee={med_fee:.3f}R G1="
                  f"{'PASS' if gate1 else 'FAIL'}\n    {cells}",
                  flush=True)

    # G2: pooled WR at 3R per segment (gross-edge-first gate)
    for seg in SEGS:
        tr = [x for s in ASSETS if all_tr[s][seg, 3.0]
              for x in all_tr[s][seg, 3.0]]
        if not tr:
            tf_pass = False
            print(f"  G2({seg}): FAIL (no trades)", flush=True)
            continue
        pnls = np.array([p for p, _ in tr])
        wr = float(np.mean(pnls > 0))
        ok = wr > G2_WR
        tf_pass = tf_pass and ok
        print(f"  G2({seg}): pooled n={len(pnls)} WR3R={wr:.1%} "
              f"(need >{G2_WR:.0%}) -> {'PASS' if ok else 'FAIL'}",
              flush=True)

    # G3: median fee_r per segment (all TPs, pooled)
    for seg in SEGS:
        fees = [f for tp_r in TPS for s in ASSETS
                for _, f in all_tr[s][seg, tp_r]]
        med = float(np.median(fees)) if fees else float("inf")
        ok = med <= G3_FEE
        tf_pass = tf_pass and ok
        print(f"  G3({seg}): median fee_r={med:.3f} (cap {G3_FEE}) "
              f"-> {'PASS' if ok else 'FAIL'}", flush=True)

    print(f"  VERDICT TF {tf}: {'PASS' if tf_pass else 'FAIL'}",
          flush=True)
    return tf_pass


def main() -> None:
    v1 = _run_tf("1H")
    v4 = _run_tf("4H")
    print("\n==== FAMILY VERDICT ====", flush=True)
    if v1 and v4:
        print("BOTH TFs PASS -> go to separate confirmation prereg")
    elif v1 or v4:
        print("ONE TF PASS -> WEAK, needs confirm (per prereg)")
    else:
        print("BOTH FAIL -> AVSL-cross entry family CLOSED for good")


if __name__ == "__main__":
    main()


