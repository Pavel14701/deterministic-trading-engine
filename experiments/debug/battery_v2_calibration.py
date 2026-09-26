# -*- coding: utf-8 -*-
"""Battery v2 calibration (prereg PREREG_BATTERY_V2.md §8).
Three cases: avsl_cross_s1, avsl_trailing_s1, synthetic null.
One shot."""
from __future__ import annotations

import numpy as np

from engine.battery_v2 import report, evaluate_v2
from engine.passed.avsl_cross_s1 import (
    ASSETS, MSEC_4H, collect_trades, fast_line, repo_root,
    resample_4h, read_1h, s1_sizes,
)
from engine.passed.avsl_trailing_s1 import collect_all, trade_revcross
from ta.src.volatility.atr import atr_ind


def parent_collect(symbols, repo):
    ctxs, trades = {}, []
    for sym in symbols:
        d = collect_trades(sym, repo)
        _ts, _hp, _lp, cp4, _v = resample_4h(*read_1h(repo, sym))
        ctxs[sym] = {"g0": d["g0"], "n_bars": d["n_bars"],
                     "sizes": s1_sizes(cp4)}
        for tr in d["trades"]:
            trades.append({**tr, "sym": sym})
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    return ctxs, trades


def synth_collect(symbols, repo, n_bars=15269, seed=7):
    """10 iid random-walk assets, same entry rule + trailing exit."""
    ctxs, trades = {}, []
    for k, sym in enumerate(symbols):
        rng = np.random.default_rng(seed * 100 + k)
        r = rng.normal(0.0, 0.02, n_bars)
        cp = 100.0 * np.exp(np.cumsum(r))
        hp, lp = cp * (1 + 0.001), cp * (1 - 0.001)
        vol = np.ones(n_bars)
        ts = (np.arange(n_bars) + k * 17) * MSEC_4H  # staggered starts
        line = fast_line(lp, cp, vol)
        atr = np.asarray(atr_ind(hp, lp, cp, 14, use_talib=False))
        up = (cp[1:] > line[1:]) & (cp[:-1] < line[:-1])
        dn = (cp[1:] < line[1:]) & (cp[:-1] > line[:-1])
        cross_idx = np.nonzero(up | dn)[0] + 1
        b = ts // MSEC_4H
        env = {"hp": hp, "lp": lp, "cp": cp, "line": line, "atr": atr,
               "up": up, "dn": dn, "cross_idx": cross_idx,
               "b": b, "g0": int(b[0]), "n_bars": n_bars}
        ctxs[sym] = {"g0": env["g0"], "n_bars": n_bars,
                     "sizes": s1_sizes(cp)}
        for t, is_long in zip(cross_idx, up[cross_idx - 1]):
            if t < 400:
                continue
            tr = trade_revcross(env, int(t), bool(is_long))
            if tr is not None:
                tr["sym"] = sym
                trades.append(tr)
    trades.sort(key=lambda x: (x["e0"], x["sym"]))
    return ctxs, trades


def main() -> None:
    repo = repo_root()
    print("CALIBRATION CASE 1/3")
    report(evaluate_v2(parent_collect, label="avsl_cross_s1"))
    print("\nCALIBRATION CASE 2/3")
    report(evaluate_v2(lambda syms, rp: collect_all(syms, rp)[1:],
                          label="avsl_trailing_s1"))
    print("\nCALIBRATION CASE 3/3")
    report(evaluate_v2(synth_collect, label="synthetic null"))


if __name__ == "__main__":
    main()
