# -*- coding: utf-8 -*-
"""Универсальный ранер теорий: yaml/DSL -> симуляция -> метрики -> гейты.

Позволяет заводить эксперимент БЕЗ питон-скрипта: гипотеза описывается
yaml-файлом (схема -- dsl/theory.py:Theory), условия входа -- выражениями
DSL.  Ранер делает остальное:

  1. грузит бары (data/binance/kl_<SYM>USDT_1h.parquet), ресемплит до
     timeframe теории (engine.core.resample_bars, frozen-семантика);
  2. предвычисляет серии индикаторов из выражений (avsl, sma, atr);
  3. на каждом баре t >= warmup вычисляет entry_long/entry_short через
     DSL-интерпретатор и симулирует сделки по frozen-конвенциям
     (вход по close[t], консервативный within-bar, stop-wins, MTM
     через horizon, fee в R) -- 1:1 как engine/passed/avsl_cross_s1;
  4. считает метрики ТОЛЬКО через engine.core/battery_v2 (никаких
     локальных копий): EV, WR, NW-Sharpe, bootstrap CI, DD, сегменты;
  5. выносит вердикт по гейтам G1'--G5' (пороги docs/BATTERY.md,
     переопределяются в theory.gates);
  6. по --register заводит experiments/<family>/<experiment>/ с
     EXPERIMENT.md и записью версии.

Запуск:
    uv run python -m experiments.infra.theory_runner <theory.yaml>
    uv run python -m experiments.infra.theory_runner <theory.yaml> --register
"""
from __future__ import annotations

import argparse
import json
import shutil

from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from dsl.context import Context
from dsl.exceptions import DSLError
from dsl.interpreter import Interpreter
from dsl.parser import parse
from dsl.theory import SeriesProvider, Theory, load_theory, scan_indicators
from engine.battery_v2 import concurrency
from engine.core import (
    block_bootstrap_ci_p,
    fast_line_p,
    nw_sharpe_p,
    portfolio_dd_p,
    resample_bars,
    s1_sizes_p,
    sized_accrual_stream_p,
)
from ta.src.overlap.sma import sma_ind
from ta.src.volatility.atr import atr_ind


MSEC = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
GATE_DEFAULTS = {"g1_min_sharpe": 1.0, "g2_max_dd": 0.25,
                 "g3_min_ev": 0.10, "g4_min_pos": 0.7}
ATR_PERIOD = 14

REPO = Path(__file__).resolve().parents[2]


# ---- данные и серии ----------------------------------------------------------

def load_data(sym: str, msec: int, repo: Path = REPO) -> tuple:
    """Binance 1H parquet -> ресемпл до msec (frozen-семантика)."""
    df = pl.read_parquet(repo / f"data/binance/kl_{sym}USDT_1h.parquet")
    ts, hp, lp, cp, vol = (
        df["ts"].to_numpy().astype(np.int64),
        df["high"].to_numpy().astype(np.float64),
        df["low"].to_numpy().astype(np.float64),
        df["close"].to_numpy().astype(np.float64),
        df["volume"].to_numpy().astype(np.float64),
    )
    if msec != MSEC["1h"]:
        ts, hp, lp, cp, vol = resample_bars(ts, hp, lp, cp, vol, msec)
    return ts, hp, lp, cp, vol


def precompute(theory: Theory, hp: np.ndarray, lp: np.ndarray,
               cp: np.ndarray, vol: np.ndarray) -> dict[tuple, np.ndarray]:
    """Предвычислить все серии, встречающиеся в выражениях теории.

    OHLCV всегда; atr(14) всегда (риск-модель); avsl/sma -- по вызовам.
    """
    series: dict[tuple, np.ndarray] = {
        ("close", frozenset()): cp,
        ("high", frozenset()): hp,
        ("low", frozenset()): lp,
        ("volume", frozenset()): vol,
        ("atr", frozenset({("period", ATR_PERIOD)})): np.asarray(
            atr_ind(hp, lp, cp, ATR_PERIOD, use_talib=False)),
    }
    used = scan_indicators(theory.entry_long, theory.entry_short,
                           theory.stop_line)
    for name, params_list in used.items():
        for params in params_list:
            key = (name, frozenset(params.items()))
            if key in series:
                continue
            if name == "avsl":
                series[key] = fast_line_p(
                    lp, cp, vol, int(params.get("fast", 70)),
                    int(params.get("slow", 345)))
            elif name == "sma":
                series[key] = np.asarray(
                    sma_ind(cp, int(params.get("period", 20)),
                            use_talib=False, nan_policy="ffill"))
            elif name == "atr":
                series[key] = np.asarray(
                    atr_ind(hp, lp, cp, int(params.get("period", 14)),
                            use_talib=False))
            else:
                raise ValueError(
                    f"индикатор '{name}' не поддержан раннером; "
                    f"доступны: avsl, sma, atr")
    return series


