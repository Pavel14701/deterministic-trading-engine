"""Runner for the z-score strategy track (STATUS 2026-09-21, frozen).

Implements exactly the pre-registered evaluation:
- event basis: engine.sim.sim pessimistic R (validated taker +
  pessimism stack -- NO extra cost subtraction), entries at next bar
  open, one open trade per asset, max hold = engine cap 48 bars;
- stream basis: hourly portfolio streams with 8bp/side turnover cost,
  Sharpe_NW (lags 5) annualised x sqrt(24*365);
- folds: PRIMARY = first 2/3 of the common calendar grid, F3 = last
  1/3, gates on PRIMARY only.

Run:  python -m experiments.zscore.runner
"""

from __future__ import annotations

import json
import time

from dataclasses import dataclass

import numpy as np
import polars as pl

from engine.sim.engine import sim
from experiments._repo import REPO
from experiments.zscore.signals import (
    hyb1_signals,
    mom1_signals,
    mr1_signals,
    xsec1_weights,
)
from ta.src.statistics.zscore import zscore_ind
from ta.src.trend.adx import adx_ind
from ta.src.volatility.atr import atr_ind


DATA = REPO / "data" / "binance"
OUT = REPO / "runs"

MAJORS = [
    "BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "LINK",
    "TON", "TRX", "DOT", "LTC", "BCH", "NEAR", "APT", "ARB", "OP",
    "SUI", "PEPE", "TIA", "INJ", "FIL", "ATOM", "ETC", "XLM", "HBAR",
    "AAVE", "WIF", "SEI",
]
COST_SIDE = 0.0008       # 8bp per side of turnover (stream basis)
NW_LAGS = 5
ANN = 24 * 365
MIN_ASSETS_XSEC = 10
REBALANCE = 168
G1_RATIO = 0.5           # frozen "5/10"
GATE_SHARPE = 1.0
GATE_DD = 0.25
RISK_PER_TRADE = 0.01    # 1% risk per event trade for the G3 equity


@dataclass(frozen=True)
class Strategy:
    name: str
    k_sl: float
    k_tp: float
    kind: str               # "event" or "xsec"


STRATEGIES = [
    Strategy("MR-1", 2.0, 2.0, "event"),
    Strategy("MOM-1", 3.0, 3.0, "event"),
    Strategy("XSEC-1", 0.0, 0.0, "xsec"),
    Strategy("HYB-1", 2.5, 2.5, "event"),
]


def load_asset(sym: str) -> dict[str, np.ndarray] | None:
    path = DATA / f"kl_{sym}USDT_1h.parquet"
    if not path.exists():
        return None
    df = pl.read_parquet(path).sort("ts")
    high = df["high"].to_numpy().astype(np.float64)
    low = df["low"].to_numpy().astype(np.float64)
    close = df["close"].to_numpy().astype(np.float64)
    z336 = np.asarray(
        zscore_ind(close, length=336, ddof=1, use_talib=False)
    )
    z168 = np.asarray(
        zscore_ind(close, length=168, ddof=1, use_talib=False)
    )
    atr24 = np.asarray(
        atr_ind(high, low, close, length=24, use_talib=False)
    )
    adx14 = np.asarray(
        adx_ind(high, low, close, length=14, use_talib=False)[0]
    )
    return {
        "ts": df["ts"].to_numpy(),
        "open": df["open"].to_numpy().astype(np.float64),
        "high": high, "low": low, "close": close,
        "z336": z336, "z168": z168, "atr24": atr24, "adx14": adx14,
    }


def positions(asset: dict[str, np.ndarray], st: Strategy) -> np.ndarray:
    if st.name == "MR-1":
        return mr1_signals(asset["z336"], 2.0, 0.0, True)
    if st.name == "MOM-1":
        return mom1_signals(asset["z168"], 1.5, 0.0)
    if st.name == "HYB-1":
        return hyb1_signals(asset["z336"], asset["adx14"], 20.0, 25.0, 2.0)
    raise ValueError(st.name)


