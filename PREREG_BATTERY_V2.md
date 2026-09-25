# PREREG: BATTERY V2 -- cross-sectional honesty patch

Status: FROZEN 2026-09-25 (commit recorded in STATUS.md) before
any v2 code run.  Scope: ADDITIVE read-outs + two new gates on
top of frozen battery v1.  Does NOT modify v1 gates, formulas,
seeds; does NOT touch engine/passed/*; does NOT re-open AVSL.

## Rationale
AVSL family failed at the system level: correlated beta passed
pos_assets>=7, and NW Sharpe / time-block bootstrap could not see
it.  v1 conflates "signal does not work" with "we cannot measure
the signal".  v2 separates them.

## V1 (kept untouched)
nw_sharpe (per-bar stream, NW_LAGS=500), portfolio_dd, net EV,
time-block bootstrap CI (B=1000, block=500, seed 11), segments
PRIMARY 2/3 + F3, gates Sharpe>=1.0 / DD<=0.25 / EV>=0.10R /
boot_ci[0]>0 / pos_assets>=7.  TRUE global grid.

## New read-outs (printed every run, NOT gated)
R1 ENB per segment: eigenvalues of corr(X) where X = aligned
   asset x bar matrix of per-bar sized accrual returns;
   ENB = (sum lam)^2 / sum(lam^2).  Bands: >=3.0 trust Sharpe;
   1.5-3.0 borderline (discount Sharpe, DD optimistic); <1.5
   effectively one bet.
R2 Concurrency profile: n_open[t]; p50/p95/max, %bars>=5,
   per-year p95.
R3 Standalone leg metrics (long/short x segment): sharpe_nw, dd,
   ev, n, avg hold, ex_top20_ev, top20_share.
R4 Exit attribution: per leg x segment, count and R-sum by exit
   reason (when the ledger provides reasons).
R5 Orthogonalized EV: per leg x segment, OLS of per-trade net R
   on factor F; EV of residual + t-stat; NaN if n_leg < 50.
   Factor (frozen, no tuning): F_long(t) = log(BTC close[t] /
   BTC close[t - 180]) (30-day trailing BTC return, 4H bars);
   F_short = -F_long.
R6 Regime balance per segment: calendar span and fraction of
   bars with BTC below 1D SMA200; flags "balanced" (<10pp diff)
   or "skewed" (>30pp).
R7 Cross-sectional block bootstrap CI: resample bar-index blocks
   (500, circular, B=1000, seed 11) of the asset x bar matrix,
   all assets moved together; CI of the mean of the summed
   stream.  Printed next to the v1 time-block CI; divergence =
   v1 CI too narrow (flag in STATUS).  Not gated in v2.

## New gates (joint with v1: gates_pass_v2 = gates_pass_v1 AND
## G-ENB AND G-CONC)
G-ENB: ENB >= 2.0 per segment (deliberately loose; catches the
   AVSL-class failure at ENB ~1.2-1.5).
G-CONC: p95(n_open) <= 6 per segment.

## Verdict semantics
FAIL           : v1 gates fail (v1 semantics, family closed).
FAIL-CORR      : v1 passes, G-ENB or G-CONC fails -- signal not
                 distinguishable from beta on this universe;
                 closes the UNIVERSE, not the hypothesis; next
                 work changes universe or factor structure.
PASS           : candidate for promotion.

## Calibration (pre-registered, one shot, before first family)
1. avsl_cross_s1  -- expect: passes v1, likely fails G-ENB.
2. avsl_trailing_s1 -- expect: passes v1, borderline G-ENB.
3. Synthetic null -- 10 iid random-walk assets, same entry rule
   + trailing exit + S1 sizing: expect fails v1 and v2.
If (1)/(2) PASS G-ENB -> threshold too loose, ONE adjustment
allowed before v2 is frozen for families.  If (1)/(2) fail both
new gates and (3) fails v1 -> v2 calibrated as-is.

## Scope discipline
No sizing changes, no portfolio vol-targeting, no correlation-
aware allocation, no regime filters.  v2 is measurement, not
strategy.  No v2 parameter changes after the first family run
without a new dated prereg.