# ---- симуляция (frozen-конвенции: engine/passed/avsl_cross_s1) ---------------

def _sim_outcome(hp, lp, cp, t, is_long, stop, target, horizon):
    """(gross R, бар выхода); консервативный within-bar, stop-wins."""
    risk = cp[t] - stop if is_long else stop - cp[t]
    if risk <= 0:
        return None, t
    tp = cp[t] + target * risk if is_long else cp[t] - target * risk
    n = len(cp)
    for k in range(t + 1, min(t + 1 + horizon, n)):
        if is_long:
            if lp[k] <= stop:
                return -1.0, k
            if hp[k] >= tp:
                return target, k
        else:
            if hp[k] >= stop:
                return -1.0, k
            if lp[k] <= tp:
                return target, k
    sign = 1.0 if is_long else -1.0
    return (float(sign * (cp[min(t + horizon, n - 1)] - cp[t]) / risk),
            min(t + horizon, n - 1))


def _series_schemas(series: dict[tuple, np.ndarray]) -> dict:
    """Манифест провайдера из предвычисленных серий."""
    schemas: dict[str, dict] = {}
    for (name, params) in series:
        schemas.setdefault(name, {"parameters": {}, "attributes": []})
        for (p, _v) in params:
            schemas[name]["parameters"][p] = {"type": "any"}
    return schemas


def collect_trades(theory: Theory, series: dict[tuple, np.ndarray],
                   hp, lp, cp, buckets: np.ndarray, g0: int) -> list[dict]:
    """Прогон сигналов теории по барам: DSL-условия + симуляция сделок."""
    provider = SeriesProvider(series, _series_schemas(series))
    interp = Interpreter(Context([provider]))
    try:
        ast_long = parse(theory.entry_long)
        ast_short = parse(theory.entry_short)
    except DSLError as e:
        raise ValueError(f"теория {theory.name}: {e}") from e

    atr = series["atr", frozenset({("period", ATR_PERIOD)})]
    stop_key = None
    if theory.stop_line:
        (sname, sparams), = [
            (n, p[0]) for n, p in scan_indicators(theory.stop_line).items()
        ]
        stop_key = (sname, frozenset(sparams.items()))
    fee_mult = 2.0 * theory.fee_bps * 1e-4

    trades: list[dict] = []
    n = len(cp)
    for t in range(theory.warmup, n - 1):
        provider.bar = t
        try:
            up = interp.visit(ast_long)
            dn = interp.visit(ast_short)
        except (DSLError, IndexError):
            continue  # NaN/за краем истории -> бара-сигнала нет
        if not (up or dn):
            continue
        is_long = bool(up)
        risk = theory.k_atr * float(atr[t])
        if stop_key is not None:
            risk = max(risk, abs(cp[t] - float(series[stop_key][t])))
        if not np.isfinite(risk) or risk <= 0:
            continue
        stop = cp[t] - risk if is_long else cp[t] + risk
        pnl, k_exit = _sim_outcome(hp, lp, cp, t, is_long, stop,
                                   theory.primary, theory.horizon)
        if pnl is None:
            continue
        trades.append({
            "net": pnl - fee_mult * cp[t] / risk,
            "gross": pnl,
            "e0": int(buckets[t]) - g0,
            "e1": int(buckets[k_exit]) - g0,
            "long": is_long,
        })
    return trades

# ==== CUT-EVAL ====


# ---- метрики и гейты (только engine.core / battery_v2) -----------------------

