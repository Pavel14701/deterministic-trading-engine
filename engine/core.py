# -*- coding: utf-8 -*-
"""Параметрическое ядро метрик и сигналов (engine/core.py).

ЕДИНОЕ МЕСТО истины для новых модулей: все показатели, которыми
измеряются стратегии, живут здесь в параметрическом виде.  Frozen
(passed) модули НЕ импортируют это ядро -- у них свои побайтовые
копии, потому что они являются regression-контрактом (любое их
изменение аннулирует PASS).  Обязательство ядра -- обратное:
параметрики с дефолтами, равными frozen-значениям, обязаны давать
бит-в-бит тот же результат, что и frozen-копии.  Это проверяется
тестом ``engine/tests/test_core.py``.

Правила:
  1. Новый код (experiments/) импортирует метрики отсюда, а не
     копирует их из passed-модулей.
  2. Дефолты параметров = frozen-значения проекта (70/345, S1,
     lags 500, block 500, seed 11).  Менять дефолты = ломать
     сопоставимость всей книги; менять можно только через новый
     датированный prereg.
  3. Ядро не импортирует ничего из experiments/.
"""
from __future__ import annotations

import numpy as np

from ta.src.custom.avs_base import (
    _avs_base,
    _compute_len_v,
    _compute_vpcc,
    _price_v_rolling,
)
from ta.src.overlap.sma import sma_ind

# ---- значения frozen-конфига (дефолты ядра) --------------------------------
FAST, SLOW = 70, 345
STAND_DIV = 2.0
MSEC_4H = 14_400_000
ANN = 6 * 365                # 4H-баров в году
VOL_WIN = 100
VOL_TARGET = 0.20
SIZE_MIN, SIZE_MAX = 0.25, 2.0
RISK_PCT = 0.01              # 1% капитала на 1.0 единицу размера
NW_LAGS = 500
BOOT_B = 1000
BOOT_BLOCK = 500             # = HORIZON
BOOT_SEED = 11               # seed заархивированных вердиктов; НЕ менять


# ---- сигнал -----------------------------------------------------------------
def fast_line_p(lp: np.ndarray, cp: np.ndarray, vol: np.ndarray,
                fast: int = FAST, slow: int = SLOW,
                stand_div: float = STAND_DIV) -> np.ndarray:
    """Параметрическая линия AVSL(fast, slow), NaN-безопасная.

    Бит-в-бит совпадает с engine.passed.avsl_cross_s1.fast_line
    при дефолтных fast=70, slow=345 (проверено тестом).
    """
    vpc, vpr, _vm, vpci, dev = _avs_base(cp, vol, fast, slow,
                                         stand_div, False)
    len_v = _compute_len_v(vpc, vpci)
    vpcc = _compute_vpcc(vpc)
    price_v = _price_v_rolling(lp, vpr, len_v, vpcc)
    adjusted = lp - price_v + dev
    return np.asarray(
        sma_ind(adjusted, slow, use_talib=False, nan_policy="ffill"),
        dtype=np.float64,
    )


def resample_bars(ts: np.ndarray, hp: np.ndarray, lp: np.ndarray,
                  cp: np.ndarray, vol: np.ndarray,
                  msec: int = MSEC_4H) -> tuple:
    """Детерминированный агрегат 1H -> msec-бары (first/max/min/last/sum).

    Семантически эквивалентна frozen resample_4h при
    msec=14_400_000.  Оговорка: поларсовский group_by-sum
    параллелен, поэтому float-суммы (vol) могут отличаться от
    frozen-копии на последний бит — это не влияет на вердикты.
    """
    import polars as pl

    bucket = ts // msec
    df = pl.DataFrame(
        {"b": bucket, "ts": ts, "hp": hp, "lp": lp, "cp": cp,
         "vol": vol},
    )
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


