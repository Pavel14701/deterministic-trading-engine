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
| `nested_cv` | hyperparameter selection bias — era −2.2%. Re-run: **KILL criterion triggered** — discount −27.9% (threshold −15%); single-split selection carries order-10-30% bias, nested selection mandatory for near-zero results |
| `admission_policies` | FCFS vs REPLACE-low slot admission — REPLACE-low +28% EV. Re-run: **MAGNITUDE** — gain +12% with CI [+0.9R,−0.5R] crossing zero; mechanism direction holds in point estimate only |
| `portfolio` | block-bootstrap DD on the WF trade stream. Re-run: **SURVIVES** — honest DD on record: p95 maxDD 16.1R, p99 19.9R (@1R=1%); kill-switch K=4R/P=14d → p95 5.5R |
| `robustness` | block-length sensitivity, event-vs-daily DD. Re-run: **MAGNITUDE** — daily bias +0% (era "~30%" was phantom-inflated); block stability holds (10d adequate) |
| `execution_costs` | pessimistic cost model: slip ×2, gap G×ATR — the pess/optimistic spread convention *(convention, not re-run)* |
| `maker_entry` | maker-or-skip vs market — REJECTED: total adverse selection, lift −0.41R (conclusion stands; structural, not re-run) |
| `cost_cap` | cost-aware row cap + AVSL-off — cap is a DD lever, not free EV. Re-run: **SURVIVES** — DD 24.1R→14.8R at cap=0.15, EV stays negative |
| `ranker_only` | free ranker gate vs rule-table gate. Re-run: **SURVIVES** — mixed table/free (no consistent winner), every cell negative |
| `ranking_baselines` | cost-aware stop-rule ranking head (LambdaRank). Re-run: **no flip to positive** — fresh ranker beats era stop-head (−0.113 vs −0.273 pess; dd 3.8R vs 12.4R), rk+gate −0.056R/dd 0.7R, all arms negative |
| `feature_family` | DSL feature family A/B vs hand-built. Re-run: **SURVIVES** — no family positive (best combo −0.038, halves DD); features don't create edge |
| `joint_rank` | joint (stop rule × TP target) ranking — REJECTED. Re-run: **SURVIVES** — test pess −0.091 (n=50); gated −0.609 (n=3) |
| `adaptive_tp` | MFE/MAE head → adaptive TP: regime-TP rejected (noise); adaptive TP = same EV, ~½ DD. Re-run: **SURVIVES vacuously** — panel yields ≤2 trades per cell; no edge either way |
| `ablation` / `ablation_diag` | OB/AVSL detector ablation — **detectors carry no edge, geometry did** (and the geometry edge was the artifact). Re-run: **SURVIVES, strengthened** — OB +0.021R / AVSL +0.043R contribution, 90% of A reproduced detector-free; placebo beats real detectors 8/8 folds |
| `regime_diag` | causal regime trigger for weak folds — none found; recorded to stop a wrong stop-floor *(already negative, not re-run)* |

**Re-run program (2026-09-21): ALL 16 panel-era modules audited on the
rebuilt panel (phase 1: 8 group-A, phase 2: 6 group-B + 2 structural
exclusions). Verdict flips to positive: 0. ONE kill criterion
triggered: nested_cv selection-bias discount −27.9% (was −2.2%) →
single-split selection is order-10-30% optimistic; nested selection
mandatory for near-zero results. Panel-era negative verdicts all
stand; positive headline numbers stay retired. Full detail: STATUS.md
"HISTORICAL RE-RUN" phases 1-2.**

## Current-panel diagnostics

| module | verdict | what it decided |
|---|---|---|
| `ensemble_ab` | ⚫ | LGBM+CatBoost+logreg ensemble grid on the REBUILT panel: whole grid negative ("dead pool") → keep LightGBM-only; ensemble package stays as infra |