def evaluate(theory: Theory, data: dict[str, tuple] | None = None,
             repo: Path = REPO) -> dict:
    """Полный прогон теории по юниверсу: сделки -> метрики -> гейты."""
    msec = MSEC[theory.timeframe]
    per_asset, all_trades = {}, []
    g0g, n_g = None, 0
    assets = {}
    for sym in theory.universe:
        ts, hp, lp, cp, vol = (data[sym] if data and sym in data
                               else load_data(sym, msec, repo))
        assets[sym] = (ts, hp, lp, cp, vol)
        buckets = ts // msec
        g0 = int(buckets[0])
        g0g = g0 if g0g is None else min(g0g, g0)
        n_g = max(n_g, int(buckets[-1]) - g0 + 1)
    stream = np.zeros(n_g + 1)
    for sym, (ts, hp, lp, cp, vol) in assets.items():
        g0 = int((ts // msec)[0])
        series = precompute(theory, hp, lp, cp, vol)
        trades = collect_trades(theory, series, hp, lp, cp, ts // msec, g0)
        for tr in trades:
            tr["sym"] = sym
        all_trades.extend(trades)
        nets = np.array([t["net"] for t in trades])
        sizes = (s1_sizes_p(cp) if theory.sizing == "s1"
                 else np.ones(len(cp)))
        s = sized_accrual_stream_p(trades, sizes, len(cp))
        off = g0 - g0g
        stream[off:off + len(s)] += s
        per_asset[sym] = {
            "trades": len(trades),
            "ev_net": float(nets.mean()) if nets.size else float("nan"),
            "wr": float((nets > 0).mean()) if nets.size else float("nan"),
        }
    stream = stream[:n_g]
    return _metrics_report(theory, all_trades, stream, per_asset, assets,
                           msec, g0g, n_g)


def _metrics_report(theory: Theory, all_trades: list, stream: np.ndarray,
                    per_asset: dict, assets: dict, msec: int,
                    g0g: int, n_g: int) -> dict:
    """Сводные метрики + вердикт по гейтам G1'--G5'."""
    nets = np.array([t["net"] for t in all_trades])
    sharpe = nw_sharpe_p(stream)
    ci_lo, ci_hi = block_bootstrap_ci_p(stream)
    dd = portfolio_dd_p(stream)
    seg_sharpes = [nw_sharpe_p(s) for s in
                   np.array_split(stream, theory.segments)]
    ctxs = {s: {"g0": int((assets[s][0] // msec)[0])} for s in assets}
    n_open = concurrency(all_trades, ctxs, g0g, n_g)

    gd = {**GATE_DEFAULTS, **theory.gates}
    ev = float(np.nanmean(nets)) if nets.size else float("nan")
    gates = {
        "G1_sharpe": {"value": round(min(seg_sharpes), 3),
                      "threshold": f">= {gd['g1_min_sharpe']}",
                      "pass": min(seg_sharpes) >= gd["g1_min_sharpe"]},
        "G2_dd": {"value": round(dd, 3),
                  "threshold": f"<= {gd['g2_max_dd']}",
                  "pass": dd <= gd["g2_max_dd"]},
        "G3_ev": {"value": round(ev, 3),
                  "threshold": f">= {gd['g3_min_ev']}",
                  "pass": bool(nets.size) and ev >= gd["g3_min_ev"]},
        "G5_ci_excl_0": {"value": [round(ci_lo, 3), round(ci_hi, 3)],
                         "threshold": "0 вне CI",
                         "pass": bool(ci_lo > 0 or ci_hi < 0)},
    }
    if len(theory.universe) > 1:
        n_pos = sum(1 for v in per_asset.values() if v["ev_net"] > 0)
        gates["G4_pos_assets"] = {
            "value": f"{n_pos}/{len(theory.universe)}",
            "threshold": f">= {gd['g4_min_pos']:.0%}",
            "pass": n_pos / len(theory.universe) >= gd["g4_min_pos"]}
    return {
        "theory": f"{theory.name} v{theory.version}",
        "timeframe": theory.timeframe,
        "sizing": theory.sizing,
        "primary_tp_r": theory.primary,
        "n_trades": len(all_trades),
        "ev_net": ev,
        "wr": float((nets > 0).mean()) if nets.size else float("nan"),
        "nw_sharpe": sharpe,
        "ci95": [ci_lo, ci_hi],
        "max_dd": dd,
        "segment_sharpes": seg_sharpes,
        "concurrency_max": float(n_open.max()),
        "per_asset": per_asset,
        "gates": gates,
        "verdict": "PASS" if all(g["pass"] for g in gates.values())
        else "FAIL",
    }

# ==== CUT-CLI ====


# ---- отчёт и регистрация -----------------------------------------------------

def write_report(report: dict, theory: Theory, repo: Path = REPO) -> Path:
    out = repo / "runs" / f"theory_{theory.name}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


def register(theory: Theory, report: dict, src: Path,
             repo: Path = REPO) -> Path:
    """Завести эксперимент: папка + копия теории + EXPERIMENT.md."""
    d = repo / "experiments" / theory.family / theory.experiment
    d.mkdir(parents=True, exist_ok=True)
    ini = d / "__init__.py"
    if not ini.exists():
        base = repo / "experiments" / theory.family / "__init__.py"
        ini.write_text(base.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copy(src, d / src.name)
    icon = "🟢" if report["verdict"] == "PASS" else "⚫"
    gate_s = ", ".join(f"{k}={'PASS' if v['pass'] else 'FAIL'}"
                       for k, v in report["gates"].items())
    (d / "EXPERIMENT.md").write_text(
        f"# {theory.name} (DSL-теория)\n\n"
        f"- Семья: `{theory.family}/`\n"
        f"- Статус: {icon} {report['verdict']} (теория, не прereg-прогон)\n"
        f"- Теория: `{src.name}` v{theory.version}; запуск: "
        f"`python -m experiments.infra.theory_runner "
        f"{theory.family}/{theory.experiment}/{src.name}`\n"
        f"- Вердикт: EV {report['ev_net']:+.3f}R, WR {report['wr']:.1%}, "
        f"NW-Sh {report['nw_sharpe']:.2f}, DD {report['max_dd']:.1%}, "
        f"n={report['n_trades']}; гейты: {gate_s}\n"
        f"- Отчёт: `runs/theory_{theory.name}.json`\n\n"
        f"## История версий\n\n"
        f"| версия | дата | изменение |\n|---|---|---|\n"
        f"| v{theory.version} | {date.today().isoformat()} | "
        f"первичный прогон теории |", encoding="utf-8")
    return d


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Прогон DSL-теории: симуляция + метрики + гейты")
    ap.add_argument("theory", help="путь к yaml-файлу теории")
    ap.add_argument("--register", action="store_true",
                    help="завести experiments/<family>/<experiment>/")
    args = ap.parse_args()
    src = Path(args.theory)
    theory = load_theory(src)
    report = evaluate(theory)
    print(f"== {report['theory']} [{theory.timeframe}, "
          f"TP={theory.primary}R, {theory.sizing}] ==")
    for sym, st in report["per_asset"].items():
        print(f"  {sym:8s} n={st['trades']:4d}  EV={st['ev_net']:+.3f}R  "
              f"WR={st['wr']:.1%}")
    print(f"  pooled   n={report['n_trades']}  EV={report['ev_net']:+.3f}R"
          f"  WR={report['wr']:.1%}")
    print(f"  NW-Sharpe={report['nw_sharpe']:.2f}  "
          f"CI95=[{report['ci95'][0]:.2f}, {report['ci95'][1]:.2f}]  "
          f"DD={report['max_dd']:.1%}  "
          f"maxConcurrent={report['concurrency_max']:.0f}")
    for g, v in report["gates"].items():
        print(f"  {g:16s} {v['value']!s:12s} ({v['threshold']})  "
              f"{'PASS' if v['pass'] else 'FAIL'}")
    print(f"  VERDICT: {report['verdict']}")
    out = write_report(report, theory)
    print(f"  отчёт: {out.relative_to(REPO)}")
    if args.register:
        d = register(theory, report, src)
        print(f"  эксперимент заведён: {d.relative_to(REPO)}/")


if __name__ == "__main__":
    main()



