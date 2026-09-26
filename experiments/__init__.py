"""Reproducible experiments, organized by HYPOTHESIS FAMILY.

Family tracks (entry-signal families and market families):
  avsl/      -- AVSL-cross family (screen -> confirm -> risk-overlay
                -> mirror/channel/portfolio layer)
  donchian/  -- Donchian breakout family (closed)
  ob/        -- Order-Block retest family (closed)
  zscore/    -- z-score entry family (closed)
  ttf/       -- taker-flow divergence (closed)
  carry/     -- funding-carry family
  options/   -- Deribit vol-carry family (closed)
  fx/        -- FX transfer family (closed)
  stocks/    -- equities transfer family (closed)
Infrastructure (no hypothesis, no gates):
  infra/loaders/   -- data loaders (Binance / OKX / Yahoo)
  infra/sharadar/  -- Sharadar fetcher (ready, blocked on key)
  infra/live/      -- live-scale parity / pilot tracking
Debug & diagnostics (no gates, never a verdict):
  debug/     -- one-off checks, calibration, postmortems

Each module is runnable: ``python -m experiments.<track>.<name>``.
Results land in ``runs/``; verdicts are logged in ``docs/JOURNAL.md``
(see STATUS.md snapshot). Repo root: ``from experiments import REPO``.
"""

from experiments._repo import REPO  # noqa: F401