def run_event_asset(
    asset: dict[str, np.ndarray], st: Strategy
) -> list[dict]:
    """Event trades for one asset: entries at the NEXT bar open (no
    lookahead), one open sim trade at a time (cursor at exit)."""
    pos = positions(asset, st)
    o, h, lo, c = (asset["open"], asset["high"], asset["low"],
                   asset["close"])
    atr, ts = asset["atr24"], asset["ts"]
    n = len(pos)
    trades: list[dict] = []
    cursor = 0
    for i in range(1, n):
        if pos[i] == pos[i - 1] or pos[i] == 0 or i < cursor:
            continue
        i0 = i + 1
        if i0 >= n or not np.isfinite(atr[i]):
            continue
        side = "long" if pos[i] == 1 else "short"
        fill = o[i0]
        sl = fill - st.k_sl * atr[i] if side == "long" \
            else fill + st.k_sl * atr[i]
        tp = fill + st.k_tp * atr[i] if side == "long" \
            else fill - st.k_tp * atr[i]
        r_opt, r_pess, exit_idx = sim(
            o, h, lo, c, i0, side, sl, tp, 48, atr[i]
        )
        if exit_idx < 0:
            break                    # sim ran past the end of data
        cursor = exit_idx + 1
        trades.append({"ts": int(ts[i0]),
                       "r_opt": float(r_opt),
                       "r_pess": float(r_pess)})
    return trades


def sharpe_nw(v: np.ndarray, ann: int = ANN) -> float:
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan")
    base = float(v.mean() / v.std() * np.sqrt(ann))
    rho = [float(np.corrcoef(v[:-k], v[k:])[0, 1])
           for k in range(1, NW_LAGS + 1) if v.size > k + 10]
    factor = float(np.sqrt(max(1.0, min(5.0, 1.0 + 2.0 * float(np.sum(rho))))))
    return base / factor


def event_dd(r_pess: np.ndarray) -> float:
    """G3: equity compounding 1% risk per trade, max drawdown."""
    r = r_pess[np.isfinite(r_pess)]
    if r.size == 0:
        return float("nan")
    eq = np.cumprod(1.0 + RISK_PER_TRADE * r)
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def build_matrices(
    assets: dict[str, dict], all_ts: np.ndarray, names: list[str],
    st: Strategy,
) -> tuple[np.ndarray, np.ndarray]:
    """Position/weight matrix and hourly log-return matrix on the
    union-ts grid (the frozen fold axis)."""
    grid = {t: k for k, t in enumerate(all_ts)}
    n_g, n_a = len(all_ts), len(names)
    posm = np.zeros((n_g, n_a))
    rets = np.full((n_g, n_a), np.nan)
    for j, name in enumerate(names):
        a = assets[name]
        idx = np.array([grid[t] for t in a["ts"]])
        if st.kind != "xsec":
            posm[idx, j] = positions(a, st)
        lc = np.log(a["close"])
        r = np.full(len(a["close"]), np.nan)
        r[1:] = np.diff(lc)
        rets[idx, j] = r
    if st.kind == "xsec":
        zmat = np.full((n_g, n_a), np.nan)
        for j, name in enumerate(names):
            a = assets[name]
            idx = np.array([grid[t] for t in a["ts"]])
            zmat[idx, j] = a["z336"]
        posm = xsec1_weights(zmat, 0.2, 0.2, REBALANCE, MIN_ASSETS_XSEC)
    return posm, rets


def stream_metrics(
    posm: np.ndarray, rets: np.ndarray, n_split: int,
) -> tuple[dict, dict[int, float]]:
    """Portfolio stream (G2/F3) and per-asset PRIMARY Sharpe (G1).

    Stream convention (frozen): gross_t = sum_j pos_{t-1,j} ret_{t,j}
    divided by the number of ACTIVE assets (|pos|>0 with finite ret),
    0 if none; minus 8bp x per-asset turnover.
    """
    lag = np.vstack([np.zeros((1, posm.shape[1])), posm[:-1]])
    active = (np.abs(lag) > 0) & np.isfinite(rets)
    n_act = active.sum(axis=1)
    gross = np.where(
        n_act > 0,
        np.nansum(np.where(active, lag * rets, 0.0), axis=1)
        / np.maximum(n_act, 1),
        0.0,
    )
    turn = np.nansum(np.abs(posm - lag), axis=1) * COST_SIDE
    stream = gross - turn
    per_asset: dict[int, float] = {}
    for j in range(posm.shape[1]):
        lagj = np.zeros(posm.shape[0])
        lagj[1:] = posm[:-1, j]
        sj = np.where(np.isfinite(rets[:, j]),
                      lagj * np.nan_to_num(rets[:, j]), 0.0)
        sj -= COST_SIDE * np.abs(posm[:, j] - lagj)
        per_asset[j] = sharpe_nw(sj[:n_split])
    prim, f3 = stream[:n_split], stream[n_split:]
    out = {
        "sharpe_primary": sharpe_nw(prim),
        "sharpe_f3": sharpe_nw(f3),
        "gross_mean_primary": float(np.mean(gross[:n_split])),
    }
    return out, per_asset


