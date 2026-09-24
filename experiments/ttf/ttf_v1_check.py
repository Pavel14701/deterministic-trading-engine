"""TTF v1: taker-flow divergence, one-shot per the frozen prereg
(STATUS 2026-09-21, "TTF v1 -- PRE-REGISTRATION").

Signal (frozen): tbv_share = taker_buy/volume (1H); s = Z(share,
trailing 336); r = ret over trailing 24; LONG: r<0 AND s>=+2
(confirmation close>open), SHORT mirrored; entry next bar open;
exit |s|<0.5 / opposite divergence / stop 2xATR24; no TP; one
position per asset; notional 1.0; cost 0.075%/side (0.15% RT).

Evaluation (frozen): F1 2021-01-01..2023-08-31, F2
2023-09-01..2025-08-31, PRIMARY = pooled; F3 from 2025-09-01
reported, not gated.  Daily net streams per asset; Sharpe_NW
lags 1..5, ann 365; activity floor 60d.  Gates on PRIMARY:
T-G1 per-asset Sharpe_NW>=1.0 on >=3/6 assets; T-G2 portfolio
(equal-weight, flat contributes 0) Sharpe_NW>=1.0; T-G3
portfolio maxDD<=20%; T-G4 gross portfolio Sharpe>0; n<200
trades on PRIMARY -> INCONCLUSIVE.

Execution conventions declared here (prereg-silent details,
not parameters): z ddof=1; stop checked intrabar FIRST
(stop-first, repo convention; gap fills at open), close-based
exits at bar close; ATR frozen at the signal bar; daily
stream is mark-to-market on day closes; portfolio = sum of
asset streams / 6 (fixed denominator).
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import nw_sharpe, portfolio_dd, repo_root
from ta.src.volatility.atr import atr_ind


SYMS = ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE")
W_Z = 336
W_RET = 24
S_IN = 2.0
S_OUT = 0.5
ATR_MULT = 2.0
COST_SIDE = 0.00075
ANN_D = 365
ACT_FLOOR_D = 60
N_TRADE_MIN = 200
MS_D = 86_400_000


def _ms(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


F1_LO, F1_HI = _ms(2021, 1, 1), _ms(2023, 9, 1)
F2_HI = _ms(2025, 9, 1)


def _roll_z(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        win = x[i - w + 1:i + 1]
        if np.isfinite(win).all():
            sd = win.std(ddof=1)
            if sd > 0:
                out[i] = (x[i] - win.mean()) / sd
    return out


def simulate(sym: str, repo) -> dict:
    df = pl.read_parquet(repo / f"data/binance/kl_{sym}USDT_1h.parquet")
    ts = df["ts"].to_numpy().astype(np.int64)
    op = df["open"].to_numpy()
    hp = df["high"].to_numpy()
    lp = df["low"].to_numpy()
    cp = df["close"].to_numpy()
    vol = df["volume"].to_numpy()
    tbv = df["taker_buy_volume"].to_numpy()

    share = np.where(vol > 0, tbv / np.where(vol > 0, vol, 1.0), np.nan)
    s = _roll_z(share, W_Z)
    r = np.full(len(cp), np.nan)
    r[W_RET:] = cp[W_RET:] / cp[:-W_RET] - 1.0
    atr = np.asarray(atr_ind(hp, lp, cp, W_RET, use_talib=False), float)

    n = len(cp)
    trades: list[tuple[int, int, float, float, int]] = []
    i = W_Z
    while i < n - 1:
        long_sig = (np.isfinite(s[i]) and r[i] < 0 and s[i] >= S_IN
                    and cp[i] > op[i])
        short_sig = (np.isfinite(s[i]) and r[i] > 0 and s[i] <= -S_IN
                     and cp[i] < op[i])
        if not (long_sig or short_sig) or not np.isfinite(atr[i]):
            i += 1
            continue
        sign = 1 if long_sig else -1
        entry = op[i + 1]
        stop = entry - sign * ATR_MULT * atr[i]
        exit_px = None
        j = i + 1
        while j < n:
            hit = lp[j] <= stop if sign > 0 else hp[j] >= stop
            if hit:  # stop-first, gap fills at open
                exit_px = min(op[j], stop) if sign > 0 else max(op[j], stop)
            else:
                sx = s[j]
                opp = (bool(sx <= -S_IN and r[j] > 0) if sign > 0
                       else bool(sx >= S_IN and r[j] < 0))
                if np.isfinite(sx) and (abs(sx) < S_OUT or opp):
                    exit_px = cp[j]
            if exit_px is not None:
                break
            j += 1
        if exit_px is None:
            j = n - 1
            exit_px = cp[j]
        trades.append((i + 1, j, entry, exit_px, sign))
        i = j
    return {"ts": ts, "cp": cp, "trades": trades}


def daily_stream(res: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(days, gross, net) daily MTM streams on this asset's UTC days."""
    ts, cp, trades = res["ts"], res["cp"], res["trades"]
    days = np.unique(ts // MS_D)
    pos = {int(d): k for k, d in enumerate(days)}
    last: dict[int, float] = {}
    for k in range(len(ts)):
        last[int(ts[k] // MS_D)] = cp[k]
    dc = np.array([last[int(d)] for d in days])
    gross = np.zeros(len(days))
    net = np.zeros(len(days))
    active = np.zeros(len(days), bool)
    for b0, b1, entry, exit_px, sign in trades:
        k0, k1 = pos[int(ts[b0] // MS_D)], pos[int(ts[b1] // MS_D)]
        active[k0:k1 + 1] = True
        if k0 == k1:
            gross[k0] += sign * (exit_px / entry - 1.0)
        else:
            gross[k0] += sign * (dc[k0] / entry - 1.0)
            gross[k0 + 1:k1] += sign * (dc[k0 + 1:k1] / dc[k0:k1 - 1] - 1.0)
            gross[k1] += sign * (exit_px / dc[k1 - 1] - 1.0)
        net[k0] -= COST_SIDE
        net[k1] -= COST_SIDE
    return days, gross, net + gross, active


def _on(days: np.ndarray, d: np.ndarray, v: np.ndarray) -> np.ndarray:
    out = np.zeros(len(days))
    out[np.searchsorted(days, d)] = v
    return out


def main() -> None:
    repo = repo_root()
    per: dict[str, tuple] = {}
    for sym in SYMS:
        res = simulate(sym, repo)
        per[sym] = (res, *daily_stream(res))
    days = np.unique(np.concatenate([p[1] for p in per.values()]))
    lo, hi = np.searchsorted(days, [F1_LO // MS_D, F2_HI // MS_D])
    prim = slice(lo, hi)
    print(f"PRIMARY F1+F2: days={hi - lo}", flush=True)

    g_sum = np.zeros(len(days))
    n_sum = np.zeros(len(days))
    asset_pass = 0
    trades_primary = {}
    for sym in SYMS:
        res, d, g, nn, act_m = per[sym]
        g_sum += _on(days, d, g)
        n_sum += _on(days, d, nn)
        tp = sum(F1_LO <= res["ts"][t[0]] < F2_HI for t in res["trades"])
        trades_primary[sym] = tp
        k = np.searchsorted(d, F1_LO // MS_D)
        m = np.searchsorted(d, F2_HI)
        act = int(np.count_nonzero(act_m[k:m]))
        shp = nw_sharpe(nn[k:m], lags=5, ann=ANN_D)
        gate = act >= ACT_FLOOR_D and np.isfinite(shp) and shp >= 1.0
        asset_pass += gate
        print(f"  {sym:<4}: n_trades={tp:>4}  active_days={act:>5}  "
              f"net Sharpe_NW={shp:+.2f}  T-G1={'PASS' if gate else 'fail'}",
              flush=True)

    port_g = g_sum[prim] / len(SYMS)
    port_n = n_sum[prim] / len(SYMS)
    sh_g = nw_sharpe(port_g, lags=5, ann=ANN_D)
    sh_n = nw_sharpe(port_n, lags=5, ann=ANN_D)
    dd_n = portfolio_dd(port_n)
    t_g1 = asset_pass >= 3
    t_g2 = bool(np.isfinite(sh_n) and sh_n >= 1.0)
    t_g3 = bool(np.isfinite(dd_n) and dd_n <= 0.20)
    t_g4 = bool(np.isfinite(sh_g) and sh_g > 0)
    print(f"portfolio (PRIMARY): gross Sh_NW={sh_g:+.2f}  net Sh_NW="
          f"{sh_n:+.2f}  maxDD={dd_n:.1%}")
    print(f"T-G1 {asset_pass}/6 {'PASS' if t_g1 else 'fail'}  "
          f"T-G2 {'PASS' if t_g2 else 'fail'}  "
          f"T-G3 {'PASS' if t_g3 else 'fail'}  "
          f"T-G4 {'PASS' if t_g4 else 'fail'}")
    for name, a, b in (("F1", F1_LO, F1_HI), ("F2", F1_HI, F2_HI),
                       ("F3", F2_HI, (days[-1] + 1) * MS_D)):
        ka = np.searchsorted(days, a // MS_D)
        kb = np.searchsorted(days, b // MS_D)
        print(f"  fold {name}: gross={nw_sharpe(g_sum[ka:kb] / 6, lags=5, ann=ANN_D):+.2f}"
              f"  net={nw_sharpe(n_sum[ka:kb] / 6, lags=5, ann=ANN_D):+.2f}"
              f"  DD={portfolio_dd(n_sum[ka:kb] / 6):.1%}")

    if min(trades_primary.values()) < N_TRADE_MIN:
        print("TTF v1: INCONCLUSIVE (n<200 trades on PRIMARY per prereg)")
    elif t_g1 and t_g2 and t_g3 and t_g4:
        print("TTF v1: PASS -> all prereg gates met")
    else:
        print("TTF v1: CLOSED -> gate(s) failed, no re-tuning per prereg")


if __name__ == "__main__":
    main()
