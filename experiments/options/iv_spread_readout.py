# -*- coding: utf-8 -*-
"""D1-readout: BTC/ETH IV spread (DVOL diff) -- one-shot.
Distribution, z60 mean-reversion, forward reversion at |z|>2.
Output: runs/iv_spread_readout.log
"""
from __future__ import annotations
__version__ = "1.0.0"
import json
import numpy as np
from engine.passed.avsl_cross_s1 import repo_root


def load(sym):
    d = json.loads((repo_root() / f"data/deribit/dvol_{sym}_1D.json")
                   .read_text())
    return {int(r[0]): float(r[4]) for r in d}


def main():
    b, e = load("BTC"), load("ETH")
    days = sorted(set(b) & set(e))
    sp = np.array([b[d] - e[d] for d in days])
    z = np.full(len(sp), np.nan)
    for i in range(60, len(sp)):
        w = sp[i - 60:i]
        if w.std() > 0:
            z[i] = (sp[i] - w.mean()) / w.std()
    log = [f"iv_spread_readout v{__version__} -- one-shot",
           f"days {len(days)}, spread med {np.median(sp):+.1f}pt "
           f"IQR [{np.quantile(sp, .25):+.1f}, {np.quantile(sp, .75):+.1f}]",
           f"corr(sp[i], sp[i-1]) = "
           f"{np.corrcoef(sp[1:], sp[:-1])[0, 1]:+.3f}"]
    ok = np.isfinite(z)
    log.append(f"z60: |z|>2 days {np.mean(np.abs(z[ok]) > 2):.1%}")
    # forward reversion: at |z|>2, spread change over next 5d
    chg, z0 = [], []
    for i in range(len(sp) - 5):
        if np.isfinite(z[i]) and abs(z[i]) > 2:
            chg.append(sp[i + 5] - sp[i])
            z0.append(z[i])
    chg, z0 = np.array(chg), np.array(z0)
    if len(chg) >= 10:
        hi = z0 > 2
        lo = z0 < -2
        log.append(f"|z|>2 events n={len(chg)}: "
                   f"z>2 -> d5d {np.median(chg[hi]):+.1f}pt (n={hi.sum()}), "
                   f"z<-2 -> d5d {np.median(chg[lo]):+.1f}pt (n={lo.sum()})")
        log.append("reversion = изменения против знака z")
    else:
        log.append(f"|z|>2 events: INSUFFICIENT (n={len(chg)})")
    out = repo_root() / "runs/iv_spread_readout.log"
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
