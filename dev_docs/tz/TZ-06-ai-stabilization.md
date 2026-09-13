# TZ-06. Stabilizing `ai/` (EntryExitTransformer)

> **Status: 🔨 core done; remaining items listed in acceptance.**
> ✅ torch explicit, temporal split (no validation leak), self-training isolation with rollback,
> model bundle + loader, `predict_p_win` inference contract, bisect OB index, package `ai`
> identity + doc cleanup, tests (68 passed), logging instead of print, YAML config
> (`configs/ai.yaml` + `ai/src/config.py`), compute backends (`ai/src/device.py`,
> CUDA/CPU training; ONNX DirectML/Vulkan-path inference).
> ⬜ OB-encoder batching in forward (no measurements yet); ⬜ predict_p_win < 5 ms on window 128.

## 1. Context

`ai/` is self-contained but an isolated "island" module (~3.5k lines): it does not know about
dsl/ta/strategies and is tied to the order-block concept that exists nowhere else. The core
(transformer, losses, self-training, contracts) is quality, but integration is blocked by the
problems below. Roadmap order: right after TZ-01, before TZ-02/03 — torch and the validation leak
block any model use.

## 2. Problems and rationale

### 2.1. torch absent from dependencies (critical)
`pyproject.toml` has no torch — it comes transitively via sentence-transformers. Version and
variant (CPU/CUDA) are unpinned. **Decision:** add torch explicitly with index configuration.
**Why not keep transitive:** uv-lock does not manage it directly; a sentence-transformers update
silently swaps torch.

### 2.2. Validation leak via random split (critical)
`_split_train_val` shuffles, and seq_len=128 windows overlap by 127 bars — the same market slice
in train and val, inflated metrics. Matches checklist item 5.
**Decision:** chronological split by bar ranges (train < T_val ≤ val) without window overlap at the
boundary. **Why not K-fold:** the temporal structure — "from the future" validation is meaningless
for trading.

### 2.3. Self-training destructively mutates the dataset
`_update_labels_parquet` overwrites labels.parquet with pseudo-labels without a provenance marker
→ error accumulation is irreversible. **Decision:** a separate file/column `is_pseudo`, backup of
the previous state, round rollback. **Why:** self-training is iterative; without rollback the first
bad round poisons the dataset forever.

### 2.4. Model bundle (critical for inference)
`torch.save(state_dict)` without seq_len, column list, atr_global, normalization stats — the model
cannot be reloaded correctly. **Decision:** bundle
`{state_dict, config, feature_columns, seq_len, atr_global, norm_stats}` + loader. Without a
bundle, TZ-05 (`--ml`) is technically impossible.

### 2.5. Inference contract
A function `predict_p_win(model, bundle, window, ...) -> float` — the only interaction point of the
Risk Engine and the inference script with the model. Currently absent: forward returns per-bar
logits in batches. The "< 1 ms per trade" requirement is additionally unattainable because forward
loops over order blocks in Python creating a tensor each — the OB encoder needs batching.

### 2.6. O(windows × OB) scanning
`TradingDataset.__getitem__` linearly scans all blocks per sample. On real volumes — hours.
**Decision:** an OB index by bar (sorted + bisect).

### 2.7. Package identity
Docstrings/examples reference `trading.*`; `quickstart.py` imports from `trading.quickstart`
(broken path). Fix the package name `ai`, clean the docs (including the mythical Lark parser in
`ai/docs/README.md` — see TZ-01 §2.7).

### 2.8. No tests at all
`dsl` and `ta` are covered, `ai` is not — although ai makes the most expensive decision. Minimal
set: label generator (look-ahead: a label at bar t independent of bars > t), losses,
split-leak, label parity with the TZ-04 engine (golden test).

### 2.9. Misc
`contracts.py` prints warnings via print (including "Batch validation passed." every batch) →
logging; `quickstart` hardcodes `close_idx=3`; `compute_atr` is a Python loop (numba exists);
## 3. Requirements (summarized)

