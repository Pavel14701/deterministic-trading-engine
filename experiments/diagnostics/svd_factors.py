# -*- coding: utf-8 -*-
"""Level-1 SVD diagnostic: how many real factors drive the 10-asset
AVSL universe (STATUS 2026-09-24, "SVD diagnostic plan").

Question: is the 10-asset pilot universe 10 independent bets or one
crypto-beta bet in 10 costumes?  Method: eigenspectrum of the 4H
log-return correlation matrix (closed 4H buckets, common timestamps
only).  Diagnostic ONLY -- reads the frozen module's loaders, changes
nothing, gates nothing.

Metrics printed:
  - full eigenvalue spectrum of corr (trace = 10);
  - n_eff(90%): smallest k explaining 90% of variance;
  - participation ratio PR = (sum lam)^2 / sum lam^2 (shannon-like
    effective count, robust to the 90% threshold choice);
  - mean off-diagonal pairwise correlation;
  - PC1 loadings (who sits on the main factor).
Run:  uv run python -m experiments.diagnostics.svd_factors
"""

from __future__ import annotations

import numpy as np

from engine.passed.avsl_cross_s1 import (
    ASSETS,
    read_1h,
    repo_root,
    resample_4h,
)


MS = 14_400_000  # 4H bucket in ms


def _closes_4h(repo) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per asset: (bucket_ts_ms, log close) for closed 4H buckets."""
    out = {}
    for sym in ASSETS:
        ts, _hp, _lp, cp, _vol = resample_4h(*read_1h(repo, sym))
        b = np.asarray(ts, dtype=np.int64) // MS
        out[sym] = (b[:-1], np.log(np.asarray(cp[:-1], dtype=float)))
    return out


def main() -> None:
    repo = repo_root()
    data = _closes_4h(repo)

    common: np.ndarray = data[ASSETS[0]][0]
    for sym in ASSETS[1:]:
        common = np.intersect1d(common, data[sym][0])
    r = []
    for sym in ASSETS:
        b, lc = data[sym]
        idx = np.searchsorted(b, common)
        r.append(np.diff(lc[idx]))
    R = np.column_stack(r)  # (n_buckets-1, 10)
    print(f"assets={len(ASSETS)} aligned closed 4H buckets="
          f"{len(common) - 1} last={common[-1]}")

    corr = np.corrcoef(R.T)
    lam = np.linalg.eigvalsh(corr)[::-1]  # descending, trace = 10
    explained = lam / lam.sum()
    cum = explained.cumsum()

    n_eff90 = int((cum < 0.90).sum()) + 1
    pr = float(lam.sum() ** 2 / (lam ** 2).sum())
    off = corr[~np.eye(len(ASSETS), dtype=bool)]
    print("eigenvalues:", np.round(lam, 3).tolist())
    print("explained%:", np.round(explained * 100, 1).tolist())
    print("cumulative%:", np.round(cum * 100, 1).tolist())
    print(f"n_eff(90%)={n_eff90}  participation_ratio={pr:.2f}")
    print(f"mean pairwise corr={off.mean():+.3f}  "
          f"mean |corr|={np.abs(off).mean():.3f}")

    evals, evecs = np.linalg.eigh(corr)
    pc1 = evecs[:, np.argmax(evals)]
    if pc1[np.abs(pc1).argmax()] < 0:
        pc1 = -pc1  # sign convention: max-magnitude loading positive
    print("PC1 loadings:", {s: round(float(v), 2)
                           for s, v in zip(ASSETS, pc1)})

    if n_eff90 <= 2:
        verdict = ("ONE-FACTOR universe (crypto-beta): cluster DD is "
                   "structural -- universe problem, not sizing")
    elif 4 <= n_eff90 <= 6:
        verdict = ("multi-factor structure present: portfolio-layer "
                   "optimization (SVD levels 2-4) is meaningful")
    else:
        verdict = f"intermediate structure (n_eff={n_eff90})"
    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
