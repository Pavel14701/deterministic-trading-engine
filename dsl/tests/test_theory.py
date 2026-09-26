# -*- coding: utf-8 -*-
"""Тесты dsl.theory: схема, сканер индикаторов, SeriesProvider."""
from pathlib import Path

import pytest

from dsl.context import Context
from dsl.interpreter import Interpreter
from dsl.parser import parse
from dsl.theory import SeriesProvider, load_theory, scan_indicators


YAML = """
name: t-demo
version: 0.1.0
family: demo
experiment: demo_exp
universe: [TEST]
timeframe: 1h
warmup: 10
entry_long: "close > avsl(fast=5, slow=20) and close[1] <= avsl(fast=5, slow=20)[1]"
entry_short: "close < avsl(fast=5, slow=20)"
k_atr: 2.0
stop_line: "sma(period=20)"
targets: [2, 3]
primary: 3
horizon: 24
sizing: flat
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "t.yaml"
    p.write_text(YAML, encoding="utf-8")
    return p


def test_load_theory(tmp_path: Path) -> None:
    th = load_theory(_write(tmp_path))
    assert th.name == "t-demo"
    assert th.universe == ["TEST"]
    assert th.primary == 3.0
    assert th.stop_line == "sma(period=20)"
    assert th.sizing == "flat"


def test_load_theory_missing_field(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="обязательных полей"):
        load_theory(p)


def test_scan_indicators() -> None:
    used = scan_indicators(
        "close > avsl(fast=5, slow=20) and close[1] <= sma(period=20)[1]",
        None)
    assert used == {"avsl": [{"fast": 5, "slow": 20}],
                    "sma": [{"period": 20}]}


def test_series_provider_and_eval() -> None:
    cp = [10.0 + i * 0.1 for i in range(50)]
    sma = [sum(cp[max(0, i - 2):i + 1]) / len(cp[max(0, i - 2):i + 1])
           for i in range(50)]
    schemas = {"close": {"parameters": {}, "attributes": []},
               "sma": {"parameters": {"period": {"type": "any"}},
                       "attributes": []}}
    prov = SeriesProvider({("close", frozenset()): cp,
                           ("sma", frozenset({("period", 3)})): sma},
                          schemas)
    interp = Interpreter(Context([prov]))
    prov.bar = 40
    assert interp.visit(parse("close > sma(period=3)")) is True
    prov.bar = 0
    assert interp.visit(parse("close[1] > sma(period=3)")) is False
