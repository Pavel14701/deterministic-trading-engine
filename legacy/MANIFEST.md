# Legacy archive

Everything here is **dead code kept for reference only** - excluded from
pytest, ruff and mypy (see `pyproject.toml`). It is documented, not
deleted: every entry lists what it was, why it died, and how to revive
it if ever needed. Do not import from `legacy/` in live code.

Archived: 2026-09-19, repo restructure after stage D.12 (see
STATUS.md). Live surface after cleanup: `ai/` (library), `scripts/`
(research pipeline), `tests/`, vendored `ta/`, the minimal root `dsl/`
subset (imported by `ta/src/provider.py`), `data/`, `runs/`.

## dev_docs/ (archived 2026-09-20)

The design docs of the former monorepo and the research stage: TZ-00
(roadmap) through TZ-15 (OKX API events), the indicator baseline
report (`ai_baseline_report.md` - still the canonical reference for
indicator default params, cited from `ta/src/provider.py`), the quant
checklist, statistics/strategy notes, testing conventions. Nothing in
`engine/` or `dsl/` imports from here; `legacy/dev_docs/tz/` remains
the spec-of-record for anything not yet re-derived in STATUS.md.

## packages/

| package | was | why dead | revival path |
|---|---|---|---|
| `dsl/` | strategy DSL (tokenizer/parser/interpreter, 7k lines) | superseded by the D-stage geometry pipeline; stop-rule engine extracted verbatim to `scripts/zones.py` | a **minimal live subset** (`exceptions.py`, `providers/base.py`, `providers/manifest.py`) was kept at the root `dsl/` because the vendored `ta/src/provider.py` imports it; a full revival is not planned |
| `strategies/` | rule strategies for the DSL engine | tied to the DSL engine | none |
| `okx/` | full OKX exchange adapter (ws, executor, collector, DI) | only `fetch.py` is live - it moved to `ai/marketdata/okx_fetch.py` (the data path). The rest (ws, executor, collector, DI) was built pre-pivot for a live bot that was not started | **stage "live execution" (NEXT)**: the ws/executor/signing design is sound and tested; copy back the needed modules rather than resurrecting wholesale |
| `contracts/` | Candle/OhlcvBatch msgspec contracts | only consumer was `okx/` | goes together with `okx/` |
| `tinvest/` | T-Bank (Tinkoff Invest) API client | the project pivoted from T-Bank RAG to crypto research | none |
| `rag/`, `infer/`, `main/`, `risk/` | services of the original t-invest RAG system | same pivot | none |
| `backtest/` | service-style backtester | replaced by the unified event simulator `scripts/sim_engine.py` (`sim`/`pess`) | none - `sim_engine` is strictly better |
| `migrations/`, `alembic.ini`, `docker-compose.yaml` (in `root/`) | Postgres infra of the service layout | storage moved to plain parquet (`data/`, `runs/`) | none |

## scripts/ (former research entry points)

| script | was | why dead |
|---|---|---|
| `dsl_stage0.py`, `dsl_strategy_search.py` | DSL strategy search | engine superseded; three stop-geometry functions extracted verbatim to `scripts/zones.py` (public names: `compute_anchors`, `paint_zone`, `build_tp_sl`) |
| `d6b_joint_v2.py` | joint ranking v2 (D.6b) | superseded by the 2x2 matrix / walk-forward protocol (`scripts/matrix_2x2.py`, `scripts/wf_ab.py`); results in STATUS.md D.6b |
| `d7_trf_fair.py` | "fair" transformer run (D.7) | TRF fully parked by D.8 causal decomposition (D-C=0); result preserved in STATUS.md |
| `build_transformer_dataset.py` | TRF dataset builder | only consumer was the TRF training path above |
| `train_okx.py`, `train_mtf_model.py`, `train_entryexit_mtf.py` | legacy training entry points | replaced by WF training inside `scripts/wf_ab.py` / `scripts/matrix_2x2.py` |
| `eval_okx.py`, `eval_trf_ab.py`, `backtest.py` | legacy evaluators | replaced by the stage D scripts |
| `run_pipeline.py`, `replay_state_machine.py`, `attention_diagnostics.py` | orchestration / replay / TRF attention diagnostics | one-off diagnostics, documented in STATUS.md D.7 |

