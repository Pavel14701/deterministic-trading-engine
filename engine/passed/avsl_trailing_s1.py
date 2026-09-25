# -*- coding: utf-8 -*-
"""AVSL-cross 4H + reverse-cross exit, S1 sizing -- SECOND passed
strategy (promotion of F-TP1, prereg frozen in STATUS 2026-09-25
BEFORE this module's first run).

Self-contained on purpose: it imports ONLY from the parent passed
module (engine.passed.avsl_cross_s1) and ta/ -- never from
``experiments/`` (the evidence trail).  The archived research
driver is experiments/avsl/tp1_revcross.py.

PROVENANCE (STATUS.md is the single evidence trail):
  parent module   engine/passed/avsl_cross_s1.py (stays FROZEN;
                  its TP=5R exit is retired, not deleted)
  F-TP1 prereg    commit 032726e  (2026-09-25, frozen)
  F-TP1 verdict   commit 902400d  -- one-shot PASS, all gates
  due-diligence   commit 8e2654b  -- CHK-1 true grid, CHK-2
                  trailing portfolio null, CHK-3 distribution
  post-mortem     commit 1285c56  -- NW factor artifact + tail
                  concentration findings

FROZEN CONFIG (changing ANY parameter requires a NEW prereg and
closes this module):
  entry      close crosses AVSL(70, 345) (stand_div 2.0), normal
             arm, WARMUP 400 -- identical to the parent module
  stop       max(|close - line|, 2 * ATR14) at the entry bar
  exit       FIRST OPPOSITE-cross bar, taken at its close
             (reverse-cross semantics), capped at HORIZON 500;
             stop is checked intrabar and wins within the bar;
             if NO opposite cross exists after entry, the trade
             is marked-to-market at the FINAL data bar (exact
             evidence-trail walker semantics); TP: NONE
  fees       taker 10 bp round trip, expressed in R units
  sizing S1  size = clip(0.20 / rv100, 0.25, 2.0) (parent formula)
  universe   BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP
             (Binance 1H -> deterministic 4H resample)
  segments   PRIMARY = first 2/3, F3 = rest of the common calendar
  grid       TRUE global grid: absolute 4H bucket minus the
             earliest asset bucket (declared convention; legacy
             index placement is NOT used -- R-OB-1 lesson)

FROZEN RESULT (runs/tp1_checks.log, must reproduce via --verify):
  n=2941 trades; PRIMARY Sharpe_NW +1.22, DD 22%, EV +0.49R,
  pos 9/10; F3 Sharpe_NW +1.35, DD 20%, EV +0.38R, pos 10/10.

FROZEN THESIS (honest wording, post-mortem 1285c56):
  "loss-cutting exit (avg loss -0.45R vs -1.02R baseline,
  per-trade t~3, distributed over all trades) + episodic trend
  capture (top-20 trades ~99% of PRIMARY PnL, ex-monster EV ~0).
  NOT a smooth-Sharpe product: expect long flat/negative
  stretches between monsters.  NW Sharpe sits at its resolution
  ceiling for this persistence class (eff_n 36/34)."

REQUIRED DISCLOSURES (printed on every run; read-outs, not gates):
  plain_ann Sharpe + NW eff_n, ex-top-20 EV per segment, per-year
  EV and per-year ex-top-20 table.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    HORIZON,
    K_STOP,
    MSEC_4H,
    TAKER_FEE,
    WARMUP,
    block_bootstrap_ci,
    fast_line,
    nw_sharpe,
    portfolio_dd,
    read_1h,
    repo_root,
    resample_4h,
    s1_sizes,
)
from ta.src.volatility.atr import atr_ind

SPLIT_FRAC = 2 / 3
MSEC_4H = MSEC_4H  # re-exported alias for clarity

# frozen expected values (printed precision of runs/tp1_checks.log)
FROZEN = {
    "n_trades": 2941,
    "PRIMARY": {"sharpe_nw": 1.22, "dd": 0.22, "net_ev": 0.49,
                "pos_assets": 9},
    "F3": {"sharpe_nw": 1.35, "dd": 0.20, "net_ev": 0.38,
           "pos_assets": 10},
}
TOL = 0.005


def build_env(sym: str, repo) -> dict:
    """Per-asset 4H environment (identical to the parent signal
    path; mirrors experiments/avsl/ablation_entry._env semantics)."""
    ts, hp, lp, cp, vol = read_1h(repo, sym)
    ts, hp, lp, cp, vol = resample_4h(ts, hp, lp, cp, vol)
    line = fast_line(lp, cp, vol)
    atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
    up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
    dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
    cross_idx = np.nonzero(up | dn)[0] + 1
    b = ts // MSEC_4H
    return {"hp": hp, "lp": lp, "cp": cp, "line": line, "atr": atr,
            "up": up, "dn": dn, "cross_idx": cross_idx,
            "b": b, "g0": int(b[0]),
            "n_bars": int(b[-1]) - int(b[0]) + 1}


def trade_revcross(env: dict, t: int, is_long: bool) -> dict | None:
    """One reverse-cross trade entered at bar t.

    Exit rules (frozen): first OPPOSITE-cross bar, taken at its
    close; the hard stop is checked intrabar first and wins within
    the bar; if neither occurs, mark-to-market at bar t + HORIZON.
    Returns {net, e0 (bucket idx rel. to the ASSET grid), e1
    (asset bar idx), long} or None if the entry risk is invalid.
    """
    hp, lp, cp = env["hp"], env["lp"], env["cp"]
    line, atr = env["line"], env["atr"]
    risk = max(abs(cp[t] - line[t]), K_STOP * atr[t])
    if not np.isfinite(risk) or risk <= 0:
        return None
    stop = cp[t] - risk if is_long else cp[t] + risk
    fee_r = 2 * TAKER_FEE * cp[t] / risk
    entry = cp[t]
    n = len(cp)
    dirs = env["up"][env["cross_idx"] - 1]
    want_up = not is_long
    bars = env["cross_idx"][dirs == want_up]
    nxt = bars[bars > t]
    k_exit = int(min(nxt[0], t + HORIZON)) if nxt.size else -1
    if k_exit < 0:
        k_exit = n - 1
    pnl = 0.0
    hit = False
    e1 = k_exit
    for k in range(t + 1, min(k_exit + 1, n)):
        if is_long:
            if lp[k] <= stop:
                pnl, hit, e1 = -1.0, True, k
                break
        else:
            if hp[k] >= stop:
                pnl, hit, e1 = -1.0, True, k
                break
    if not hit:
        sign = 1.0 if is_long else -1.0
        pnl = sign * (cp[k_exit] - entry) / risk
    return {"net": pnl - fee_r, "e0": int(env["b"][t]) - env["g0"],
            "e1": e1, "long": is_long}


def collect_all(symbols: tuple = ASSETS, repo=None) -> tuple:
    """Envs + true-grid contexts + all reverse-cross trades."""
    repo = repo or repo_root()
    envs = {s: build_env(s, repo) for s in symbols}
    ctxs, trades = {}, []
    for sym in symbols:
        env = envs[sym]
        _ts, _hp, _lp, cp4, _v = resample_4h(*read_1h(repo, sym))
        ctxs[sym] = {"g0": env["g0"], "n_bars": env["n_bars"],
                     "sizes": s1_sizes(cp4)}
        entry_idx = env["cross_idx"]
        is_longs = env["up"][entry_idx - 1]
        for t, is_long in zip(entry_idx, is_longs):
            if t < WARMUP:
                continue
            tr = trade_revcross(env, int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = sym
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    return envs, ctxs, trades


def evaluate(symbols: tuple = ASSETS, repo=None) -> dict:
    """True-grid battery + required disclosures.  Same accrual
    formula and gates as the parent module; placement uses the
    TRUE global grid (absolute bucket minus the earliest)."""
    envs, ctxs, trades = collect_all(symbols, repo)
    g0g = min(c["g0"] for c in ctxs.values())
    n_g = max(c["g0"] + c["n_bars"] for c in ctxs.values()) - g0g
    split = int(n_g * SPLIT_FRAC)
    s = np.zeros(n_g + 1)
    for tr in trades:
        c = ctxs[tr["sym"]]
        e0 = tr["e0"] + c["g0"] - g0g
        e1 = tr["e1"] + c["g0"] - g0g
        hold = max(e1 - e0, 1)
        w = c["sizes"][tr["e0"]] * tr["net"] / (hold + 1)
        s[e0:e1 + 1] += w
    stream = s[:n_g]
    out: dict = {"n_g": n_g, "split": split, "n_trades": len(trades)}
    for seg, lo, hi in (("PRIMARY", 0, split), ("F3", split, n_g)):
        seg_tr = [t for t in trades
                  if lo <= t["e0"] + ctxs[t["sym"]]["g0"] - g0g < hi]
        r = np.array([t["net"] for t in seg_tr])
        pos = 0
        for sym in symbols:
            v = [t["net"] for t in seg_tr if t["sym"] == sym]
            if v and float(np.mean(v)) > 0:
                pos += 1
        v = stream[lo:hi]
        lsum = _lag_sum(v, 500)
        factor = float(np.sqrt(max(1e-6, 1.0 + 2.0 * lsum)))
        r_desc = np.sort(r)[::-1]
        top20 = r_desc[:20]
        ex20 = r_desc[20:]
        out[seg] = {
            "n": len(seg_tr),
            "sharpe_nw": nw_sharpe(v),
            "plain_ann": float(v.mean() / v.std() * np.sqrt(6 * 365))
            if v.std() > 0 else float("nan"),
            "dd": portfolio_dd(v),
            "net_ev": float(r.mean()),
            "pos_assets": pos,
            "boot_ci": block_bootstrap_ci(v),
            "eff_n": int(v.size / factor ** 2),
            "ex_top20_ev": float(ex20.mean()) if ex20.size
            else float("nan"),
            "top20_share": float(top20.sum() / r.sum())
            if r.sum() != 0 else float("nan"),
        }
    out["gates_pass"] = all(
        out[seg]["sharpe_nw"] >= 1.0 and out[seg]["dd"] <= 0.25
        and out[seg]["net_ev"] >= 0.10 and out[seg]["pos_assets"] >= 7
        and out[seg]["boot_ci"][0] > 0
        for seg in ("PRIMARY", "F3"))
    out["per_year"] = _per_year(ctxs, trades, g0g)
    out["stream"] = stream
    return out


def _lag_sum(v: np.ndarray, kmax: int) -> float:
    s = 0.0
    for k in range(1, min(kmax, v.size - 10) + 1):
        c = np.corrcoef(v[:-k], v[k:])[0, 1]
        if np.isfinite(c):
            s += c
    return s


def _per_year(ctxs: dict, trades: list, g0g: int) -> dict:
    allr = np.array([t["net"] for t in trades])
    top = set(np.argsort(allr)[::-1][:20].tolist())
    out = {}
    for i, tr in enumerate(trades):
        y = dt.datetime.utcfromtimestamp(
            (g0g + tr["e0"]) * MSEC_4H / 1000).year
        d = out.setdefault(y, {"all": [], "ex": []})
        d["all"].append(tr["net"])
        if i not in top:
            d["ex"].append(tr["net"])
    return {y: {"ev": float(np.mean(v["all"])),
                "ev_ex_top20": float(np.mean(v["ex"])),
                "n_top20": len(v["all"]) - len(v["ex"]),
                "n": len(v["all"])}
            for y, v in sorted(out.items())}


def verify() -> bool:
    """P1 gate: reproduce the frozen result at printed precision."""
    r = evaluate()
    ok = r["n_trades"] == FROZEN["n_trades"]
    for seg in ("PRIMARY", "F3"):
        for k, tol_k in (("sharpe_nw", TOL), ("dd", TOL),
                         ("net_ev", TOL)):
            ok &= abs(r[seg][k] - FROZEN[seg][k]) <= tol_k
        ok &= r[seg]["pos_assets"] == FROZEN[seg]["pos_assets"]
    return bool(ok), r


def main(verify_only: bool = False) -> None:
    ok, r = verify()
    print(f"true grid n={r['n_g']}, split {r['split']}, "
          f"trades {r['n_trades']}")
    for seg in ("PRIMARY", "F3"):
        m = r[seg]
        ci = m["boot_ci"]
        print(f"{seg:>7}: Sharpe_NW={m['sharpe_nw']:+.2f} "
              f"plain_ann={m['plain_ann']:+.2f} eff_n={m['eff_n']} "
              f"DD={m['dd']:.0%} EV={m['net_ev']:+.2f}R "
              f"ex_top20_EV={m['ex_top20_ev']:+.3f}R "
              f"(top20 share {m['top20_share']:.0%}) "
              f"pos={m['pos_assets']}/10 "
              f"CI=[{ci[0]:+.5f},{ci[1]:+.5f}] n={m['n']}")
    print("per-year (EV / EV ex-top20 / n_top20):",
          {y: (round(v["ev"], 3), round(v["ev_ex_top20"], 3),
               v["n_top20"]) for y, v in r["per_year"].items()})
    print(f"battery gates: {'PASS' if r['gates_pass'] else 'FAIL'}")
    print(f"P1 --verify vs frozen: {'PASS' if ok else 'DEVIATION'}")
    print(f"PROMOTION VERDICT: "
          f"{'PASS' if ok and r['gates_pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