1. ✅ torch in pyproject (§2.1) — declared explicitly (`torch>=2.4.1`), with index configuration.
2. ✅ Temporal split (§2.2) — `_split_train_val` by bar ranges, no overlap across the boundary.
3. ✅ Self-training isolation (§2.3) — `is_pseudo` flag + backup + rollback.
4. ✅ Model bundle (§2.4) — `save_bundle` / `load_bundle` / `rebuild_model`. ONNX export in
   `device.py` (`export_onnx` with dynamic_axes); duplicate removed from bundle.
5. ✅ `predict_p_win` contract (§2.5) — `EntryExitPredictor(bundle).predict_proba(...) -> {p_entry,
   p_exit, p_win}` and `predict_p_win(...) -> float` (last bar of window, `torch.inference_mode`).
   Threshold consumers (Risk Engine, TZ-05) never touch tensors directly.
6. ✅ OB index (bisect) (§2.6) — `TradingDataset.__getitem__` finds blocks via `np.searchsorted`
   over sorted `end_idx` (prefix + `start_bar` filter) instead of a full scan. OB-encoder batching
   in forward — ⬜ remains (profile on real volume; current test volume is small).
7. ✅ Package identity `ai`, doc cleanup (§2.7) — package `ai`, relative test imports, Lark legend
   removed (see TZ-01 §2.7).
8. ✅ Tests (§2.8) — `ai/src/tests/`: label look-ahead (`test_features`, `test_label_generation`),
   losses (`test_losses`), split-leak + self-training isolation (`test_stabilization`),
   bundle/predict (`test_bundle`). Total: **68 passed**.
9. ✅ logging instead of print (§2.9) — `training.py` and `contracts.py` use a module `logger`
   (warning for contracts, info for training progress; 'Batch validation passed.' → debug).
10. ✅ **Configuration (YAML)** — `configs/ai.yaml` + `ai/src/config.py`
    (sections risk/model/training/compute, `seed`, defaults = previous hardcodes, config threaded
    via args, no global state; `risk_kwargs()` maps RiskConfig to the label generator).
11. **Compute backends** — `ai/src/device.py`.
    - Training: **CUDA or CPU only** (non-CUDA training dropped); `train_backend: auto | cuda | cpu`,
      wrong backend = ValueError.
    - Inference: `infer_backend: auto | cuda | cpu | onnx_directml | vulkan`;
      `vulkan` is an alias for `onnx_directml` (DX12: AMD/Intel/NVIDIA).
    - Pure Vulkan and GGUF **rejected**: there is no Vulkan backward-pass; GGUF is a llama.cpp
      format for specific LLM architectures, a custom EntryExitTransformer is not covered by a
      converter; rewriting forward in GGML is disproportionate.
    - Non-CUDA inference path: `export_onnx()` → ONNX Runtime DirectML EP; optional `[gpu]`
      group (torch-directml, onnxruntime-directml, Windows).
    - A smoke test for non-CUDA backends is mandatory (risk of silent NaN).

## 4. Acceptance criteria

- ✅ ai test set green: **68 passed, 3 skipped** (skips — platform-dependent DirectML without `[gpu]`).
- ✅ `quick_train` end-to-end on synthetic data (`test_quickstart`).
- ⬜ predict_p_win < 5 ms on window 128 (CPU) — measure on first run on real hardware; a
  correctness test invariant exists.
- ✅ label and split invariants green.
- ✅ Rerun with the same seed → identical metrics (`set_seed` in config; `test_config` checks seed).

## 5. Checklist reconciliation

| Checklist item | Status | Where |
|---|---|---|
| item 5: time-only validation (no shuffle) | ✅ | `_split_train_val`, window-overlap test |
| item 5: TP/SL from data ≤ t (prior ATR) | ✅ (was) | `features.compute_tp_sl` |
| item 6: reproducibility (seed, config) | ✅ | `configs/ai.yaml`, `set_seed` |
| item 4: max-drawdown metric in validation | ⬜ | TZ-04 (backtest), not ai |
| item 1: online ZigZag / fixed OB | ⬜ | TZ-04 §4.3 |
| item 2: execution open[t+1], commissions | ✅ (was) | `features.py` (moved to the TZ-04 engine) |
| item 3: RF/XGBoost baselines | ⬜ | TZ-04 §4.6 |
the pattern-head is declared but "unused in training" — implement data or remove from docs.