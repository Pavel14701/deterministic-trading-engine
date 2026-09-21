# panel — champion-stack panel experiments (HISTORICAL) + diagnostics

All `HISTORICAL` modules ran on the pre-fix simulator / panel whose
labels booked gap-through-stop entries as ~+1R wins (8–12% of rows) and
wrong-side stops as instant wins (8.7%). The chain produced the
+0.44R / +466R headline numbers that were later RETIRED (STATUS,
D.13g). The protocol designs (WF folds, embargo, nested CV, admission
semantics) remain the repo standard; the artifacts do not.

Run: `uv run python -m experiments.panel.<name> [args]`

| module | question it answered (historical verdict) |
|---|---|
| `walk_forward_ab` | per-asset (A) vs multi-asset LGBM (B) under WF 8×56d — B won 6/8 → champion head. On the REBUILT panel (2026-09-21 re-run): B wins 4/8, both arms negative — consistent with the dead-pool verdict |
| `matrix_2x2` | 2×2 data×model decomposition — TRF rejected causally (D−B bootstrap [−0.507,−0.188]) |
| `nested_cv` | hyperparameter selection bias — measured −2.2% discount |
| `admission_policies` | FCFS vs REPLACE-low slot admission — REPLACE-low +28% EV (mechanism insight survives; the EV level does not) |
| `portfolio` | block-bootstrap DD on the WF trade stream — daily aggregation ~30% optimistic |
| `robustness` | block-length sensitivity, event-vs-daily DD, capped-out trade distribution |
| `execution_costs` | pessimistic cost model: slip ×2, gap G×ATR — the pess/optimistic spread convention |
| `maker_entry` | maker-or-skip vs market — REJECTED: total adverse selection, lift −0.41R (conclusion stands) |
| `cost_cap` | cost-aware row cap + AVSL-off — cap is a DD lever, not free EV |
| `ranker_only` | free ranker gate vs rule-table gate |
| `ranking_baselines` | cost-aware stop-rule ranking head (LambdaRank over 11-rule panel) |
| `feature_family` | DSL feature family A/B vs hand-built features |
| `joint_rank` | joint (stop rule × TP target) ranking — REJECTED |
| `adaptive_tp` | MFE/MAE head → adaptive TP: regime-TP rejected (noise); adaptive TP = same EV, ~½ DD |
| `ablation` / `ablation_diag` | OB/AVSL detector ablation — **detectors carry no edge, geometry did** (and the geometry edge was the artifact) |
| `regime_diag` | causal regime trigger for weak folds — none found; recorded to stop a wrong stop-floor |

## Current-panel diagnostics

| module | verdict | what it decided |
|---|---|---|
| `ensemble_ab` | ⚫ | LGBM+CatBoost+logreg ensemble grid on the REBUILT panel: whole grid negative ("dead pool") → keep LightGBM-only; ensemble package stays as infra |
