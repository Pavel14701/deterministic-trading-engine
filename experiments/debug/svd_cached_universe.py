# -*- coding: utf-8 -*-
"""SVD + tail correlation on the CACHED universe (OKX 34 + Binance 30).

Question: is the cached union structurally rank-one (like the
10-asset AVSL universe), or does it contain enough independent
structure to justify running AVSL on an extended set?

Metrics:
  1. PC1 share + Marchenko-Pastur barrier (normal-day factor count)
  2. Mean pairwise correlation
  3. Tail correlation (worst 5% of portfolio days) -- the metric
     that matters for DD-window overlap
  4. Per-asset distance from PC1 (candidate diversifiers)

Diagnostic ONLY.  Reads cached parquets.  No network.  No gates.
Declared conventions: 4H epoch-aligned buckets, last close per
bucket, common-bucket intersection across ALL tickers, >= 2 years
of 1H bars per ticker, dedupe by ticker with Binance preferred.

Run:  python -m experiments.debug.svd_cached_universe
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[2]
MSEC_4H = 14_400_000
MIN_1H_BARS = 8760 * 2   # ~2 years of 1h bars -- WF-compatible
TAIL_Q = 0.05


# ----------------------------------------------------------------------
# 1. Discovery
# ----------------------------------------------------------------------
def _find_close_col(df: pl.DataFrame) -> str:
    for c in ("close", "Close", "c"):
        if c in df.columns:
            return c
    raise ValueError(f"no close column in {df.columns}")


def _find_ts_col(df: pl.DataFrame) -> str:
    for c in ("ts", "timestamp", "date", "time"):
        if c in df.columns:
            return c
    raise ValueError(f"no ts column in {df.columns}")


def load_one(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (ts_ms, close) or None if unreadable/short."""
    try:
        df = pl.read_parquet(path)
    except Exception as e:
        print(f"  SKIP {path.name}: {e}")
        return None
    try:
        ts_col = _find_ts_col(df)
        cl_col = _find_close_col(df)
    except ValueError as e:
        print(f"  SKIP {path.name}: {e}")
        return None
    ts = df[ts_col].to_numpy()
    if ts.dtype.kind in "i" and ts.max() < 10**11:
        ts = ts * 1000  # seconds -> ms
    elif ts.dtype.kind == "M":
        ts = ts.astype("datetime64[ms]").astype(np.int64)
    ts = ts.astype(np.int64)
    close = df[cl_col].to_numpy().astype(np.float64)
    mask = np.isfinite(close) & (close > 0)
    ts, close = ts[mask], close[mask]
    if len(ts) < MIN_1H_BARS:
        return None
    return ts, close


def discover() -> dict[str, tuple[np.ndarray, np.ndarray, str]]:
    """Scan both caches, dedupe by TICKER (e.g. BTC), prefer Binance."""
    found: dict[str, tuple[np.ndarray, np.ndarray, str]] = {}
    n_short = 0

    okx_dir = REPO / "data/okx21"
    if okx_dir.exists():
        for p in okx_dir.glob("raw_*_USDT_1H.parquet"):
            ticker = p.stem[len("raw_"):-len("_1H")].replace("-USDT", "")
            r = load_one(p)
            if r is not None:
                found[ticker] = (*r, "okx")
            else:
                n_short += 1

    binance_dir = REPO / "data/binance"
    if binance_dir.exists():
        for p in binance_dir.glob("kl_*USDT_1h.parquet"):
            ticker = p.stem[len("kl_"):-len("_1h")].replace("USDT", "")
            r = load_one(p)
            if r is not None:
                found[ticker] = (*r, "binance")  # overrides OKX
            elif ticker not in found:
                n_short += 1

    print(f"  dropped (history < {MIN_1H_BARS} 1h bars): {n_short}")
    return found


# ----------------------------------------------------------------------
# 2. Align to 4H, common buckets
# ----------------------------------------------------------------------
def to_4h_close(ts_ms: np.ndarray, close: np.ndarray):
    """Bucket to 4H (epoch-aligned), return (bucket, last_close)."""
    b = ts_ms // MSEC_4H
    df = pl.DataFrame({"b": b, "c": close})
    g = df.group_by("b", maintain_order=True).agg(pl.last("c"))
    return (g["b"].to_numpy().astype(np.int64),
            g["c"].to_numpy().astype(np.float64))