def main() -> None:
    t0 = time.time()
    assets: dict[str, dict] = {}
    for m in MAJORS:
        a = load_asset(m)
        if a is not None:
            assets[m] = a
    names = list(assets)
    print(f"loaded {len(assets)}/{len(MAJORS)} assets", flush=True)
    all_ts = np.unique(np.concatenate([a["ts"] for a in assets.values()]))
    n_split = int(len(all_ts) * 2 / 3)
    split_ts = int(all_ts[n_split])
    print(f"grid {len(all_ts)} bars, PRIMARY/F3 split ts={split_ts}",
          flush=True)

    report: dict = {
        "split_ts": split_ts, "n_assets": len(names),
        "strategies": {},
    }
    for st in STRATEGIES:
        posm, rets = build_matrices(assets, all_ts, names, st)
        sm, per_asset = stream_metrics(posm, rets, n_split)
        finite = {names[j]: v for j, v in per_asset.items()
                  if np.isfinite(v)}
        n_g1 = sum(1 for v in finite.values() if v >= GATE_SHARPE)
        g1 = len(finite) > 0 and n_g1 >= G1_RATIO * len(finite)
        g2 = bool(np.isfinite(sm["sharpe_primary"])
                  and sm["sharpe_primary"] >= GATE_SHARPE)

        rep: dict = {
            "kind": st.kind,
            "sharpe_primary": sm["sharpe_primary"],
            "sharpe_f3": sm["sharpe_f3"],
            "gross_mean_primary": sm["gross_mean_primary"],
            "n_g1": int(n_g1), "n_eval_g1": len(finite),
            "per_asset_sharpe_primary": finite,
        }
        if st.kind == "event":
            trades: list[dict] = []
            for name in names:
                trades.extend(run_event_asset(assets[name], st))
            trades.sort(key=lambda t: t["ts"])
            prim_tr = [t for t in trades if t["ts"] < split_ts]
            r_p = np.array([t["r_pess"] for t in prim_tr])
            r_o = np.array([t["r_opt"] for t in prim_tr])
            dd = event_dd(r_p)
            g3 = bool(np.isfinite(dd) and dd <= GATE_DD)
            g4 = bool(r_o.size and np.nanmean(r_o) > 0)
            rep.update(
                n_trades_primary=int(r_p.size),
                ev_net_r=float(np.nanmean(r_p)) if r_p.size else None,
                ev_gross_r=float(np.nanmean(r_o)) if r_o.size else None,
                win_rate=float(np.nanmean(r_p > 0)) if r_p.size else None,
                dd_event=dd,
            )
            dd_show, g4_show = dd, rep["ev_gross_r"]
        else:
            lag = np.vstack([np.zeros((1, posm.shape[1])), posm[:-1]])
            active = (np.abs(lag) > 0) & np.isfinite(rets)
            n_act = active.sum(axis=1)
            gross_only = np.where(
                n_act > 0,
                np.nansum(np.where(active, lag * rets, 0.0), axis=1)
                / np.maximum(n_act, 1), 0.0,
            )
            g_only = gross_only[:n_split]
            dd = event_dd(g_only)  # same compounding on stream R
            g3 = bool(np.isfinite(dd) and dd <= GATE_DD)
            g4 = bool(g_only.size and np.nanmean(g_only) > 0)
            rep.update(dd_stream_equity=dd,
                       gross_mean_primary=float(np.nanmean(g_only)))
            dd_show, g4_show = dd, rep["gross_mean_primary"]

        rep.update(g1=bool(g1), g2=g2, g3=g3, g4=g4,
                   verdict="PASS" if (g1 and g2 and g3 and g4)
                   else "FAIL")
        report["strategies"][st.name] = rep
        print(f"{st.name}: G1 {n_g1}/{len(finite)}  "
              f"G2 {sm['sharpe_primary']:+.2f}  "
              f"G3 dd={dd_show:.3f}  G4 {g4_show:+.5f}  "
              f"F3 {sm['sharpe_f3']:+.2f}  -> {rep['verdict']}",
              flush=True)

    OUT.mkdir(exist_ok=True)
    (OUT / "zscore_report.json").write_text(json.dumps(report, indent=2))
    print(f"done in {time.time() - t0:.0f}s -> runs/zscore_report.json",
          flush=True)


if __name__ == "__main__":
    main()


