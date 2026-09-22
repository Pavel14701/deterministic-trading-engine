# ob — Order-Block rework pipeline (D.15, ta pipeline) — all CLOSED

Run: `uv run python -m experiments.ob.<name> [args]`

| module | verdict | what it decided |
|---|---|---|
| `ob_raw_ev` | ⚫ | first look-ahead-clean OB test (online ZigZag, confirm-guarded): raw EV ≤ 0 net of costs |
| `ob_wf_ev` | ⚫ | OB pipeline EV under the WF fold calendar: no tradable edge |
| `ob_delay_curve` | ⚫ | retest-delay buckets: no bucket passes train criterion |
| `ob_ldgrid` | ⚫ | L×delay EV surface incoherent |
| `ob_lookback13` | ⚫ | lookback ablation: 13 vs 30 — no lift → **OB-retest on 15m CLOSED per prereg** |
| `ob_lookback_grid` | ⚫ | L grid × TP grid: no coherent cell |
| `ob_holdout_assets` | ⚫ | working point does not transfer to holdout assets |
| `ob_struct_diagnostics` | ⚫ (info) | bars/ATR, AR(1) half-life diagnostics: impulse structure too short-lived at 15m |

## Research presets (BACKLOG, STATUS 2026-09-22)

Live presets (1m..1d) are quality-first: the "4h" preset yields
only 9-34 blocks/asset on the 4H grid -- useless for EV statistics.
A separate family of RESEARCH presets (R1-R5, looser filters,
200-2000 blocks/asset, detector logic untouched, repaint-free and
determinism non-negotiable) is planned in STATUS
("OB ENGINEERING PLAN"). Acceptance criteria are frozen there.
NEVER use a research preset for live trading or a live preset for
EV research.
