# panel — champion-stack panel experiments (HISTORICAL) + diagnostics

> All positive numbers in this group are INVALIDATED by the D.13g
> simulator artifact. The only live-defensible result in the repo is
> `carry/funding_carry_v3` (PASS per pre-reg, but decaying — see the
> root index).

All `HISTORICAL` modules ran on the pre-fix simulator / panel whose
labels booked gap-through-stop entries as ~+1R wins (8–12% of rows) and
wrong-side stops as instant wins (8.7%). The chain produced the
+0.44R / +466R headline numbers that were later RETIRED (STATUS,
D.13g). The protocol designs (WF folds, embargo, nested CV, admission
semantics) remain the repo standard; the artifacts do not.

Run: `uv run python -m experiments.panel.<name> [args]`

| module | question it answered (historical verdict → 2026-09-21 re-run on rebuilt panel) |
|---|---|
| `walk_forward_ab` | per-asset (A) vs multi-asset LGBM (B) under WF 8×56d — B won 6/8 → champion head. Re-run: B wins 4/8, both arms negative — retired |
| `matrix_2x2` | 2×2 data×model decomposition — TRF rejected causally (D−B [−0.507,−0.188]). Re-run: **SURVIVES**, D−B [−0.445,+0.002] — still no TRF effect; B−A ns; nothing positive |
| `nested_cv` | hyperparameter selection bias — measured −2.2% discount *(procedure, not re-run)* |
| `admission_policies` | FCFS vs REPLACE-low slot admission — REPLACE-low +28% EV. Re-run: **MAGNITUDE** — gain +12% with CI [+0.9R,−0.5R] crossing zero; mechanism direction holds in point estimate only |
| `portfolio` | block-bootstrap DD on the WF trade stream — daily aggregation ~30% optimistic *(procedure, not re-run)* |
| `robustness` | block-length sensitivity, event-vs-daily DD, capped-out trade distribution *(procedure, not re-run)* |
| `execution_costs` | pessimistic cost model: slip ×2, gap G×ATR — the pess/optimistic spread convention *(convention, not re-run)* |
| `maker_entry` | maker-or-skip vs market — REJECTED: total adverse selection, lift −0.41R (conclusion stands; structural, not re-run) |
| `cost_cap` | cost-aware row cap + AVSL-off — cap is a DD lever, not free EV. Re-run: **SURVIVES** — DD 24.1R→14.8R at cap=0.15, EV stays negative |
| `ranker_only` | free ranker gate vs rule-table gate *(procedure, not re-run)* |
| `ranking_baselines` | cost-aware stop-rule ranking head (LambdaRank over 11-rule panel) *(procedure, not re-run)* |
| `feature_family` | DSL feature family A/B vs hand-built features *(procedure, not re-run)* |
| `joint_rank` | joint (stop rule × TP target) ranking — REJECTED. Re-run: **SURVIVES** — test pess −0.091 (n=50); gated −0.609 (n=3) |
| `adaptive_tp` | MFE/MAE head → adaptive TP: regime-TP rejected (noise); adaptive TP = same EV, ~½ DD. Re-run: **SURVIVES vacuously** — panel yields ≤2 trades per cell; no edge either way |
| `ablation` / `ablation_diag` | OB/AVSL detector ablation — **detectors carry no edge, geometry did** (and the geometry edge was the artifact). Re-run: **SURVIVES, strengthened** — OB +0.021R / AVSL +0.043R contribution, 90% of A reproduced detector-free; placebo beats real detectors 8/8 folds |
| `regime_diag` | causal regime trigger for weak folds — none found; recorded to stop a wrong stop-floor *(already negative, not re-run)* |

**Re-run program (2026-09-21): 8 group-A modules audited on the rebuilt
panel — 0 verdict flips, kill criterion (≥6 flips) not triggered. The
panel-era negative verdicts all stand; the positive headline numbers
stay retired. Full detail: STATUS.md "HISTORICAL RE-RUN".**

## Current-panel diagnostics

| module | verdict | what it decided |
|---|---|---|
| `ensemble_ab` | ⚫ | LGBM+CatBoost+logreg ensemble grid on the REBUILT panel: whole grid negative ("dead pool") → keep LightGBM-only; ensemble package stays as infra |
