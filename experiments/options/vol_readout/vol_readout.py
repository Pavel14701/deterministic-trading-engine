# -*- coding: utf-8 -*-
"""Phase-0 vol read-out (frozen one-shot): VRP + skew stability +
prints-vs-proxy share.  No gates, no strategies.

Deliverables (runs/vol_readout.log):
  1. data inventory (files ok/corrupt, time spans)
  2. daily VRP = DVOL - RV30: by year, by DVOL percentile bucket
  3. per-print VRP (iv - rv30 at print): by year x TTM bucket x
     DVOL pct bucket, puts and calls separately
  4. skew stability: iv - dvol by moneyness bucket x year (median,
     n), puts and calls
  5. prints-vs-proxy share for the frozen strangle roll legs

Greeks engine: experiments/options/_pricing.py, unit-tested in
engine/tests/core/test_bs_greeks.py.
"""

from __future__ import annotations

__version__ = "1.0.0"

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from engine.passed.avsl_cross_s1 import repo_root
from experiments.options._pricing import load_prints

MSEC_DAY = 86_400_000
TTM_BUCKETS = ((0, 45), (45, 90), (90, 10_000))
DVOL_PCT_EDGES = (0.25, 0.50, 0.75)


def year(ts: float) -> int:
    return dt.datetime.utcfromtimestamp(ts / 1000).year  # noqa: WHISPERS-OF-2029