# ---- сайзинг ----------------------------------------------------------------
def s1_sizes_p(cp: np.ndarray, vol_win: int = VOL_WIN,
               vol_target: float = VOL_TARGET,
               size_min: float = SIZE_MIN,
               size_max: float = SIZE_MAX,
               ann: int = ANN) -> np.ndarray:
    """S1 vol-target размер: clip(vol_target / rv{vol_win}, min, max).

    rv на баре i = std лог-доходностей за vol_win баров ДО i
    (сам бар исключён), годовая.  NaN-фолбэк = 1.0 (без сайза).
    Бит-в-бит совпадает с frozen s1_sizes при дефолтах.
    """
    n = len(cp)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(cp[1:] / cp[:-1])
    sizes = np.ones(n)
    for i in range(1, n):
        r = np.nanstd(lr[max(0, i - vol_win):i]) * np.sqrt(ann)
        if np.isfinite(r) and r > 0:
            sizes[i] = float(np.clip(vol_target / r, size_min, size_max))
    return sizes


def sized_accrual_stream_p(trades: list[dict], sizes: np.ndarray,
                           n_g: int) -> np.ndarray:
    """Бар-поток портфеля в R: каждая открытая сделка начисляет
    size x net R линейно по барам удержания.
    """
    s = np.zeros(n_g + 1)
    for tr in trades:
        hold = max(tr["e1"] - tr["e0"], 1)
        w = sizes[tr["e0"]] * tr["net"] / (hold + 1)
        s[tr["e0"]:tr["e1"] + 1] += w
    return s[:n_g]


# ---- измерение (battery-показатели) -----------------------------------------
def nw_sharpe_p(v: np.ndarray, lags: int = NW_LAGS,
                ann: int = ANN) -> float:
    """Годовой Sharpe с поправкой Newey-West на бар-поток.

    factor = sqrt(1 + 2*sum(rho_k)), k = 1..lags.
    """
    v = v[np.isfinite(v)]
    if v.size < 30 or v.std() == 0:
        return float("nan")
    rhos = []
    for k in range(1, min(lags, v.size - 10) + 1):
        c = np.corrcoef(v[:-k], v[k:])[0, 1]
        if np.isfinite(c):
            rhos.append(c)
    factor = float(np.sqrt(max(1e-6, 1.0 + 2.0 * float(np.sum(rhos)))))
    return float(v.mean() / v.std() * np.sqrt(ann) / factor)


def block_bootstrap_ci_p(v: np.ndarray, b: int = BOOT_B,
                         block: int = BOOT_BLOCK,
                         seed: int = BOOT_SEED) -> tuple:
    """Циркулярный block bootstrap 95% CI среднего (дефолты = frozen:
    b=1000, block=500, seed=11).  Возвращает (2.5%, 97.5%).
    """
    v = np.asarray(v)
    n = v.size
    if n < block:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(b, n_blocks))
    means = np.empty(b)
    for i in range(b):
        idx = np.concatenate(
            [(np.arange(starts[i, j], starts[i, j] + block)) % n
             for j in range(n_blocks)],
        )[:n]
        means[i] = v[idx].mean()
    return float(np.percentile(means, 2.5)), \
        float(np.percentile(means, 97.5))


def portfolio_dd_p(stream: np.ndarray,
                   risk_pct: float = RISK_PCT) -> float:
    """Максимальная просадка cumprod(1 + risk_pct x бар-поток)."""
    eq = np.cumprod(1.0 + risk_pct * stream)
    return float(np.max(1.0 - eq / np.maximum.accumulate(eq)))


# ---- переэкспорт battery v2 (замороженная измерительная батарея) ------------
# enb / ortho_ev / xs_bootstrap_ci / concurrency живут в engine.battery_v2
# (frozen); здесь только удобный re-export для новых модулей.
from engine.battery_v2 import (  # noqa: E402
    concurrency,
    enb,
    ortho_ev,
    xs_bootstrap_ci,
)

__all__ = [
    "fast_line_p", "resample_bars", "s1_sizes_p",
    "sized_accrual_stream_p", "nw_sharpe_p", "block_bootstrap_ci_p",
    "portfolio_dd_p", "enb", "ortho_ev", "xs_bootstrap_ci",
    "concurrency",
]