## ai/ (former `ai/src` modules)

| module | was | why dead |
|---|---|---|
| `bundle.py` | model save/load bundle | served the service-style inference path |
| `contracts.py` | batch validation | served the trainer/bundle path |
| `dataset.py` | torch `TradingDataset` | served the torch trainer; LGBM pipeline reads panels directly |
| `device.py` | CUDA/DirectML device resolution | torch training left the research path |
| `losses.py` | dual loss (torch) | same |
| `metrics.py` | action accuracy / trade metrics | same; WF scripts compute their own stats |
| `quickstart.py` | end-to-end toy trainer | same |
| `training.py` | torch training loop / self-training | same |

Their tests are in `tests_ai/`. `transformer.py` (the model itself)
stayed live - `scripts/matrix_2x2.py` needs it for the parked TRF cells.

## marketdata/tinvest_source.py

T-Bank candle source; the project trades OKX only. `common.py` and
`okx_source.py` moved to `ai/marketdata/` (live - data expansion for
more assets will use them).

## logs/

Raw run logs of stages D.1-D.12 (build/train/pytest). Numbers quoted in
STATUS.md; kept as provenance.

## Known upstream failure

`ta/tests/.../test_midprice_with_nan` - vendored `ta/` library, fails on
its own synthetic case, unrelated to the pipeline (documented since the
first full-suite run). `ta/` is excluded from the default pytest
path (`testpaths = ["tests"]`).

## Second pass (restructure v2, 2026-09-19)

- **Root `dsl/` restored in full** (it had been replaced by a hand-made
  5-file minimal subset): original `dte-dsl` package again lives at
  `dsl/` — tokenizer/parser/AST/interpreter/evaluate, all providers
  (in_process, http), README, docs/, own pyproject (workspace member),
  and its test suite (26 tests). `dsl/tests` are back in the default
  pytest run and in CI. Nothing was lost content-wise meanwhile: the
  archived `legacy/packages/dsl` is byte-identical to the checkpoint
  root `dsl/` and stays as the monorepo-layout archive.
- **Ghost dependency fixed**: `pandas` was used by live code
  (`ai/mtf_model.py`, `scripts/wf_ab.py`, `matrix_2x2.py`,
  `nested_cv.py`) but declared nowhere — it rode along in the old
  lockfile via yfinance. Now declared in root + ai pyprojects.

- `ai/transformer.py` moved here (from `ai/transformer.py`);
  `tests/test_transformer.py`
  and the two transformer-reference tests cut from `tests/test_ob_pipeline.py`
  (`test_transformer_encodes_all_ob_fields`,
  `test_vectorised_ob_encoding_matches_per_block`, appended at the bottom of
  `legacy/tests_ai/test_transformer.py`). The module had zero live importers:
  `scripts/matrix_2x2.py` carries its own inline torch TRF for cells C/D.
- `ai/docs/` (7 md files describing the archived transformer system) ->
  `legacy/ai_docs/`.
- `tests/conftest.py`: transformer-only fixtures removed (sample_batch,
  sample_batch_tensors, model_params, sample_action_outcome_labels,
  sample_parquet_files, Batch alias); shared data fixtures kept.
- Deps trimmed: `tensorboard`, gpu extras (torch-directml / onnx /
  onnxruntime-directml) removed from `ai/pyproject.toml` (torch kept for
  matrix_2x2). `configs/ai.yaml` restored after being dropped in v1
  (live builders need `load_config(risk_profile=...)`).

## Third pass (restructure v3, 2026-09-20)

- `ai/` -> `engine/` decomposed into functional subpackages; research
  `scripts/` dissolved into `engine/experiments/` (d-prefixes dropped);
  dataset builders -> `engine/datasets/`. See STATUS.md 2026-09-20.
- `dev_docs/` archived here (section above) - the repo root now carries
  README.md + STATUS.md only.
