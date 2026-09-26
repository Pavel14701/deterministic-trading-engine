# -*- coding: utf-8 -*-
"""E2E-тест ранера теорий: синтетика -> сделки -> метрики -> регистрация."""
from pathlib import Path

import numpy as np
import pytest

from experiments.infra.theory_runner import (
    evaluate,
    load_theory,
    register,
)


def _theory_yaml() -> str:
    return """
name: t-e2e
version: 0.1.0
family: avsl
experiment: theory_e2e_tmp
universe: [AAA, BBB]
timeframe: 1h
warmup: 100
entry_long: >-
  close > avsl(fast=5, slow=30)
  and close[1] <= avsl(fast=5, slow=30)[1]
entry_short: >-
  close < avsl(fast=5, slow=30)
  and close[1] >= avsl(fast=5, slow=30)[1]
k_atr: 2.0
stop_line: "avsl(fast=5, slow=30)"
targets: [2, 3, 5]
primary: 3
horizon: 24
fee_bps: 5
sizing: s1
segments: 2
"""


def _synth(seed: int) -> tuple:
    rng = np.random.default_rng(seed)
    n = 900
    ts = (1_700_000_000_000 + np.arange(n) * 3_600_000).astype(np.int64)
    steps = rng.normal(0.0008, 0.01, size=n)
    cp = 100.0 * np.exp(np.cumsum(steps))
    spread = np.abs(rng.normal(0, 0.004, size=n)) + 1e-4
    hp = cp * (1.0 + spread)
    lp = cp * (1.0 - spread)
    vol = rng.uniform(10.0, 100.0, size=n)
    return ts, hp.astype(float), lp.astype(float), cp.astype(float), vol


@pytest.fixture()
def data() -> dict:
    return {"AAA": _synth(11), "BBB": _synth(12)}


def test_e2e_run_and_gates(tmp_path: Path, data: dict) -> None:
    p = tmp_path / "t.yaml"
    p.write_text(_theory_yaml(), encoding="utf-8")
    th = load_theory(p)
    rep = evaluate(th, data=data, repo=tmp_path)
    assert rep["n_trades"] > 0
    assert np.isfinite(rep["ev_net"])
    assert {"G1_sharpe", "G2_dd", "G3_ev", "G4_pos_assets",
            "G5_ci_excl_0"} <= set(rep["gates"])
    assert rep["verdict"] in ("PASS", "FAIL")
    for sym in ("AAA", "BBB"):
        assert rep["per_asset"][sym]["trades"] > 0


def test_register_creates_experiment(tmp_path: Path, data: dict) -> None:
    p = tmp_path / "t.yaml"
    p.write_text(_theory_yaml(), encoding="utf-8")
    th = load_theory(p)
    rep = evaluate(th, data=data, repo=tmp_path)
    (tmp_path / "experiments" / "avsl").mkdir(parents=True, exist_ok=True)
    (tmp_path / "experiments" / "avsl" / "__init__.py").write_text("",
                                                                  "utf-8")
    d = register(th, rep, p, repo=tmp_path)
    assert (d / "EXPERIMENT.md").exists()
    assert (d / "t.yaml").exists()
    text = (d / "EXPERIMENT.md").read_text(encoding="utf-8")
    assert "t-e2e" in text and "v0.1.0" in text


def test_no_signal_theory_is_safe(tmp_path: Path, data: dict) -> None:
    p = tmp_path / "t.yaml"
    p.write_text(_theory_yaml().replace("warmup: 100", "warmup: 50000"),
                 encoding="utf-8")
    th = load_theory(p)
    rep = evaluate(th, data=data, repo=tmp_path)
    assert rep["n_trades"] == 0
    assert rep["verdict"] == "FAIL"
