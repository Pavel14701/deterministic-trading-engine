# Experiments catalog

Every experiment is a runnable module, grouped by track:

```bash
uv run python -m experiments.<track>.<name> [args]
```

| track | contents | README |
|---|---|---|
| `loaders/` | data loaders & dataset builders (OKX / Yahoo / Binance) | [loaders/README.md](loaders/README.md) |
| `carry/` | funding-carry chain + barrier probability | [carry/README.md](carry/README.md) |
| `avsl/` | AVSL / Donchian entry-signal family | [avsl/README.md](avsl/README.md) |
| `ob/` | Order-Block rework pipeline | [ob/README.md](ob/README.md) |
| `panel/` | champion-stack panel experiments (historical) + current-panel diagnostics | [panel/README.md](panel/README.md) |

Results land in `runs/` (JSON/log artifacts); every verdict is recorded
in **STATUS.md** with a pre-registration where applicable. STATUS.md is
the evidence trail; the per-track READMEs are the INDEX. Negative
results are kept on purpose - a closed track stays closed per its
pre-registration (no re-tuning, revival requires a NEW prereg).

Status legend (used in all sub-READMEs):

- ACTIVE - track alive; params frozen by prereg, result pending
- INFRA - data loader / builder, no gates, safe to re-run (all caches
  are resumable page-caches)
- SURVIVOR - passed its gates; the one live trading track
- CLOSED - gate(s) failed per prereg; verdict final
- HISTORICAL - ran before the D.13g simulator fix (gap-through-stop
  artifact); its positive numbers are INVALIDATED. Kept for protocol
  archaeology. Do not quote artifacts from this group.

Repo-root path for any module: `from experiments import REPO`.

## Conventions for new experiments

1. **Pre-register before running**: rules, params, gates, eval windows -
   into STATUS.md (see TTF v1 / ProSP v2 for the format). A parameter
   touched after the first run kills the track.
2. **Gates on PRIMARY windows only**; report fold-by-fold decay - it is
   the crowding signal, not a bug.
3. **Pessimistic sim first** (SL-first, slip, gap-through-stop scratch),
   gross EV before costs, composition sanity (hold, win/exit mix)
   before trusting any headline number (lesson: D.13g).
4. Negative results stay: module kept, verdict in STATUS.md, row added
   to the track README with a CLOSED mark.
5. New module goes into an existing track folder (or opens a new one
   with its own README); keep this index row-linked.