def main() -> None:
    repo = repo_root()
    out = repo / "runs/vol_readout.log"
    L: list[str] = [f"vol_readout v{__version__} -- phase-0 one-shot"]

    # ---- context: binance daily closes + dvol -------------------------
    _df = pl.read_parquet(repo / "data/binance/kl_BTCUSDT_1h.parquet")
    ts1 = _df["ts"].to_numpy().astype(np.int64)
    cp1 = _df["close"].to_numpy().astype(np.float64)
    b = ts1 // MSEC_DAY
    g = pl.DataFrame({"b": b, "cp": cp1}).group_by(
        "b", maintain_order=True).agg(pl.last("cp"))
    day_b = g["b"].to_numpy().astype(np.int64)
    day_cp = g["cp"].to_numpy().astype(np.float64)
    lr30 = np.full(len(day_cp), np.nan)
    for i in range(30, len(day_cp)):
        lr30[i] = float(np.std(np.diff(np.log(day_cp[i - 30:i + 1])))
                        * math.sqrt(365) * 100)

    def rv30(ts: float) -> float:
        j = int(np.searchsorted(day_b, ts // MSEC_DAY, side="right")) - 1
        return float(lr30[j]) if j >= 0 else float("nan")

    dvol = json.loads((repo / "data/deribit/dvol_BTC_1D.json").read_text())
    dv_ts = np.array([d[0] for d in dvol], dtype=np.int64)
    dv_v = np.array([d[4] for d in dvol], dtype=np.float64)

    def dvol_at(ts: float) -> float:
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        return float(dv_v[max(j, 0)])

    dv_pct_rank = {}
    order = np.argsort(dv_v)
    ranks = np.empty(len(dv_v))
    ranks[order] = np.arange(len(dv_v)) / len(dv_v)
    for i, t in enumerate(dv_ts):
        dv_pct_rank[int(t)] = float(ranks[i])

    def pct_bucket(ts: float) -> str:
        j = int(np.searchsorted(dv_ts, ts, side="right")) - 1
        r = ranks[max(j, 0)]
        if r < DVOL_PCT_EDGES[0]:
            return "q1_lo"
        if r < DVOL_PCT_EDGES[1]:
            return "q2"
        if r < DVOL_PCT_EDGES[2]:
            return "q3"
        return "q4_hi"

    def spot(ts: float) -> float:
        j = int(np.searchsorted(ts1, ts, side="right")) - 1
        return float(cp1[max(j, 0)])

    # ---- 1. inventory --------------------------------------------------
    L.append("")
    L.append("=== 1. DATA INVENTORY ===")
    folders = {
        "strangle_trades": "strangle",
        "puts_trades": "puts70-92",
        "puts_trades2": "puts90-98",
    }
    prints: dict[str, list[dict]] = {}
    for fold, label in folders.items():
        tr, ok, bad = load_prints(repo / "data/deribit" / fold)
        prints[fold] = tr
        n_iv = sum(1 for x in tr if x.get("iv"))
        if tr:
            span = (f"{dt.datetime.utcfromtimestamp(tr[0]['timestamp']/1000):%Y-%m-%d}"
                    f" -> {dt.datetime.utcfromtimestamp(tr[-1]['timestamp']/1000):%Y-%m-%d}")
        else:
            span = "-"
        L.append(f"  {fold} ({label}): files ok={ok} corrupt={bad}, "
                 f"trades={len(tr)} with_iv={n_iv}, span {span}")
    L.append(f"  dvol_BTC_1D: n={len(dv_ts)}, "
             f"{dt.datetime.utcfromtimestamp(dv_ts[0]/1000):%Y-%m-%d} -> "
             f"{dt.datetime.utcfromtimestamp(dv_ts[-1]/1000):%Y-%m-%d}")

    # ---- 2. daily VRP ---------------------------------------------------
    L.append("")
    L.append("=== 2. DAILY VRP = DVOL(close) - RV30 (vol points) ===")
    vrp = []
    for i in range(len(dv_ts)):
        rv = rv30(int(dv_ts[i]))
        if np.isfinite(rv):
            vrp.append((int(dv_ts[i]), float(dv_v[i]) - rv, float(dv_v[i])))
    hdr = "  year    n   mean   med  share>0"
    L.append(hdr)
    by_year: dict[int, list[float]] = {}
    for _t, v, _d in vrp:
        by_year.setdefault(year(_t), []).append(v)
    for y in sorted(by_year):
        a = np.array(by_year[y])
        L.append(f"  {y} {len(a):5d} {a.mean():+6.2f} "
                 f"{np.median(a):+6.2f} {np.mean(a > 0):7.0%}")
    a_all = np.array([v for _t, v, _d in vrp])
    L.append(f"  ALL {len(a_all):5d} {a_all.mean():+6.2f} "
             f"{np.median(a_all):+6.2f} {np.mean(a_all > 0):7.0%}")
    L.append("  by DVOL percentile bucket (regime):")
    for qb in ("q1_lo", "q2", "q3", "q4_hi"):
        a = np.array([v for _t, v, _d in vrp if pct_bucket(_t) == qb])
        L.append(f"    {qb:6s} n={len(a):5d} mean {a.mean():+6.2f} "
                 f"med {np.median(a):+6.2f} share>0 {np.mean(a > 0):5.0%}")

    # ---- 3. per-print VRP ----------------------------------------------
    L.append("")
    L.append("=== 3. PER-PRINT VRP = iv(print) - rv30(ts), vol points ===")
    for fold in folders:
        L.append(f"  [{fold}]")
        rows = []
        inst_exp: dict[str, int] = {}
        for x in prints[fold]:
            iv = x.get("iv")
            if not iv:
                continue
            rv = rv30(x["timestamp"])
            if not np.isfinite(rv):
                continue
            name = x["instrument_name"]
            if name not in inst_exp:
                inst_exp[name] = x.get("expiry") or 0
            rows.append((x["timestamp"], float(iv) - rv,
                         x["instrument_name"], x["timestamp"]))
        # expiry from instrument name BTC-DDMMMYY-...; use trades files' meta
        L.append("    by year:")
        yr: dict[int, list[float]] = {}
        for _ts, v, _n, _t2 in rows:
            yr.setdefault(year(_ts), []).append(v)
        for y in sorted(yr):
            a = np.array(yr[y])
            L.append(f"      {y} n={len(a):6d} mean {a.mean():+6.2f} "
                     f"med {np.median(a):+6.2f} share>0 {np.mean(a > 0):5.0%}")
        L.append("    by TTM bucket (need expiry; from name suffix):")
        ttm_rows: dict[str, list[float]] = {"<45d": [], "45-90d": [],
                                            ">90d": []}
        for _ts, v, name, t2 in rows:
            exp = expiry_of(name)
            if exp is None:
                continue
            ttm = (exp - t2) / MSEC_DAY
            key = ("<45d" if ttm < 45 else "45-90d" if ttm < 90 else ">90d")
            ttm_rows[key].append(v)
        for k in ("<45d", "45-90d", ">90d"):
            a = np.array(ttm_rows[k])
            if len(a):
                L.append(f"      {k:7s} n={len(a):6d} mean {a.mean():+6.2f} "
                         f"med {np.median(a):+6.2f}")
        L.append("    by DVOL percentile bucket:")
        pb: dict[str, list[float]] = {q: [] for q in
                                      ("q1_lo", "q2", "q3", "q4_hi")}
        for _ts, v, _n, t2 in rows:
            pb[pct_bucket(t2)].append(v)
        for q in ("q1_lo", "q2", "q3", "q4_hi"):
            a = np.array(pb[q])
            if len(a):
                L.append(f"      {q:6s} n={len(a):6d} mean {a.mean():+6.2f} "
                         f"med {np.median(a):+6.2f} share>0 {np.mean(a > 0):5.0%}")

    # ---- 4. skew stability ----------------------------------------------
    L.append("")
    L.append("=== 4. SKEW STABILITY: iv - dvol by moneyness x year ===")
    for fold, otype, mlo, mhi in (("puts_trades", "put", 0.60, 1.00),
                                  ("puts_trades2", "put", 0.60, 1.00),
                                  ("strangle_trades", "both", 0.60, 1.45)):
        bk: dict[tuple, list[float]] = {}
        for x in prints[fold]:
            iv = x.get("iv")
            if not iv:
                continue
            m = strike_of(x["instrument_name"]) / spot(x["timestamp"])
            if not (mlo <= m <= mhi):
                continue
            is_call = x["instrument_name"].endswith("-C")
            bkt = (int(m / 0.05) * 5, "C" if is_call else "P",
                   year(x["timestamp"]))
            bk.setdefault(bkt, []).append(float(iv) - dvol_at(x["timestamp"]))
        L.append(f"  [{fold}] median(iv-dvol), rows=bucket%, cols=year, n>=10")
        buckets = sorted({k[0] for k in bk})
        years = sorted({k[2] for k in bk})
        hdr = "        " + "".join(f"{y:>9d}" for y in years)
        L.append(hdr)
        for bkt in buckets:
            cells = []
            for y in years:
                a = bk.get((bkt, "P", y)) or bk.get((bkt, "C", y)) \
                    or bk.get((bkt, "P", y), [])
                if not a:
                    a = []
                cells.append(f"{np.median(a):+8.1f}({len(a):4d})"
                             if len(a) >= 10 else "      -    ")
            L.append(f"    [{bkt:3d},{bkt + 3})" + "".join(cells))

    # ---- 5. prints-vs-proxy on frozen strangle legs ---------------------
    L.append("")
    L.append("=== 5. PRINTS-VS-PROXY: frozen strangle roll legs ===")
    rolls = json.loads((repo / "data/deribit/strangle_rolls.json").read_text())
    subset = json.loads((repo / "data/deribit/strangle_subset.json").read_text())
    real = proxy = 0
    for roll in rolls:
        t_r, nxt, s0 = roll["roll_ts"], roll["next_exp"], roll["spot"]
        for otype, tgt in (("put", 0.90), ("call", 1.10)):
            ks = sorted({int(m["strike"]) for m in subset.values()
                         if m["option_type"] == otype
                         and m["expiration_timestamp"] == nxt})
            if not ks:
                continue
            k = min(ks, key=lambda x: abs(x - tgt * s0))
            name = f"BTC-{ms_to_deribit(nxt)}-{k}-{'C' if otype == 'call' else 'P'}"
            near = [x for x in prints["strangle_trades"]
                    if x["instrument_name"] == name
                    and abs(x["timestamp"] - t_r) <= MSEC_DAY]
            if near:
                real += 1
            else:
                proxy += 1
    L.append(f"  roll legs with real prints (+/-1d): {real}; "
             f"priced via DVOL+skew proxy: {proxy} "
             f"({real / max(real + proxy, 1):.0%} real)")
    L.append("  (phase-2 delta-hedged prereg must use prints where real;")
    L.append("   proxy share above is the model-risk upper bound)")

    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {out}")


def strike_of(name: str) -> float:
    return float(name.split("-")[2])


def expiry_of(name: str) -> float | None:
    """Deribit instrument name BTC-23FEB24-34000-P -> expiry ms (08:00 UTC)."""
    import calendar
    try:
        tag = name.split("-")[1]          # e.g. '23FEB24'
        day, mon_s, yy = int(tag[:2]), tag[2:5].upper(), int(tag[5:7])
        month = list(calendar.month_abbr).index(mon_s.title())
        return calendar.timegm((2000 + yy, month, day, 8, 0, 0)) * 1000
    except Exception:
        return None


def ms_to_deribit(ms: float) -> str:
    d = dt.datetime.utcfromtimestamp(ms / 1000)
    return f"{d.day:02d}{d.strftime('%b').upper()}{d:%y}"


if __name__ == "__main__":
    main()