def build_matrix(found: dict):
    """Return (buckets, R, tickers, sources); R = aligned log returns."""
    per: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    src: dict[str, str] = {}
    for t, (ts, c, s) in found.items():
        b, lc = to_4h_close(ts, c)
        per[t] = (b, lc)
        src[t] = s

    common = None
    for t, (b, _) in per.items():
        common = b if common is None else np.intersect1d(common, b)
    common = np.sort(common)
    n = len(common)
    print(f"  common 4H buckets: {n} ({n * MSEC_4H / 3.156e10:.2f} years)")

    tickers = sorted(per.keys())
    cols: list[np.ndarray] = []
    kept: list[str] = []
    for t in tickers:
        b, lc = per[t]
        mask = np.isin(b, common)
        if not np.array_equal(b[mask], common):
            print(f"  SKIP {t}: bucket gaps inside common grid")
            continue
        cols.append(lc[mask])
        kept.append(t)

    R = np.column_stack([np.diff(np.log(col)) for col in cols])
    ok = np.isfinite(R).all(axis=1)
    print(f"  assets kept: {len(kept)}; rows kept after finite-filter: "
          f"{int(ok.sum())} / {n - 1}")
    return common[1:][ok], R[ok], kept, [src[t] for t in kept]


# ----------------------------------------------------------------------
# 3. Metrics
# ----------------------------------------------------------------------
def pc1_and_mp(R: np.ndarray) -> dict:
    corr = np.corrcoef(R.T)
    lam = np.linalg.eigvalsh(corr)[::-1]
    n, p = R.shape
    q = n / p
    mp = (1 + 1 / np.sqrt(q)) ** 2
    off = corr[~np.eye(p, dtype=bool)]
    return {
        "pc1_share": float(lam[0] / lam.sum()),
        "mp_barrier": float(mp),
        "eigs_above_mp": int((lam > mp).sum()),
        "mean_pairwise_corr": float(off.mean()),
        "eigvals": lam,
    }


def tail_correlation(R: np.ndarray, q: float = TAIL_Q) -> dict:
    port = R.mean(axis=1)
    thr = np.percentile(port, q * 100)
    worst = R[port <= thr]
    if worst.shape[0] < 10:
        return {"tail_mean_corr": float("nan"),
                "n_worst": worst.shape[0]}
    corr = np.corrcoef(worst.T)
    off = corr[~np.eye(R.shape[1], dtype=bool)]
    return {
        "tail_mean_corr": float(np.nanmean(off)),
        "n_worst": worst.shape[0],
    }


def pc1_distance(R: np.ndarray,
                 tickers: list[str]) -> list[tuple[str, float]]:
    """|corr(asset, PC1 score)| -- 1.0 pure beta, 0.0 decoupled."""
    corr = np.corrcoef(R.T)
    _lam, vecs = np.linalg.eigh(corr)
    pc1 = vecs[:, -1]
    if pc1[np.abs(pc1).argmax()] < 0:
        pc1 = -pc1
    score = R @ pc1
    out = []
    for j, t in enumerate(tickers):
        c = np.corrcoef(R[:, j], score)[0, 1]
        out.append((t, abs(float(c))))
    out.sort(key=lambda kv: kv[1])
    return out


# ----------------------------------------------------------------------
# 4. Verdict
# ----------------------------------------------------------------------
def verdict(pc1: float, tail: float) -> str:
    if pc1 < 0.50 and tail < 0.60:
        return "REAL DIVERSIFICATION -> run AVSL on extended universe"
    if pc1 < 0.60 and tail < 0.75:
        return "PARTIAL -> AVSL on PC1-decoupled subset + puts in parallel"
    return "RANK-ONE CONFIRMED -> puts / vol carry / FX"


def main() -> None:
    print("=== cached universe SVD diagnostic ===")
    found = discover()
    print(f"discovered: {len(found)} unique tickers (post-dedupe)")
    by_src: dict[str, int] = {}
    for _, _, s in found.values():
        by_src[s] = by_src.get(s, 0) + 1
    for s, n in sorted(by_src.items()):
        print(f"  source {s}: {n}")

    if len(found) < 15:
        print("too few tickers -- abort")
        return

    print("\nbuilding aligned 4H matrix ...")
    _buckets, R, tickers, _sources = build_matrix(found)
    print(f"  R shape: {R.shape}")

    m = pc1_and_mp(R)
    t = tail_correlation(R)
    dist = pc1_distance(R, tickers)

    print("\n=== metrics ===")
    print(f"PC1 share:          {m['pc1_share']:.1%}")
    print(f"MP lambda+ barrier: {m['mp_barrier']:.3f}")
    print(f"Eigenvalues > MP:   {m['eigs_above_mp']}")
    print(f"Mean pairwise corr: {m['mean_pairwise_corr']:+.3f}")
    print(f"Tail mean corr (worst {int(TAIL_Q * 100)}%): "
          f"{t['tail_mean_corr']:+.3f}  (n_worst={t['n_worst']})")

    print("\n=== top-15 most PC1-decoupled tickers ===")
    print("(candidates for a diversifying sub-universe)")
    for tk, c in dist[:15]:
        print(f"  {tk:<10} |corr(., PC1)| = {c:.3f}")

    print("\n=== bottom-5 (pure beta, skip if subsetting) ===")
    for tk, c in dist[-5:]:
        print(f"  {tk:<10} |corr(., PC1)| = {c:.3f}")

    print(f"\nVERDICT: {verdict(m['pc1_share'], t['tail_mean_corr'])}")


if __name__ == "__main__":
    main()
