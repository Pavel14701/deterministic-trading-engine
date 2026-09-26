# -*- coding: utf-8 -*-
"""Теория эксперимента в декларативной форме (yaml) + провайдер серий.

Теория -- это yaml-файл, описывающий гипотезу БЕЗ питон-кода: условия
входа на языке DSL (см. dsl/README.md), риск-модель, таймфрейм и
пороги гейтов.  Исполнение теории -- experiments/infra/theory_runner.py:
он вычисляет серии индикаторов, прогоняет симуляцию по frozen-конвенциям,
считает метрики через engine.core/battery_v2 и по запросу (--register)
заводит папку эксперимента с EXPERIMENT.md.

Этот модуль намеренно БЕЗ numpy/pandas: только схема, загрузка yaml,
сканер индикаторов и SeriesProvider (стандартная библиотека + dsl).
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .providers.base import IndicatorProvider


# ---- схема теории -----------------------------------------------------------


@dataclass
class Theory:
    """Декларативное описание эксперимента (один yaml-файл)."""

    name: str
    version: str
    family: str                    # experiments/<family>/
    experiment: str                # имя папки эксперимента
    universe: list[str]            # символы (без USDT)
    timeframe: str                 # "1h" | "4h" | "1d"
    warmup: int                    # баров до первого сигнала
    entry_long: str                # DSL-выражение (bool)
    entry_short: str               # DSL-выражение (bool)
    k_atr: float = 2.0             # риск = max(..., k_atr * atr(14))
    stop_line: str | None = None   # DSL-выражение линии стопа (опц.)
    targets: list[float] = field(default_factory=lambda: [3.0, 5.0, 8.0])
    primary: float = 5.0           # основной TP (R) для вердикта
    horizon: int = 500             # MTM-выход, баров
    fee_bps: float = 5.0           # taker, за сторону (round trip = 2x)
    sizing: str = "s1"             # "s1" | "flat"
    gates: dict = field(default_factory=dict)   # переопределения порогов
    segments: int = 2              # на сколько сегментов делить поток

    REQUIRED: ClassVar[tuple] = (
        "name", "version", "family", "experiment", "universe",
        "timeframe", "warmup", "entry_long", "entry_short",
    )


def load_theory(path: str | Path) -> Theory:
    """Загрузить теорию из yaml-файла с валидацией обязательных полей."""
    import yaml  # лениво: ядро dsl остаётся без внешних зависимостей

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: ожидается yaml-отображение теории")
    missing = [k for k in Theory.REQUIRED if not raw.get(k)]
    if missing:
        raise ValueError(f"{path}: нет обязательных полей {missing}")
    if raw["timeframe"] not in ("1h", "4h", "1d"):
        raise ValueError(
            f"{path}: timeframe '{raw['timeframe']}' не поддержан")
    gates = raw.get("gates") or {}
    return Theory(
        name=str(raw["name"]),
        version=str(raw["version"]),
        family=str(raw["family"]),
        experiment=str(raw["experiment"]),
        universe=[str(s) for s in raw["universe"]],
        timeframe=str(raw["timeframe"]),
        warmup=int(raw["warmup"]),
        entry_long=str(raw["entry_long"]),
        entry_short=str(raw["entry_short"]),
        k_atr=float(raw.get("k_atr", 2.0)),
        stop_line=raw.get("stop_line"),
        targets=[float(x) for x in raw.get("targets", [3, 5, 8])],
        primary=float(raw.get("primary", 5.0)),
        horizon=int(raw.get("horizon", 500)),
        fee_bps=float(raw.get("fee_bps", 5.0)),
        sizing=str(raw.get("sizing", "s1")),
        gates=dict(gates),
        segments=int(raw.get("segments", 2)),
    )


# ---- сканер индикаторов -----------------------------------------------------

_IND = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(([^)\[]*)\)")


def scan_indicators(*exprs: str | None) -> dict[str, list[dict]]:
    """Собрать (имя, параметры) всех индикатор-вызовов в выражениях.

    Возвращает {имя: [params, ...]}.  OHLCV-имена пропускаются: они
    резолвятся напрямую из баров.
    """
    out: dict[str, list[dict]] = {}
    for expr in exprs:
        if not expr:
            continue
        for m in _IND.finditer(expr):
            name = m.group(1)
            params: dict = {}
            for chunk in m.group(2).split(","):
                if "=" in chunk:
                    k, v = chunk.split("=", 1)
                    params[k.strip()] = float(v) if "." in v else int(v)
            lst = out.setdefault(name, [])
            if params not in lst:
                lst.append(params)
    return out


# ---- провайдер предвычисленных серий ----------------------------------------


class SeriesProvider(IndicatorProvider):
    """Провайдер поверх предвычисленных numpy/list-серий.

    series: {(имя, frozenset(params.items())): последовательность float}.
    Поле ``bar`` двигается раннером по барам; offset из DSL (``x[1]``)
    превращается в индекс bar - offset.
    """

    def __init__(
        self,
        series: dict[tuple, list[float]],
        schemas: dict[str, dict],
        bar: int = 0,
    ) -> None:
        self.series = series
        self.bar = bar
        self._manifest_dict = {"indicators": schemas}

    def get_manifest(self) -> dict:
        """Манифест доступных индикаторов (формат providers.manifest)."""
        return self._manifest_dict

    def resolve(self, indicator, params, attributes, offset) -> float:
        """Значение серии (indicator, params) на баре bar - offset."""
        key = (indicator, frozenset((params or {}).items()))
        try:
            seq = self.series[key]
        except KeyError as e:  # pragma: no cover - защита от миссконфига
            raise KeyError(
                f"серия не предвычислена: {indicator} params={params}",
            ) from e
        i = self.bar - int(offset)
        if i < 0 or i >= len(seq):
            return float("nan")  # край истории -> False в сравнениях
        return float(seq[i])
