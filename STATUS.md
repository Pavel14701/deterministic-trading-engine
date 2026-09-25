# STATUS


#### ProSP v2 RUN DECLARATION (2026-09-24): the frozen prereg
#### (2026-09-21) is being EXECUTED.  Prereg-silent details
#### declared BEFORE the run (conventions, not parameters):
#### (a) "funding z(3d)" = 3-day mean of DAILY funding, mapped
####     to 1H bars of the NEXT day (no lookahead), z-scored on
####     a trailing 90d window (ddof=1);
#### (b) "tbv_share delta(24)" = share(t) - share(t-24);
#### (c) z(336) features via polars rolling ddof=1, min 336
####     completed bars (NaN before warmup);
#### (d) universe = the 30 carry names mapped to Binance symbols
####     with cached 1H klines at run time (PEPE absent, TON->
####     GRAM alias; GRAM contributes only post-2026-07 rows);
#### (e) P-G1 constant baseline = TEST-fold class rate (the
####     strongest constant baseline, conservative for the model);
#### (f) portfolio rows: each asset's LAST completed 1H bar of
####     day d predicts day d+1 return close(d+1)/close(d)-1;
####     legs = top/bottom 3 by calibrated P(up)-P(dn); cost
####     0.15% per leg membership change vs the prior day;
#### (g) P-G2 tercile spread uses the same 0.15% cost on
####     tercile membership changes.
#### ProSP v2 RUN A ABORT (2026-09-24): implementation bugs, no
#### verdict recorded.  (1) min-row gate was applied PER-ASSET
#### (barrier-v1 copy-paste) instead of pooled as the prereg
#### requires -- funding cache covers only the last ~40% of
#### history, so folds 0-5 were wrongly skipped per-asset;
#### (2) the portfolio stream included zero-days without
#### predictions, diluting P-G3.  Gates untouched; code fixed
#### and committed; RUN B below is the one-shot execution.
####

#### AVSR-MIRROR PRE-REG (2026-09-24, frozen BEFORE run; NEW dated
#### prereg under P-2; the frozen AVSL module is NOT modified).
#### Hypothesis: AVSR(70,345) = mirror resistance line,
#### SMA(high + price_v(high) - DeV) on the identical AVS base
#### (VPC/VPR/VM/VPCI/DeV from close/volume, stand_div 2.0).
#### Entry semantics IDENTICAL to AVSL (cross above = long,
#### cross below = short; breakout semantics, NOT reverse).
#### This is a mirror transfer of a LATENT family, one-shot:
#### protocol byte-identical to the frozen AVSL battery --
####   universe 10 Binance majors, 4H resample, WARMUP 400,
####   stop max(|close-line|, 2*ATR14), TP 5R PRIMARY,
####   HORIZON 500, fee 10bp RT, PRIMARY = first 2/3 of the
####   global 4H grid, F3 = rest;
####   configs S1..S4 exactly as the AVSL overlay prereg
####   (b6005ca): S1 vol-target clip(0.20/rv100, 0.25, 2.0),
####   S2 ATR-pct regime x1/x0.5/x0.25 (80/90), S3 caps
####   (max 5 open, expo < 3x), S4 = S1xS2 with S3 caps;
####   gates per config per segment G1' Sh_NW >= 1.0, G2' DD
####   <= 25%, G3' net EV >= 0.10R, G4' >= 7/10 assets positive,
####   G5' block bootstrap (block 500, B 1000) CI excludes 0.
#### Verdict rule (frozen): risk-first S3 > S4 > S1 > S2 among
#### full passers; 0/4 pass => AVSR mirror CLOSED (the AVSL
#### LATENT verdict is unaffected; a mirror FAIL is evidence
#### the S1 edge is geometry+low-line specific, not symmetric).
#### DECLARED PRIOR (low, per analysis): 70% same-as-AVSL-noise
#### band, 20% worse (high noisier than low), 10% better;
#### family budget: counts as attempt #2 of the AVS family
#### (N=3 per P-2).  Runner: experiments/avsr/risk_overlay_mirror.py.
####
#### AVSR-MIRROR RESULT (2026-09-24; one-shot @ 594aa40).
#### Verdict: **CLOSED -- 0/4 configs pass** (per the frozen
#### risk-first rule; the AVSL LATENT verdict is unaffected).
####   S1: PRIMARY 5/5 PASS (Sh +1.55, DD 17%, EV +0.18R,
####       8/10 assets, CI [+0.0068,+0.0275]) -- numerically
####       almost identical to frozen AVSL PRIMARY (1.50,
####       22%, +0.17R); F3 FAIL (Sh +0.52, DD 32%, EV +0.08R,
####       CI includes 0).  AVSR has NO F3 leg, unlike AVSL
####       (F3 Sh 2.84).
####   S2: PRIMARY DD 45% F; S3/S4: mixed single-segment noise,
####       no config passes both segments.
#### Read-out: the mirror reproduces the AVSL PRIMARY surface
#### (shared geometry + shared AVS base) but carries none of
#### the F3 regime edge -- consistent with the declared prior
#### (same-as-AVSL band, weaker side; high is noisier than
#### low).  Family budget: AVS attempt #2 of 3 consumed; one
#### attempt remains (channel AVSL+AVSR is the declared
#### backlog candidate and would be attempt #3).  Frozen AVSL
#### module untouched throughout.
####
#### AVS-CHANNEL PRE-REG (2026-09-24, frozen BEFORE run; AVS
#### family attempt #3 of 3 -- a FAIL here closes the family
#### FINALLY per the confirm-gate convention).  Hypothesis:
#### AVSL+AVSR form a volatility channel; the edge is in the
#### BREAKOUT OUT OF THE CHANNEL (regime change), not in either
#### line alone.  New signal, distinct claim from the AVSL-cross
#### latent (bounce/support) and the AVSR mirror (resistance).
#### Frozen spec:
####   lines      AVSL(70,345) + AVSR(70,345), stand_div 2.0,
####              both from the frozen formulas; entry bar
####              requires BOTH lines finite.
####   trigger    transition into "outside": prev 4H bar close
####              inside [AVSL, AVSR] AND current close outside
####              -- close > AVSR => LONG; close < AVSL => SHORT.
####              No re-entry while outside (state, not level).
####   entry      close[t] (identical bookkeeping to the frozen
####              cross tracks).
####   stop       risk = max(distance to the OPPOSITE line at t,
####              2*ATR14[t]) -- long: max(cp-AVSL, 2ATR);
####              short: max(AVSR-cp, 2ATR).  Stop-first
####              within-bar, conservative (identical to frozen).
####   exit       TP 5R PRIMARY ONLY (the {3,5,8} scan is not
####              re-opened; confirm showed narrow TPs dead and
####              one claim per prereg), HORIZON 500, fee 10bp RT.
####   universe   the same 10 Binance majors, 4H resample.
####   segments   PRIMARY = first 2/3 of the global 4H grid, F3.
####   sizing     the identical S1..S4 battery (S1 vol-target
####              clip(0.20/rv100,0.25,2.0); S2 ATR-pct x1/x0.5/
####              x0.25 at 80/90; S3 caps 5-open/3x-expo;
####              S4 = S1xS2 with caps).
####   gates      per config per segment, identical: G1' Sh_NW
####              >= 1.0; G2' DD <= 25%; G3' net EV >= 0.10R;
####              G4' >= 7/10 assets positive; G5' block boot
####              (500, B=1000) CI excludes 0.
####   verdict    risk-first S3 > S4 > S1 > S2 among full
####              passers; 0/4 => CHANNEL CLOSED and the AVS
####              family is closed finally (budget exhausted).
#### DECLARED PRIOR: 25-35% (user).  Run:
#### experiments/avsr/channel_breakout.py.
####
#### AVS-CHANNEL RESULT (2026-09-24; one-shot @ 6414aba).
#### Verdict: **PASS -- S1 selected** (risk-first; passers=[S1]).
#### 1547 trades (782 long / 765 short), grid n=15269.
####   S1: PRIMARY 5/5 PASS (Sh +1.13, DD 24%, EV +0.22R,
####       7/10 assets, CI [+0.0010,+0.0176]); F3 5/5 PASS
####       (Sh +4.96, DD 10%, EV +0.39R, 7/10, CI
####       [+0.0120,+0.0306]).
####   S2 FAIL (PRIMARY DD 51%, CI incl 0); S3 FAIL (F3 5/10
####   assets, CI [-0.0006,..] incl 0); S4 FAIL (F3 6/10 assets).
#### P-2 classification: LATENT -- full battery passed one-shot
#### with low declared prior, but (i) the edge is regime-
#### concentrated like AVSL (F3 >> PRIMARY), (ii) R here is the
#### channel width (wider stops than the cross tracks), so the
#### +0.22/+0.39R EV is NOT comparable to AVSL's +0.17R without
#### an execution-layer translation, (iii) inherited caveats:
#### survivorship universe, taker-fill assumption, 2023-24
#### holdout question inherited from the family decomposition.
#### Family budget: 3/3 attempts used, family REMAINS OPEN via
#### the channel (a PASS does not consume the budget into
#### closure).  Next layer if promoted: execution prereg
#### (honest fill/cost layer, the P4-EX pattern) before any
#### capital.  Frozen modules untouched throughout.
####
#### CORRELATION CHECK (2026-09-24, diagnostic, no gates):
#### AVSL-cross S1 vs AVS-channel S1 per-bar accrual streams
#### (identical S1 sizing + bookkeeping, global 4H grid
#### n=15269; runner experiments/avsr/corr_check.py).
####   Pearson: PRIMARY +0.627, F3 +0.622, FULL +0.625
####   Spearman: PRIMARY +0.408, F3 +0.433, FULL +0.425
####   50/50 combined: sum +257.1R, maxDD 26.7R vs 34.1R
####   (AVSL alone) / 38.0R (channel alone) -- diversification
####   benefit is real but the tracks are NOT independent
####   (moderate correlation, shared geometry/base).
####
#### PORTFOLIO-LAYER PRE-REG (2026-09-24, frozen BEFORE run;
#### latent-revival at the portfolio layer, authorized by P-2;
#### prior 60-70%).  Claim: the 50/50 combination of the two
#### AVS LATENT tracks (AVSL-cross S1, channel S1) is
#### deployable-grade on the DD dimension because trigger
#### diversification structurally reduces DD below either
#### track alone (measured diagnostic: 26.7R vs 34.1/38.0R).
#### FROZEN SPEC:
####   inputs    the two S1 accrual streams exactly as built
####             in corr_check (frozen signals, frozen S1
####             sizing, identical bookkeeping, same grid);
####             combination = 0.5*AVSL + 0.5*channel (no
####             re-fitting, no weights search).
####   cap       PF DD cap = 30% BOTH segments -- calibrated
####             EXTERNALLY (industry-norm ceiling for
####             directional crypto), declared before this
####             run; NOT derived from the measured 26.7R and
####             NOT a relaxation of a failed gate (no gate
####             failed at 25% for these two S1 configs).
####   gates     PF-G1 Sharpe_NW >= 1.0 both segments;
####             PF-G2 event DD <= 30% both segments
####             (cumprod of 1% x stream, as the tracks);
####             PF-G3 block bootstrap (500, B=1000) CI of
####             mean bar R excludes 0 both segments;
####             PF-G4 honest layer: EVERY trailing 12m window
####             (2190 x 4H bars) has positive cumulative R
####             on the full grid (the P4 12m pattern; no
####             lookahead, trailing only).
####   verdict   PASS iff all four gates pass; else CLOSED
####             (portfolio layer), tracks stay LATENT.
####   honesty   recorded: the 30% cap is chosen in full
####             knowledge of the 26.7R diagnostic; if PF-G2
####             passes only because of the cap choice, the
####             read-out must say so explicitly.
#### Next layer on PASS: execution prereg (P4-EX honest
#### fill/cost pattern) before any capital.  Run:
#### experiments/avsr/portfolio_layer.py.
####
#### PORTFOLIO-LAYER RESULT (2026-09-24; one-shot @ 65f43bc).
#### Verdict: **FAIL -- portfolio layer CLOSED, tracks stay
#### LATENT** (per the frozen rule; PF-G4 honest layer).
####   PF-G1: PRIMARY Sh +1.39P; F3 Sh +9150.48 "P" --
####       DEGENERATE READ-OUT: the frozen NW factor
####       sqrt(1+2*sum(rhos)) with lags=500 blows up when
####       the 500-lag autocorrelation sum approaches -0.5
####       (accrual-stream sawtooth); the F3 Sharpe number is
####       not interpretable.  Methodology caveat recorded for
####       all future preregs using NW lags >= 500 (no
####       retroactive change to closed batteries).
####   PF-G2: DD 20.9% PRIMARY / 23.4% F3 vs cap 30% -- PASS
####       (honesty note: cap was declared with knowledge of
####       the 26.7R diagnostic; it did NOT bind).
####   PF-G3: CI [+0.0013,+0.0221] / [+0.0107,+0.0456] -- PASS.
####   PF-G4: FAIL -- 75 of 13080 trailing 12m windows
####       negative; ALL window-starts fall in 2022-07-31..
####       2022-08-13; worst window 2022-08-09..2023-08-09 at
####       -8.7R.  The bear-year + 2023 dead zone (the family's
####       known holdout weakness, decomposition 2026-09-22)
####       survives diversification: trigger diversification
####       fixes DD, NOT the regime hole.
#### READ-OUT: the 50/50 portfolio is statistically alive
#### (G1-G3 pass) but fails the deployability honest layer on
#### a persistent negative year.  Any revival must address the
#### 2022-23 regime hole explicitly (regime gate calibrated
#### out-of-sample, or capital-schedule that tolerates a
#### -9R year) -- that would be a NEW family attempt beyond
#### the 3/3 budget, principal-level decision.  Execution
#### layer not reached; no capital.
####
#### FAMILY-DIVERSIFICATION CHECK (2026-09-24, diagnostic, no
#### gates; runner experiments/diagnostics/avs_ob_portfolio_check.py):
#### AVSL-cross S1 (A) + AVS-channel S1 (B) + OB E8b S1 (C),
#### all on the TRUE global grid n=15269.
####   1. P&L correlation: A<->C +0.18/+0.11 (PRIMARY/F3),
####      B<->C +0.20/+0.21 -- LOW, real family diversification
####      at the daily-P&L level (the optimistic-scenario
####      condition HELD).
####   2. DD-window overlap: top-5 episode overlap A<->C =100%,
####      A<->B =80%, B<->C =80% -- REFUTED the key hope.  C's
####      largest DD (29.3%, 2022-09 -> 2023-08) sits exactly on
####      the AVS 2022-23 regime hole; C's #2 (2025-03..10)
####      overlaps A's 2024-08..2025-03 episode.  Low daily
####      correlation does NOT prevent tail co-drawdowns.
####   3. Combined: DD improves (A+C 21.3%, B+C 22.6%,
####      33/33/33 19.3% vs 28.9/31.6/29.3% individual), but
####      PF-G4 12m negative windows WORSEN with OB:
####      A+B 75 -> A+C 294 -> B+C 421 -> 33/33/33 345
####      (individual: A 193, B 778, C 457).  OB's own worst
####      12m stretch IS 2022-23.
#### CONCLUSION (per the pre-declared decision rule): the
#### pessimistic branch -- rank-one regime exposure is
#### STRUCTURAL across all three families; portfolio
#### construction fixes DD, not the 2022-23 hole.  Combined
#### portfolio prereg NOT written (would fail PF-G4 by more
#### than the AVS-only layer).  Any deployability path must
#### address the common regime hole first (out-of-sample
#### regime gate, capital schedule tolerating a -9R year, or
#### a genuinely different universe).  Otherwise: vol carry /
#### market switch per the standing options.
####
#### CACHED-UNIVERSE SVD CHECK (2026-09-24, diagnostic, no gates;
#### runner experiments/diagnostics/svd_cached_universe.py).
#### Scope ACTUAL: 29 unique tickers post-dedupe (Binance 30
#### preferred, OKX 34 fully overlapping; 1 dropped for history
#### < 2y) -- NOT the hypothesized 70-80: the cache union is
#### the carry/Binance universe plus OKX mirrors.  Common 4H
#### grid: 5606 buckets = 2.56 years (latest-listing bound,
#### ~2024-03..2026-09; the 2022 bear is NOT in this window --
#### but the 2022 co-crash is already measured on the 10
#### majors via the DD-overlap analyses above).
####   PC1 share:          66.8%   (prior was 55-65% -- WORSE)
####   Eigenvalues > MP:   1       (literally one factor)
####   MP lambda+:         1.149
####   Mean pairwise corr: +0.650  (prior 0.5-0.6 -- worse)
####   Tail corr worst 5%: +0.650  (n=281 days; LOWER than the
####       0.75-0.85 prior, but equal to the normal-day corr --
####       no tail diversification to unlock in this window)
####   Most decoupled: TRX 0.49, TON 0.67, BCH 0.72 (TRX is
####       the only sub-0.6 idiosyncratic name).
#### VERDICT (thresholds frozen in the runner): **RANK-ONE
#### CONFIRMED**.  Decision per the pre-declared rule: do NOT
#### spend 1-2 days downloading the rest of Binance symbols;
#### universe expansion on crypto is closed structurally
#### (one factor in normal days, no tail diversification to
#### unlock).  Focus: protective puts (Deribit 3-5d) / vol
#### carry / market switch (FX).  A 40-50 asset PC1-filtered
#### subset cannot help: only ONE eigenvalue clears MP.
####
#### AVSL-EXTENDED PRE-REG (2026-09-24, frozen BEFORE run; NEW
#### question, distinct from the closed SVD correlation check:
#### does the FROZEN AVSL-cross S1 signal carry its edge on the
#### 29-asset cached universe and a 2024-2026 window?).
#### UNIVERSE (frozen at pre-reg, exactly the 29 post-dedupe
#### tickers from the SVD run, all Binance cache, >= 2y 1H):
####   AAVE ADA APT ARB ATOM AVAX BCH BNB BTC DOGE DOT ETC ETH
####   FIL HBAR INJ LINK LTC NEAR OP SEI SOL SUI TIA TON TRX WIF
####   XLM XRP
#### SIGNAL/SIZING (frozen, imported read-only from
#### engine.passed.avsl_cross_s1): AVSL(70,345) cross entry,
#### stop max(|close-line|, 2*ATR14), TP 5R, HORIZON 500,
#### stop-first, fee 10bp RT, WARMUP 400, S1 size
#### clip(0.20/rv100, 0.25, 2.0).
#### GRID/SEGMENTS (declared): TRUE global grid = the common
#### 2.56y window starting 2024-03-01 (latest listing TON);
#### only trades ENTERING inside the window count; e1 clamped
#### to grid end; stream = per-bar accrual (identical formula);
#### PRIMARY = first 2/3, F3 = last 1/3.  DECLARED: NOT the
#### frozen 6y window; results not comparable to the 10-major
#### verdict; this is a separate universe/window test.
#### GATES (identical thresholds, both segments):
####   G1' Sharpe_NW >= 1.0 (raw Sharpe reported alongside;
####       known NW-factor degeneracy caveat -- if NW is
####       degenerate, the raw number governs the read-out
####       narrative but the GATE stays NW as frozen);
####   G2' event DD <= 25%;
####   G3' net EV >= 0.10R;
####   G4' >= 21/29 assets positive (ceil of 70%);
####   G5' block bootstrap (block 500, B=1000, seed 11) CI
####       excludes 0.
####   PF-G4: trailing 12m negative-window COUNT REPORTED, NOT
####       gated (declared deviation: ~315 windows only).
#### KILL: any gate FAIL in either segment -> closed.
#### PRIOR: 30% optimistic (EV +0.15..0.20R, DD 18-22%),
#### 50% realistic (EV +0.10..0.15R, DD 24-28%, LATENT),
#### 20% pessimistic (EV < 0.10R, signal weaker on non-majors).
#### RUNNER: experiments/avsl/avsl_extended_universe.py.
####
#### AVSL-EXTENDED VERDICT (2026-09-24, one-shot, log
#### runs/avsl_extended_universe.log, code frozen @ 59e199b).
#### 3823 trades inside the window (PRIMARY 2669 / F3 1154).
####   G1' Sharpe_NW: +5011 / +5862 (degenerate NW factor, as
####       pre-declared; raw Sharpe +5.01 / +5.86 governs the
####       narrative) -> PASS both.
####   G3' net EV:    +0.125R / +0.161R -> PASS both, and in
####       the REALISTIC prior branch (+0.10..0.15): the edge
####       DOES carry to non-majors, weaker than the 10-major
####       +0.17/+0.33, F3 roughly halved.
####   G2' event DD:  59.8% / 50.3% -> FAIL both (gate 25%).
####       Consistent with the frozen FORBIDDEN finding
####       (clustered entries carry the edge; caps destroyed
####       it): 29 rank-one-correlated assets make the clusters
####       ~3x bigger -> DD triples (22% -> 60%).  The SVD
####       rank-one result PREDICTED this: no diversification
####       to offset the added concurrent exposure.
####   G4' assets positive: 20/29 / 19/29 -> FAIL (>= 21).
####       Marginal, but frozen thresholds do not bend.
####   G5' bootstrap CI (block 500, seed 11): [-0.004,+0.069] /
####       [-0.038,+0.118] -> includes 0, FAIL both.  Power
####       note: a 2.56y grid with 500-bar blocks has only ~7
####       independent blocks per segment -- the gate is
####       power-limited here (declared window caveat), but it
####       stays FAIL as frozen.
####   PF-G4 read-out (NOT gated): 0/3417 trailing 12m windows
####       negative, worst +19.6R (accrual-stream construction,
####       positive-biased by design; informational only).
#### KILL RULE APPLIED: 6 gate FAILs -> **AVSL-EXTENDED
#### CLOSED**.  The frozen signal's per-trade edge survives on
#### non-majors (G1'/G3'), but portfolio-level gates fail:
#### expansion adds clustered rank-one exposure, not
#### diversification -- SVD predicted the DD, the run measured
#### it.  This does NOT touch the 10-major PASS (different
#### window/universe, own prereg intact).  Deployment remains
#### the 10-major frozen config; any 29-asset redesign
#### (de-lever/caps) is FORBIDDEN territory (S3/S4) and would
#### close the passed module for a new dated prereg.
####
#### AVSL-15M PRE-REG (2026-09-24, frozen BEFORE run; intraday
#### branch test: does the 4H-frozen AVSL wide-TP geometry
#### transfer to 15m WITH the fee wall accounted?).
#### STANDING RULE HONORED (STATUS 2026-09-21 15m post-mortem,
#### "gross edge first"): two-stage prereg.  Stage A gates GROSS
#### edge on taken trades; Stage B (only if A passes) runs the
#### S1/gates battery.
#### DATA (declared): OKX 15m cache (Binance 15m not cached --
#### declared venue deviation), 10 frozen majors, all present,
#### density 1.000; common window ~2.84y from 2023-11-14
#### (100k-row cache cap trims starts; BTC has 103k).
#### SIGNAL (identical to frozen 4H module, TF-adapted):
#### AVSL(70,345, stand_div 2.0) close-cross, normal arm both
#### sides, WARMUP 400 bars, stop max(|close-line|, 2*ATR14),
#### HORIZON 500 bars (5.2d > slow 3.6d -- fixes prior 15m
#### breakage (c); breakage (a) line-hugging 7.6 crosses/day
#### NOT fixable by prereg -- this is the test), fee 10bp RT.
#### TP: GATED = 5R only.  3R/8R = read-out, cannot rescue a
#### FAIL (anti-multiple-testing; STATUS 922 prior).
#### STAGE A (KILL gate, standing rule): per-asset GROSS EV > 0
#### AND gross WR > break-even (1/6 at 5R) on >= 5/10 assets in
#### BOTH segments; matched random-entry null (seed 11, 2000
#### entries/asset, same geometry) reported -- if signal gross
#### ~= null gross, no conditional drift.  FAIL -> intraday
#### AVSL branch CLOSED, Stage B not run.
#### STAGE B: S1 formula clip(0.20/rv100,0.25,2.0) with
#### annualization adapted to 15m (ANN 35,040 -- declared TF
#### adaptation; window/target/cap identical); TRUE-grid
#### portfolio stream; PRIMARY 2/3 / F3 1/3; gates G1'-G5'
#### identical thresholds (NW_LAGS 500, BOOT_BLOCK 500 bars,
#### seed 11; G4' 7/10); PF-G4 12m reported NOT gated; KILL any
#### FAIL.  Fee sensitivity read-out: net EV at 5bp/2bp RT
#### (maker-ish), informational.
#### HONEST PRIOR: 10-15% PASS (below proposer's 25-35%):
#### fee_r ~0.3-0.5R at 15m vs 0.05-0.08R at 4H; line
#### structurally hugging at 15m (STATUS 938-940); E2: 1H
#### already failed -- TF lift gradient runs UP toward 4H.
#### RUNNER: experiments/avsl/avsl_15m_wide_tp.py.
####
#### AVSL-15M VERDICT (2026-09-24, one-shot, log
#### runs/avsl_15m_wide_tp.log, code frozen @ f693f1a).
#### ~27.5k crosses taken (line-hugging confirmed: ~7/day, the
#### prior 15m breakage (a) reproduced exactly).
#### STAGE A: formally PASS -- gross EV>0 on 7/10 (PRIMARY) and
#### 6/10 (F3), WR>BE(16.7%) on 8/10 and 7/10.  BUT the matched
#### random-entry null (seed 11, 2000/asset, same geometry) is
#### +0.038R gross: geometry alone is positive at 15m, and the
#### signal mean (+0.053R) clears it by only ~+0.015R of
#### CONDITIONAL drift.  WR sits just above BE (17-21%), not at
#### it -- the wide-TP+2xATR fixes moved WR off break-even,
#### but the drift above the null is thin.
#### STAGE B: FAIL 10/10 gates.  Net EV -0.064R PRIMARY /
#### -0.104R F3 (fee_r 0.07-0.21R swallows the +0.015R drift
#### with 5x margin); Sh_NW -1.08/-2.69; DD 99.4%/99.9%
#### (27k clustered trades, no caps); assets+ 3/10 and 1/10;
#### CI includes 0 both.  FEE SENSITIVITY: at 2bp RT (maker
#### both sides) EV = +0.004R / -0.018R -- NOTHING even
#### fee-free-ish; at 1bp +0.027R / +0.010R.  The fee wall is
#### the binding constraint exactly as pre-declared: the
#### conditional drift (not fees-free gross) is what the 15m
#### AVSL cross does not have.
#### KILL APPLIED: **intraday AVSL branch CLOSED** (both the
#### 5R gate config and by the declared anti-multiple-testing
#### rule any 3R/8R rescue).  Reinforces E5: the AVSL lift is
#### 4H-specific.  For ANY future intraday prereg the bar is
#### now explicit: demonstrated conditional drift over a
#### matched geometry null >= ~0.2R per trade BEFORE fee
#### design matters.  OFI-as-filter (V2) has a DATA GAP: no 1m
#### taker_buy_volume cached (Binance 1h only; OKX raw lacks
#### the column) -- parked, requires a download decision.
#### 5m mean-reversion (V3) parked: needs maker fill model.
####
#### ProSP v2 RESULT (2026-09-24; RUN B, one-shot; runner
#### prosp_v2.py @ da1d2b3).  Verdict: **CLOSED -- SIGNAL-DEAD**
#### (two-layer P-2 verdict: no deployable signal in this
#### family/horizon).  All 16 fits ran; pooled TEST 415 days.
####   P-G1 (kill): FAIL.  Calibrated Brier model 0.19245 vs
####      constant class-rate baseline 0.18563 -- the model is
####      WORSE than the constant on pooled TEST; per-fold wins
####      up 2/8, dn 0/8 (needed >= 5/8).  Flow/positioning
####      features add NEGATIVE information about +-2%/24h tails.
####   P-G2: FAIL.  Tercile net daily EV -0.95bp.
####   P-G3: FAIL.  Portfolio net Sharpe_NW +0.42 (< 1.0).
#### Consistent with barrier v1 (Brier 0.21747 > 0.21688) and
#### TTF v1 (flow divergence anti-signal at 1H): probability
#### models on flow features do not beat class-rate baselines
#### out-of-sample.  The ProSP family claim is CLOSED for the
#### declared feature stack; no re-tuning per prereg.  Ledger
#### remains 0 false-positive PASS.  Not retroactive to latents
#### (AVSL S1, E8b OB).


#### P4-EX RESULT (2026-09-24; prereg 75ff2ee, frozen before the
#### run; runner p4_exec.py, one-shot).  Verdict: CLOSED as
#### execution-blocked (EX-G2 fail).  Per the frozen prereg: no
#### re-run, no constant changes; the P4 funding-stream PASS is
#### RECLASSIFIED as an upper bound, not a deployable result.

Numbers under the honest execution model (fill P=0.5, next-day
retry, +20bp taker fallback after misses, +50bp basis allowance
per RT):
- PRIMARY: ann +1.84% (capital-adjusted +0.92% -- BELOW the
  ~4-5% risk-free), Sharpe_NW +1.51 (EX-G1 pass, barely),
  maxDD 2.05% (EX-G3 pass).
- Trailing 12m: ann +0.29%, Sharpe_NW +0.31, CI95
  [-0.93, +2.11] -- EX-G2 FAIL decisively; the recent regime
  does not carry honest costs at all.
- EX-G4 PRIMARY CI95 [+0.23, +3.82] excludes 0 -- PASS.
- Rolling 6m read-out: 698/913 windows positive (76%), worst
  -3.73% -- mostly positive but materially negative windows
  exist.

Reading: the execution layer consumed ~72% of the funding-stream
ann (+6.58% -> +1.84%), and the surviving margin is below the
risk-free benchmark on capital-adjusted terms.  The v3 pattern
repeated one level deeper: majors decayed by crowding, low-caps
die by execution.  The user's declared prior ("realistic live
Sharpe 1.5-3") was correct at its bottom edge.  Survivorship
caveat still applies ON TOP of these numbers.

CONSEQUENCE: P4 is NOT deployable.  The carry family now holds
two funding-stream PASSes (v3 majors, P4 low-caps) that both
fail the honest layer, by different mechanisms (crowding decay
vs execution cost).  The basis-trade feasibility prior is
DOWNGRADED accordingly: it shares the same spot+perp execution
structure, so its gross edge must clear the same ~5%/yr honest
cost stack before it can be considered.  Breadth queue: basis
trade (downgraded prior), market switch (principal decision),
ProSP v2 (prereg open, different family).


#### P4-EX EXECUTION PRE-REG (2026-09-24, frozen BEFORE any run;
#### runner experiments/carry/p4_exec.py).  Question: does P4
#### survive an honest execution model, or is it a funding-stream
#### artifact?  All constants frozen ex ante; NOTHING is fitted.

Model (layered on the same panel/streams as the P4 PASS run):
1. FILL MODEL: each leg-side (perp+spot, entry+exit) fills as
   maker with probability P_FILL=0.5 (i.i.d., uniform, seed=7,
   single frozen RNG sequence).  A missed fill retries the NEXT
   day: entry delay skips the intervening funding; exit delay
   KEEPS the position (funding during delay accrues, honest).
   A miss that eventually fills via taker fallback pays
   SPREAD_HALF_BPS=10 extra per leg-side (half of a frozen 20bp
   low-cap spread assumption; maker fees already inside
   MAKER_RT).
2. BASIS ALLOWANCE: extra BASIS_RT=0.50% cost per completed
   round trip, all round trips (frozen conservative allowance
   for spot-perp basis widening at unwind; declared allowance,
   NOT an estimate -- no spot panel exists for these pairs).
3. CAPITAL READ-OUT (not gated): v3 convention quotes on perp
   notional; the capital-adjusted ann (divide by 2 for the two
   legs' capital) is REPORTED beside it.
4. STABILITY READ-OUT (not gated): rolling 6m ann% windows --
   count positive, worst window.

Gates (frozen; any FAIL -> P4 execution-blocked, the P4 PASS
stands as funding-stream fact):
  EX-G1: net portfolio Sharpe_NW >= 1.0 on PRIMARY
  EX-G2: net portfolio Sharpe_NW >= 0.7 on trailing 12m
  EX-G3: net portfolio maxDD <= 15%
  EX-G4: net ann CI95 (P2 bootstrap) excludes 0 on PRIMARY

Honest prior (declared): the model costs are severe by design
-- expected fill delay ~1d on ~5-10bp/day funding, ~20bp extra
spread drag and 50bp basis allowance per RT.  If EX passes
anyway, P4 is deployable-subject-to-paper-trading; if it fails,
the funding-stream PASS is reclassified as an upper bound and
the track closes without a re-run.

#### P4 RUN DECLARATION (2026-09-24): the frozen P4 prereg
#### (2026-09-21) is being EXECUTED today.  Universe snapshot
#### convention declared BEFORE the pull: "the pull window" =
#### trailing 30 days of daily klines ending at the pull date.
#### Snapshot script experiments/carry/p4_universe.py writes
#### data/p4_universe_<date>.json (rule inputs included); the
#### gate runner experiments/carry/p4_carry.py consumes the
#### snapshot verbatim (v3 rules AS-IS via funding_carry_v3
#### imports; P2 bootstrap 30d/B=10k/seed=7).  No universe or
#### parameter choice follows any P4 look.  Funding fetch
#### reuses funding_carry_v2.binance_daily_funding (cache
#### data/funding_binance/) -- no new fetch infrastructure
#### needed.

# STATUS — what is implemented vs what is needed

Single consolidated summary. Legend: ✅ done · 🔨 in progress / core done · ⬜ not started ·
⬜=spec only. Full per-task detail: `legacy/dev_docs/tz/TZ-00-roadmap.md` (archived).

## 2026-09-21 — data feasibility audit + TTF v1 / ProSP v2 preregs + OI accumulation

LAYOUT: `engine/experiments/` moved to the top-level `experiments/`
package (user directive: scripts laid out in `experiments/`).  Imports
`engine.experiments.*` -> `experiments.*` everywhere (incl.
engine/tests/test_funding_carry_v3.py); ruff per-file-ignores and the
mypy override retargeted; CI lint/type steps now cover `experiments`;
run commands are `python -m experiments.<name>`.  The catalog moved to
`experiments/README.md`.  STATUS.md history above keeps the old paths
on purpose (evidence trail of its time).

LAYOUT-2 (same day): `experiments/` re-grouped into track packages -
`loaders/` (3), `carry/` (4: funding_carry x3 + barrier_prob),
`avsl/` (5), `ob/` (8), `panel/` (18, champion-stack + diagnostics);
each has its own README, `experiments/README.md` is now the index.
Run commands: `python -m experiments.<track>.<name>`.  REPO is now
defined once in `experiments/__init__.py` and imported everywhere
(`from experiments import REPO`) so module paths stay
depth-independent.  Import smoke: all 37 modules OK.

### HISTORICAL RE-RUN PROGRAM (2026-09-21) -- PRE-REGISTRATION

D.13g fix invalidated the 16 panel-era modules (experiments/panel/).
This is an AUDIT of their verdicts on the rebuilt panel -- not
re-tuning.  Frozen before any run:

- Rebuilt panel: data/mtf_dataset/*_1h.parquet (built 2026-09-20,
  post-D.13g builder); raw 1m: data/okx/raw_*_1m.parquet.
- Simulator: current engine.sim (gap-check + wrong-side guard); pess
  labels computed at load time by the fixed code.
- Module params: AS-IS, unchanged.  Module gates: as in the original
  pre-registrations, unchanged.
- wf_trades.parquet / wf_picks.parquet regenerated 2026-09-21 21:48
  (walk_forward_ab re-run: B wins 4/8, both arms negative -- champion
  head stays retired).

Scope, priority order (group A only -- modules whose NUMBERS feed
decisions): matrix_2x2 -> admission_policies -> ablation(+ablation_diag)
-> joint_rank -> adaptive_tp -> cost_cap.  Already done: walk_forward_ab
(above), ensemble_ab (whole grid negative, "dead pool" -- STATUS above).

NOT re-run (group B/C -- procedures or structural conclusions, numbers
not decision-bearing): nested_cv, portfolio, robustness,
execution_costs, maker_entry (adverse-selection conclusion is
panel-independent), ranker_only, ranking_baselines, feature_family,
regime_diag (already negative).

Outcome classes per module: SURVIVES (verdict unchanged) / FLIPS
(PASS<->FAIL -- important, not a bug) / MAGNITUDE (verdict same,
numbers moved).  KILL criterion for the whole protocol: >=6 of 8
flips -> the original panel distorted results so deeply that the
protocol designs themselves are suspect -> full re-audit before any
further panel work.

#### HISTORICAL RE-RUN -- RESULTS (all 8 group-A modules, 2026-09-21)

Flips: 0/8.  KILL criterion NOT triggered -- WF folds, embargo and
admission semantics stand.  All artifacts: runs/rerun_*.log,
runs/{ablation,admission_policies,cost_cap}.json, runs/d8b/.

1. walk_forward_ab  -- MAGNITUDE: B wins 4/8 (was 6/8), both arms
   negative (A pess -0.047 / B -0.038).  Champion head stays retired.
2. ensemble_ab      -- SURVIVES: whole grid negative, "dead pool";
   LightGBM-only stays.
3. matrix_2x2       -- SURVIVES w/ magnitude shift: TRF still adds
   nothing (D-B CI [-0.445, +0.002] -- upper bound at zero; was
   [-0.507, -0.188]).  A -0.006 / B +0.083 (n=35, ns) / C -0.150 /
   D -0.134.  B-A CI [-0.189, +0.385] -- multi-asset LGBM edge is not
   significant.  Nothing positive anywhere.
4. admission_policies -- MAGNITUDE (level): REPLACE-low vs FCFS
   EV-gain CI [+0.9R, -0.5R] (+12% .. -6%) -- was "+28%".  Mechanism
   direction holds in point estimate (REPLACE-low -6.5R > FCFS -7.3R,
   fewer dd), but NOT significant; all arms negative.
5. ablation(+diag)  -- SURVIVES, strengthened: OB contribution
   A-B = +0.021R, AVSL A-C = +0.043R, detector-free stack D -0.063R
   explains 90% of A.  Placebo panels beat the real-detector panel in
   8/8 folds (Bs*/Ds* - A per fold +0.3..+1.4R) -- real detectors are
   noise-or-worse, not merely neutral.  Low-cost half of test rows:
   EV ~0; high-cost half: -0.19..-0.28R.
6. joint_rank       -- SURVIVES: ungated test pess -0.091 (n=50);
   gated test pess -0.609 (n=3).  Joint stop-x-TP ranking stays
   rejected.
7. adaptive_tp      -- SURVIVES (vacuously): rebuilt panel yields
   almost no candidates for this analysis (n<=2 per cell, val n=0).
   No adaptive-TP edge; the old "same EV, half DD" claim is not
   reproducible on the clean panel either way.
8. cost_cap         -- SURVIVES: caps cut DD (A 24.1R -> C|cap=0.15
   14.8R) while EV stays negative (-0.111 -> -0.043) -- cap is a DD
   lever, not free EV, exactly as pre-registered.

Bottom line: the panel-era NEGATIVE verdicts all survive the D.13g
fix; the era's positive headline numbers remain retired.  The dead
pool is confirmed dead.  Panel-era infra is closed for re-runs; new
work goes to the live tracks (carry re-validation, TTF v1, ProSP v2).

### HISTORICAL RE-RUN PHASE 2 -- group B (2026-09-21) -- PRE-REGISTRATION

Six remaining decision-relevant modules (DD metrics, label-dependent
comparisons, the one methodology number).  Same frozen rules as phase
1: rebuilt panel, current engine.sim, params AS-IS, original gates
AS-IS.  This is an audit, not re-tuning.

Scope and expectations (frozen before runs):

- portfolio, robustness  -- DD metrics.  EXPECTATION: DD higher than
  the era numbers (phantom +1R wins depressed DD).  Decision-relevant:
  honest DD drives position sizing / leverage / risk limits.
- ranker_only, ranking_baselines -- gate/ranker comparisons on clean
  labels; flips possible (ranking_baselines is the likeliest flip:
  LambdaRank trained on poisoned labels).  CAVEAT recorded here: the
  ranking_baselines baseline loads the era artifact
  data/mtf_model/stop_head.txt as the "current stop head" -- its PICKS
  are evaluated against clean r_net in replay, but the model itself
  was trained pre-fix; a comparison win/loss is still valid as
  measured, the magnitude is era-contaminated on that arm.
- feature_family -- DSL vs hand-built comparison on clean labels.
- nested_cv -- the hyperparameter-selection discount; era number
  -2.2%.  KILL criterion: if the clean-panel discount is worse than
  -15%, all historical results are over-fitted beyond tolerance and
  the selection methodology needs a re-audit.
- NOT re-run (unchanged from phase 1): execution_costs (convention),
  maker_entry (structural conclusion), regime_diag (already negative).

#### HISTORICAL RE-RUN PHASE 2 -- RESULTS (6/6, 2026-09-21)

Artifacts: runs/rerun_{portfolio,robustness,ranker_only,ranking_baselines,
feature_family,nested_cv}.log + runs/{portfolio,ranker_only,
feature_family,nested_cv,d9b_robustness}.json.

1. portfolio     -- SURVIVES mechanically, honest DD now on record:
   uncapped EV -8.3R / maxDD 9.6R; block-bootstrap tail maxDD
   p50=8.7R p95=16.1R p99=19.9R (@1R=1% eq).  Kill-switch levers work:
   K=4R/P=14d cuts p95 DD to 5.5R (skips 44%).
2. robustness    -- MAGNITUDE: daily-vs-event DD bias = +0% on the
   clean panel (era claim "~30% optimistic" does NOT reproduce --
   era number was inflated by phantom wins).  Block-length stability
   holds: p95 maxDD flat 15.8-16.1R across 10-60d blocks, 10d blocks
   adequate.  Capped-out check: rejected trades same-or-better (pure
   capacity loss, not a selection bug).
3. ranker_only   -- SURVIVES: table vs free gate is mixed (table wins
   A-cells, free wins C-cells), every cell negative (best -0.026R).
   No gate mechanism creates an edge on the clean panel.
4. ranking_baselines -- NO FLIP to positive: fresh LambdaRank beats
   the era stop-head on clean labels (test pess -0.113 vs -0.273;
   dd 3.8R vs 12.4R); rk+gate best cell -0.056R / dd 0.7R -- but ALL
   arms negative.  Era-contamination caveat on the stop-head arm held
   (see prereg): the era model is much worse than its era numbers --
   consistent with poisoned labels having inflated IT, not the ranker.
5. feature_family -- SURVIVES: DSL-zeroed -0.057, DSL-native -0.062,
   spec -0.062, combo -0.038 (dd 26R vs 41-44R).  No family positive;
   combo (DSL+hand) mildly best and halves DD.  Features do not
   create edge; encoding choice is a DD refinement at best.
6. nested_cv     -- **KILL CRITERION TRIGGERED**: selection-bias
   discount -27.9% (threshold -15%; era number -2.2%).  On the clean
   panel the -2.2% figure does NOT reproduce.  Caveat recorded: both
   arms are deeply negative (nested -0.027 n=160 vs fixed -0.038
   n=211), so the discount is estimated on a dead pool with small n
   and is noise-dominated in SIGN; what reproduces is the MAGNITUDE
   class: single-split hyperparameter selection carries order-10-30%
   bias, not ~2%.  CONSEQUENCE (binding): every point-estimate EV from
   a single-config run carries +/-10-30% selection uncertainty.  For
   verdicts negative by wide margins this changes nothing; for any
   future result near zero (e.g. carry v3 F3 +1.45%) nested selection
   is MANDATORY before quoting a number.

Phase 2 totals: 0 flips to positive, 1 kill criterion triggered
(nested_cv discount).  Panel-era closure AMENDED: all 16 modules now
audited; protocol designs (WF folds, embargo, admission, DD
machinery) stand; the single-split selection bias number is the one
era figure that was materially optimistic and is now corrected.

### NEAR-ZERO QUOTING + NEW TRACKS (2026-09-21) -- PRE-REGISTRATIONS

Follow-up to the nested_cv kill: three priorities, pre-registered
before any run.

#### P2 -- carry v3 F3 honest quoting (bootstrap CI)

Params were FROZEN ex ante (prereg efcbd5), no hyperparameter
selection ever happened -- so single-selection bias does not apply.
The near-zero risk for F3 (+1.45% ann) is SAMPLING NOISE.  Frozen
procedure: moving-block bootstrap on the F3 portfolio daily
stream, block=30d, B=10,000, seed=7; report 95% CI on ann% for
F1/F2/F3 and per-asset F3 CIs.  Rule: F3 is quotable as edge only if
the CI excludes 0 AND excludes the risk-free benchmark; otherwise
F3 stays "window closing, not quotable".  Params/streams AS-IS.

#### P3 -- OKX 96d tradability re-validation (STAGED, not run)

Goal: can the frozen v3 rules be traded on OKX at all (fee structure,
funding sign-flip cadence, per-asset coverage over the last ~94d the
OKX API serves)?  Data: engine/infra okx_fetch.fetch_funding_history
(~94d cap, verified).  Design prereg (fee assumptions, gate) must be
written BEFORE the fetch.  Status: staged, do not run until the
design prereg is committed.

#### P4 RESULT (2026-09-24; prereg frozen 2026-09-21; snapshot
#### p4_universe_2026-09-24.json, pull window 30d declared
#### before pull; runner p4_carry.py; v3 rules AS-IS via
#### imports; P2 bootstrap 30d/B=10k/seed=7).  Verdict: PASS,
#### all five gates.

Panel: 1095 days x 30 assets (2023-09-26 .. 2026-09-24).
- G1 PRIMARY portfolio Sharpe_NW = +7.16 (ann +6.58%,
  maxDD 0.23%) >= 1.0 -- PASS
- G2 trailing-12m Sharpe_NW = +10.22 (ann +7.97%) >= 0.7 --
  PASS
- G3 PRIMARY maxDD 0.23% <= 15% -- PASS
- G4 30/30 assets (100% >= 60% required) Sharpe_NW >= 0 with
  active >= 60d -- PASS
- G5 bootstrap ann CI95: PRIMARY [+5.40, +8.10], 12m
  [+6.82, +9.77] -- both exclude 0 AND the ~4-5% risk-free
  benchmark -- PASS

DECLARED CAVEATS (alter nothing in the frozen verdict, bound
the forward expectation):
1. SURVIVORSHIP: the frozen universe rule selects on TODAY's
   exchangeInfo (TRADING status + current-volume top-30 among
   age>=180d).  Perps that had high volume in 2023-2024 but
   delisted before the pull are structurally absent -- the
   backtest cannot see failed low-caps.  The ann +6.58% is an
   estimate on survivors; forward expectation is lower by an
   unmeasurable margin.
2. EXECUTION: MAKER_RT 0.2% assumes maker fills on low-cap
   perps AND the spot legs; low-cap books are thinner and
   wider than the majors the assumption was priced on.
3. Funding magnitude on low-caps is fatter-tailed than majors;
   hold-until-flip can hold through violent funding swings.

STATUS: first PASS of the breadth pivot.  The track is
deployable per the frozen gate.  Scaling decision (small live
pilot vs paper) is principal-level, same bucket as the AVSL
live-restart decision; live ops remain paused.  Breadth queue
unchanged: basis trade next-feasibility, market switch after.

#### P4 -- low-cap carry (NEW hypothesis, no era contamination)

Hypothesis: funding-carry crowding is concentrated in large-cap
perps; low-cap perps carry higher uncrowded funding with similar
flip dynamics, so the v3 rule set retains positive net carry there
even in the F3 regime.  Pre-registered from scratch (no selection):

- Universe (rule-based, frozen at first pull): Binance USDT-M perps
  NOT in the current 29-asset UNIVERSE, listing age >= 180d at pull
  date, median daily quote volume over the pull window >= $5M,
  top 30 by that volume.  No manual adds/drops, ever.
- Params: v3 rules AS-IS (DEAD_ZONE, MAKER_RT, trailing signal,
  hold-until-flip).  No tuning.  No seed variations.
- Evaluation: same fold logic anchored at pull date -- PRIMARY =
  full available history pooled; confirmation = trailing 12 months.
  Gate (frozen): portfolio Sharpe_NW >= 1.0 on PRIMARY and >= 0.7 on
  the trailing 12m, portfolio maxDD <= 15%, >= 60% of universe
  assets with Sharpe_NW >= 0 and active >= 60d.  Block-bootstrap CI
  (P2 procedure) on PRIMARY and trailing-12m ann% must exclude 0.
- Kill: if PRIMARY gate fails, track closed, no re-universe, no
  re-params (revival = NEW prereg, new universe snapshot date).

#### P2 -- RESULTS (2026-09-21)

Moving-block bootstrap (30d, B=10k, seed=7) on the frozen v3 portfolio
stream:

- F1 (2023-09..2024-08): ann +13.54%, CI95 [+8.19, +22.51] -- quotable
- F2 (2024-09..2025-08): ann +3.75%, CI95 [+0.92, +7.62] -- quotable
- F3 (2025-09..2026-09): ann +1.45%, CI95 [+0.52, +2.22] --
  excludes 0 (statistically positive) but the UPPER bound is below
  the risk-free rate (~4-5%).  Per the frozen rule (must exclude 0
  AND the risk-free benchmark) F3 is NOT quotable as tradable edge:
  the "window closing" verdict is confirmed with an honest interval.

F3 per-asset CIs: 3 of 29 assets quotably positive -- APT +14.2
[+2.0, +31.4], FIL +8.7 [+4.1, +15.8], WIF +5.7 [+1.5, +11.6]; the
rest of the universe spans deeply negative (ETC -2.7, ARB -2.2,
OP -2.1).  Motivating observation for P4 (recorded post hoc, does
not alter the frozen P4 universe rule): the F3-positive names sit
outside the mega-cap head of the universe.

### Z-SCORE STRATEGIES -- PRE-REGISTRATION (2026-09-21) -- FROZEN

Four z-score signal families on Binance 1H.  Discipline: THIS block
is committed before the runner exists; touching any parameter after
the first run kills the track (revival = NEW prereg).

Data / universe (frozen): Binance 1H klines
(data/binance/kl_*USDT_1h.parquet), full history .. 2026-09-21.
Universe = the 30 carry-UNIVERSE majors; EVALUATED = those with
cached 1H klines at freeze time = 29/30 (PEPEUSDT klines absent --
excluded by data availability, not performance).

Indicators (frozen): z-score via ta zscore_ind(window, ddof=1,
use_talib=False); ATR(24) via ta atr_ind(use_talib=False); ADX(14)
via ta adx_ind (HYB-1 only).

Implementations (frozen rules):
- MR-1 mean reversion, window 336: z <= -2 -> long; z >= +2 -> short;
  exit |z| <= 0; opposite extreme flips.
- MOM-1 z-momentum, window 168: z crosses above +1.5 -> long; crosses
  below -1.5 -> short; exit on crossing back through 0.
- XSEC-1 cross-sectional, window 336: every 168 bars rank the panel
  z; long bottom 20% (most oversold), short top 20%, weights 1/n per
  side; < 10 valid assets at rebalance -> flat until next.
- HYB-1 regime hybrid, window 336, ADX(14): ADX < 20 -> MR rules
  (entry +/-2, exit |z| <= 0.5); ADX > 25 -> momentum rules (entry
  |z| crossing 1.0, exit through 0); ADX in [20, 25] -> hold.

Event simulation (frozen): entry at NEXT bar open after the signal
bar (no lookahead); one open event trade per asset -- entry events
overlapping an open trade are skipped (cursor at exit).  SL/TP from
ATR24 at the signal bar: MR-1 2.0/2.0; MOM-1 3.0/3.0; HYB-1 2.5/2.5.
R = engine.sim.sim PESSIMISTIC return: the validated taker model
(COMM 10bp/side x2 + GEN_SLIP 5bp + gap 25% ATR + x2 entry/exit slip)
IS the frozen "taker x2 = ~0.2% RT + pessimism stack"; NO additional
cost subtraction (double-count guard).  Max hold = engine cap 48
bars (the sketch's 72 would require touching the validated engine --
frozen deviation).  MOM-1 fixed TP substitutes the sketch's
chandelier (trailing not in the validated engine -- frozen deviation).

Stream basis (frozen, for G1/G2): hourly portfolio stream
r_t = mean_j pos_{t-1,j} * ret_{t,j} - 8bp * turnover (ret = hourly
log-return); XSEC-1 uses its rebalance weights in place of pos.
Sharpe_NW (lags 5) annualised x sqrt(24*365).

Folds (frozen): split on the common calendar grid at 2/3 of its
range: PRIMARY = first 2/3, F3 (confirmation) = last 1/3.  Gates are
evaluated on PRIMARY ONLY; F3 is looked at after the verdict.

Gates (frozen):
- G1: stream Sharpe_NW >= 1.0 on >= 50% of evaluated assets
  (>= 15 of 29; the sketch's 5/10 ratio).
- G2: portfolio stream Sharpe_NW >= 1.0.
- G3: event-basis maxDD <= 25%: PRIMARY trades pooled, sorted by
  entry time, equity = cumprod(1 + 0.01 * r_pess).  XSEC-1 (no
  per-trade events): stream equity DD <= 25% (frozen substitution).
- G4: mean r_opt > 0 on PRIMARY (gross-of-pessimism pre-condition).
  XSEC-1: mean gross stream return (pre-cost) > 0.
Kill: any of G1-G4 FAIL -> track closed.  No re-params, no filters
(RSI/OB/funding), no universe/TF changes, no combinations before
each strategy is judged alone.

Reported, not gated: win rate, n trades, F1+F2 vs F3 decay,
cross-strategy stream correlation.

Expectation on record (from the sketch, not a gate): MR-1 ~20%,
MOM-1 ~15%, XSEC-1 ~25%, HYB-1 ~20% pass probability; EV near zero
after costs is the base case for the directional pair.

#### Z-SCORE TRACK -- RESULTS (2026-09-21): KILL, ALL FOUR FAIL

Single run, no tuning, per the frozen prereg (commit d25cad9).
29/30 assets, grid 61001 bars, PRIMARY = first 2/3 .. 2024-05-27,
F3 = last 1/3.  Gates evaluated on PRIMARY only; F3 shown after.

- MR-1:  n=2307  WR 46.1%  ev_net -0.312R  eventDD 99.9%
         G1 0/29  G2 -2.05  F3 -2.17              -> FAIL (all of G1-G4)
- MOM-1: n=5584  WR 53.0%  ev_net -0.057R  eventDD 98.2%
         G1 2/29  G2 -1.04  F3 -3.83              -> FAIL (G4 gross
         +0.012R was the only near-pass; net of the pessimism stack
         it is negative)
- XSEC-1: G1 1/29  G2 -1.56  streamDD 0.4% (only gate passed)
         G4 gross mean -1e-5 (strictly non-positive)  F3 -2.52
                                                          -> FAIL
- HYB-1: n=6650  WR 50.1%  ev_net -0.153R  eventDD 100%
         G1 0/29  G2 -2.59  F3 -5.35              -> FAIL (worst;
         the regime filter added nothing over its components)

KILL CRITERION TRIGGERED on every strategy: the z-score track is
CLOSED on crypto 1H majors.  No re-params, no filters, no universe
expansion; revival only via a NEW prereg with a genuinely different
hypothesis class.  Cross-strategy PRIMARY stream correlations
(reported): MR-1 x MOM-1 -0.75, HYB-1 anti-correlated with both
(-0.85 / +0.76 -- it is just their regime sandwich), XSEC-1
orthogonal (+0.10 / -0.03) -- the "different class" bet did not help:
even orthogonal XSEC-1 has zero gross edge after ranking noise.

Conclusion per the track plan: z-score as a signal is dead on
crypto 1H majors, consistent with the panel-era finding that
single-name price-derived signals do not survive the taker cost
stack.  Attention returns to TTF v1 / ProSP v2 and the carry
priorities (P3 OKX 96d, P4 low-cap).

#### Z-SCORE POST-MORTEM: MFE/MAE ON TAKEN TRADES (2026-09-21)

Diagnostic replays the frozen event path (same cursor, fills, risk
unit) and measures maximal favorable/adverse excursion in R per
taken trade (`experiments/zscore/mfe_mae.py`,
`runs/zscore_mfe.json`).  Decision rule was fixed in advance:
MFE_p75 >= 2R -> exit-RR surface (new prereg); MFE_p75 < 1.5R ->
track closed for good, reason = "no signal", not "bad exit".

PRIMARY, within the actual trade life (the exit the strategy had):

- MOM-1: MFE_p75 = 1.01R, MFE_p95 = 1.50R  -> BELOW 1.5R THRESHOLD
- MR-1:  MFE_p75 = 0.79R, MFE_p95 = 1.30R  (even weaker)
- HYB-1: MFE_p75 = 0.89R, MFE_p95 = 1.50R
F3 quantiles are identical to within +/-0.03R (no fold drift).

VERDICT: the signal never produced movement.  75% of MOM-1 trades
never saw +1R of favorable excursion before the trade ended; the
median trade saw 0.43R.  No exit scheme (TP grid, trailing, RR 2:1)
can capture movement that does not exist: a 2R TP would simply never
fill for 3/4 of trades, and the position would sit until SL or the
hold cap -- which is what the -0.057R net EV already priced in.

Caveat recorded against the obvious misreading: over a fixed
120-bar horizon MFE_p75 rises to ~3R, but MAE_p75 rises equally
(~2.5R); excursions of that size are what any ATR-scaled random walk
produces at that horizon, and the favorable/adverse asymmetry is
~1.1x -- noise.  Large 120-bar MFE is NOT evidence of capturable
edge, and chasing it would reopen exactly the "smart exit" path the
kill rule forbids.

FINAL: z-score track CLOSED with cause established: no post-entry
drift on 1H majors from z-score entries.  CORRECTION (2026-09-21,
audit): AVSL/Donchian are NOT z-family and were not "muted" by this
post-mortem -- AVSL is an anchored-VWAP line cross and both families
were closed independently by their own pre-registered runs long
before (experiments/avsl/README.md: all 5 modules dead; Donchian 4H
test 2/6, 1H/34 sweep recov 16/34 < 17; quattro G3 2/6, PF 1.05).
The z-score kill is a third independent confirmation of the same
theme: single-name price-derived entries on crypto majors carry no
post-cost edge.  Next: TTF v1 run (prereg in STATUS), P4 low-cap
carry fetch_funding.

#### AVSL PRICE-CROSS "RR-PROFILE" AUDIT (2026-09-21): ILLUSION, 0/10

Hypothesis checked (from the existing avsl_price_cross_atr.log, no
new run): does a trend-following RR profile (tight stop = 1xATR(14),
wide TP 3/5/8R, horizon 192) rescue the AVSL price-cross entry, the
way it was hoped it might rescue z-score and Donchian?

Answer: no, and the reason is structural.

1. CONSISTENCY 0/10: across all 10 assets x 2 arms x 3 TPs, not one
   cell has net > 0 on BOTH train and test.  The single train-plus
   (AVAX, 8R, net +0.119, n=1634) flips to -0.334 on test.  The
   pre-fixed decision rule ("0-3/10 -> beta, close") fires at zero.
2. WR SITS AT BREAK-EVEN AT EVERY RR: 25.5% at TP=3R (BE 25%),
   ~17% at 5R (BE 16.7%), ~12% at 8R (BE 11.1%).  A tight-stop /
   wide-TP profile does not create edge, it rescales zero: WR at
   break-even for 3 different RRs is direct evidence of no
   conditional post-entry drift.  Same conclusion as the z-score
   MFE post-mortem (MFE_p75 = 1.01R), measured independently.
3. MULTIPLE TESTING: 120 cells; best cell ~1.6 sigma vs expected
   max ~2.6 sigma -- not significant even before correction.
4. COSTS: 10bp round trip over a 1xATR(14) 15m stop is 0.15-0.5R --
   would eat any plausible gross; gross is not there anyway.

CONSEQUENCE FOR THE "RR-INSIGHT": the RR profile changes the SHAPE
of the P&L distribution, not its mean.  Re-running dead entries with
different stop/TP geometry is not a new hypothesis class.  Any
future directional prereg must show gross edge first (WR > break-even
or MFE_p75 >= 2R on taken trades), before any exit/RR design.
AVSL family stays closed; z-score stays closed; Donchian stays
closed.  Next: TTF v1 (prereg exists, runner missing), carry P3/P4.

#### AVSL CROSS HIGH-TF -- PRE-REGISTRATION (2026-09-21, FROZEN BEFORE RUN)

Hypothesis (new, not a re-param of any closed track): the prior
AVSL price-cross tests were structurally broken at 15m -- AVSL(70,345)
hugs price there (7.6 crosses/day vs a 3.6-day slow line = noise),
stop 1xATR made fee_r ~0.2-0.5R, horizon 192 < slow length.  At TFs
where the line is structural the same entry may carry gross edge.

Setup (frozen):
- Universe: BTC, AVAX, BNB, DOGE, ETH, LINK, LTC, NEAR, SOL, XRP
  (same 10).  Data: Binance 1H klines (6-7y); 4H = local resample
  of the same 1H.  Exactly two TFs: 1H and 4H.  No other TF.
- Entry: close crosses AVSL(70,345) (NaN-safe path, donor mult 2.0).
  Arm: NORMAL ONLY (long on up-cross, short on down-cross).  No
  reverse arm, no filters, no slope alignment.
- Stop: max(|close - line|, 2*ATR14) at the entry bar (structural
  with a volatility floor).  TP {3,5,8}R, horizon 500 bars, MTM
  exit, conservative within-bar (stop wins ties), entry at close of
  the cross bar.  Fee 10bp round trip.  Overlapping trades allowed
  (every cross, no cursor) -- per-asset EV readout, same as prior
  AVSL scripts.  WARMUP 400 bars.
- Segments: train = first 2/3 of each asset's bars, test = last 1/3.

Gates (PASS requires ALL; verdict per TF independently, no pooling):
- G1 consistency: net EV > 0 on >= 5/10 assets in train AND >= 5/10
  in test, at the same TP.  3 TPs are pre-registered; a pass at one
  TP only is reported as WEAK (needs confirm), not a go.
- G2 gross-edge-first: pooled WR at TP=3R > 30% (break-even 25%)
  within each segment, over trades with n >= 30 per asset.
- G3 cost sanity: median fee_r <= 0.10R per segment.
- Min-n: an asset with < 30 trades in a segment counts as
  not-positive for G1 in that segment.

Kill: any gate FAIL in a TF closes the AVSL-cross track for that TF;
FAIL in both TFs closes the entry family for good (no third TF, no
stop variants, no filters, no universe change).  A full pass goes to
a separate confirmation prereg, not to production.

#### AVSL CROSS HIGH-TF -- RESULT (2026-09-21): FAIL PER PREREG, CLOSED

runs/avsl_cross_tf.log.  VERDICT per the frozen gates: 1H FAIL,
4H FAIL -> family CLOSED for good.  Gate detail:

- 1H: G2 kills it -- pooled WR3R 25.4% train / 28.6% test vs need
  >30% (BE 25%).  Gross edge ~zero, same pattern as every prior
  price-derived track.
- 4H: G1 passes everywhere (train 8/10, 10/10, 9/10; test 7/10,
  7/10, 9/10 -- incl. 10/10 net>0 at TP=5R train), G3 passes (fees
  0.02R, the cost barrier vanishes at 4H as predicted), but G2
  kills it: pooled WR3R 28.4% train / 30.0% test, need >30%.

ANOMALY ON RECORD (not a verdict change): 4H is the FIRST
configuration in the whole project where gross WR is statistically
above break-even in BOTH segments -- train 28.4% vs BE 25% is
~+3.5 sigma at n=1966, test 30.0% vs 25% is ~+3.6 sigma at n=973
(significance overstated somewhat by overlapping-trade correlation).
This is qualitatively different from z-score/AVSL-15m/1H, where WR
sat exactly at break-even.  The 1.6pp miss vs the arbitrary 30%
G2 threshold is the only reason the family closed.

LIMITATIONS: per-asset EV gates only; no portfolio Sharpe_NW / DD
gate was in this prereg; test window overlaps the 2025-26 bull
(long+short both tested, so not pure beta, but long/short split not
examined post-hoc).  Per the kill rule: closed.  Any revival must be
a NEW dated prereg acknowledging this failure and justifying itself
-- default state is CLOSED.

#### AVSL-CROSS 4H -- CONFIRMATION PRE-REGISTRATION (2026-09-21, FROZEN BEFORE RUN)

Status: the screening prereg above FAILED its own gates (G2) and the
family was closed.  This is a NEW dated prereg that re-evaluates the
SAME frozen 4H configuration with the full gate battery the screen
lacked.  Justified only by the recorded anomaly (gross WR ~3.5 sigma
above break-even in both segments, G1 consistency to 10/10); not a
reopening of the old track and not a parameter search.

CONFIG (frozen, identical to the screen -- not one parameter moves):
AVSL(70,345) NaN-safe, 4H (Binance 1H resample), normal arm only,
stop = max(|close-line|, 2*ATR14), TP {3,5,8}R, HORIZON 500 bars,
MTM exit, conservative within-bar, entry at close of cross bar, fee
10bp round trip, overlapping trades allowed, universe = the same 10
assets.  PRIMARY TP = 5R (pre-declared: the screen's only 10/10
cell); 3R/8R recorded, not gated.

GATES (PASS requires ALL; PRIMARY = first 2/3 of the common 4H
calendar, F3 = last 1/3):
- G1 Sharpe_NW >= 1.0 on the portfolio 4H-bar stream (per-unit-risk
  R attributed to the exit bar, summed across assets), NW lags = 500
  (= HORIZON), annualised x sqrt(6*365), on PRIMARY and on F3.
- G2 Event-basis max DD <= 25%: chronological pooled trade sequence
  (entry order), equity = prod(1 + 0.01 * net_R), on PRIMARY.
- G3 Long/short split: BOTH sides net EV > 0 on PRIMARY (TP=5R).
- G4 F3 integrity: pooled net EV > 0 on F3 AND positive in >= 2 of
  its 3 equal sub-windows (stability guard).
- G5 Block bootstrap: per-asset 95% CI of net EV (TP=5R, PRIMARY +
  F3 pooled, B=2000, circular blocks of 25 trades) excludes 0 in
  >= 6/10 assets; AND pooled-per-segment CI excludes 0 in both.
- G6 NW-adjusted significance (the headline test): pooled net EV
  z-score with n_eff = n / (1 + 2*sum rho_1..rho_500) of the
  time-ordered trade sequence, >= 2.0 in BOTH PRIMARY and F3.
  (Naive 3.5 sigma is expected to shrink; the prereg question is
  whether it stays above 2.)

Kill: any FAIL -> AVSL-cross entry family closed FINALLY (no further
preregs, no parameter changes, no universe changes -- final).

#### CONFIRM ADDENDUM: G1'/G2'/G5' OVERLAP-CORRECTED RECOMPUTE (2026-09-21, FROZEN BEFORE RECOMPUTE)

Audit of the confirm implementation found the overlap handled
wrongly in three gates (G2 applied trades sequentially by entry =
non-overlapping assumption; G1 Sharpe on an exit-spike stream; G5
bootstrap block 25 trades << HORIZON 500).  G3/G4/G6 are overlap-
unaffected (G6 already NW-adjusts the trade sequence with lags 500
and PASSED: z 3.31 PRIMARY / 3.85 F3; those stand).

Corrected definitions (frozen before recomputation):
- Per-bar portfolio R stream: every open trade accrues its net R
  linearly over its hold buckets (e0..e1 inclusive); bar stream =
  sum of accruals of all open trades.  Account return per bar =
  1% x bar stream (1% risk per trade slot, concurrent).
- G1' Sharpe_NW >= 1.0 on the accrual stream (not the spike
  stream), NW lags 500, ann x sqrt(6*365), PRIMARY and F3.
- G2' event DD <= 25%: equity = cumprod(1 + 0.01 * stream[bar]),
  PRIMARY only.
- G5' block bootstrap on the bar stream (block = 500 buckets =
  HORIZON, circular, B=1000): 95% CI of the MEAN BAR R excludes 0
  in PRIMARY and in F3.  Per-asset streams: the >=6/10 criterion
  from the original prereg is DROPPED as invalid (per-asset
  standalone significance was never the hypothesis -- the entry is
  traded as one 10-asset portfolio; per-asset counts are recorded
  as diagnostics only).

Verdict rule: the family verdict = G1' G2' G5' (corrected) on top of
the already-passed G3/G4/G6.  Any FAIL -> closed FINAL, same kill as
the main confirm prereg.  No other gate is touched.

#### AVSL-CROSS 4H CONFIRM -- FINAL VERDICT (2026-09-21): CLOSED FINAL, G2' FAIL

runs/avsl_cross_confirm.log + runs/avsl_cross_confirm2.log.
The headline question -- "is the 3.5 sigma real after NW
correction?" -- answered YES:

- G6 PASSED: NW-adjusted z of pooled net EV (lags 500) = +3.31
  PRIMARY / +3.85 F3 (threshold 2.0).  The edge is NOT overlap
  inflation.
- G1'/G1 PASSED: portfolio Sharpe_NW 1.33 PRIMARY / 2.05 F3 on the
  accrual stream (1.24/1.67 on the spike stream -- same verdict).
- G3 PASSED: both sides net-positive on PRIMARY (long +0.265R,
  short +0.078R -- not beta).
- G4 PASSED: F3 pooled +0.335R, all 3/3 sub-windows positive.
- G5' PASSED: block bootstrap (block = HORIZON 500) CI of mean bar
  R excludes 0 in both segments ([+0.0066,+0.0646] /
  [+0.0247,+0.0820]).
- G2' FAILED: portfolio DD (1% risk per trade slot, concurrent,
  mean concurrency 10.9, max 43) = 61.0% PRIMARY (cap 25%), F3
  37.6%.  Verified genuine: trough 2022-07, recovered 2023-01;
  the old sequential construction gave 66.2% -- two independent
  constructions agree, the drawdown is real bear-market
  clustering, not an overlap artifact.

FAMILY CLOSED FINAL per the frozen kill rule.  What dies is the
CONFIGURATION as a tradable strategy at 1%-per-slot sizing: the
signal is statistically real (first in project history), the risk
profile is not survivable at the frozen sizing.  What is on record
for any future re-design (which would be a NEW hypothesis --
sizing/risk-overlay changes are explicitly NOT covered by this
prereg and its kill): a 10-asset AVSL(70,345) 4H cross portfolio
with net EV +0.17R/trade (PRIMARY) / +0.34R (F3), Sharpe_NW 1.3-2.1,
zero per-asset standalone significance (edge exists only in
portfolio aggregation), and bear-year DDs of 30-60% at 1%-slot
risk.  Until such a prereg exists: AVSL family = CLOSED.

#### RISK-OVERLAY TRACK -- PRE-REGISTRATION (2026-09-22, FROZEN BEFORE RUN)

Predecessor: AVSL-cross 4H confirmation (1e0e859) -- CLOSED FINAL by
G2 (DD).  Justification for this NEW track: the signal itself passed
5/6 gates including NW significance; it was killed by position
SIZING, which is a separate layer.  The entry family stays CLOSED;
this track tests sizing rules only, as a new hypothesis.

FROZEN SIGNAL CONFIG (not one parameter moves; any change closes the
track): AVSL(70,345) 4H cross, normal arm, stop =
max(|close-line|, 2*ATR14), TP {3,5,8}R with PRIMARY=5R, HORIZON
500, fee 10bp, universe = the same 10 assets, Binance 1H -> 4H
resample, PRIMARY = first 2/3, F3 = last 1/3.

SIZING HYPOTHESES (all four run in ONE pass; S1-S4 frozen, no new
ones may be added after the run):
- S1 vol-target: size = clip(target_vol / realized_vol, 0.25, 2.0),
  target 20% ann., realized = std(log rets, last 100 4H bars) x
  sqrt(6*365), measured at entry.
- S2 regime: p = ATR14 percentile within last 500 bars at entry;
  size x1.0 (p<=80), x0.5 (80<p<=90), x0.25 (p>90).
- S3 concurrency cap: entry skipped if >=5 trades already open or
  total open exposure >= 3x base size (baseline saw max 43 open).
- S4 = S1 + S2 + S3 combined.

GATES per config (PASS = ALL; kill: any FAIL closes THIS track):
- G1' Sharpe_NW >= 1.0 on the sized accrual stream, PRIMARY and F3
  (lags 500, ann x sqrt(6*365)).
- G2' portfolio DD <= 25% on PRIMARY and F3 (equity =
  cumprod(1 + 0.01 x sized bar stream)).
- G3' net EV >= 0.10R per trade on PRIMARY and F3.
- G4' >= 7/10 assets with positive net EV on PRIMARY and F3.
- G5' block bootstrap (block 500, B 1000) CI of mean bar R excludes
  0 on PRIMARY and F3.

VERDICT RULE (risk-first, not EV-first): if >=1 config passes all
five gates, the selected config is the MOST CONSERVATIVE passer
(preferred order S3 > S4 > S1 > S2), never the most profitable.  If
0 configs pass: the risk profile is fundamental (correlation, not
vol) and the risk-overlay track is CLOSED.  F3 is holdout: no
sizing parameter may be tuned on it (all thresholds above are
pre-fixed).

#### RISK-OVERLAY RESULT (2026-09-22): S1 VOL-TARGET PASSES 5/5 -- TRACK OPEN

runs/risk_overlay.log.  All four frozen configs, one pass, gates as
preregistered:

- S1 vol-target (size = clip(0.20/rv100, 0.25, 2.0), mean size
  0.33): **PASS 5/5**.  Sharpe_NW 1.50 PRIMARY / 2.84 F3 (UP from
  1.33/2.05 unsized -- vol-targeting improved the stream, not just
  scaled it).  DD 22% PRIMARY / 12% F3 (both under the 25% cap;
  F3 was 37.6% unsized).  net EV +0.17R / +0.33R (trade-level EV
  is sizing-invariant).  G4' 9/10 and 7/10 assets positive.
  Bootstrap CIs exclude 0 in both segments.
- S2 ATR-regime: FAIL -- DD 57% / 28%, caps too loose (top-decile
  ATR x0.25 not enough during 2021-22 clusters).
- S3 concurrency cap (max 5 open): FAIL -- DD 21%/21% but it
  DESTROYS the PRIMARY edge: Sharpe 0.22, net EV +0.02R, CI
  includes 0, G4' 5/10.  The clustered entries the cap removes
  carry the edge: keeping only the first 5 of each cluster leaves
  noise.  (Consistency check: S3 sizes are all 1.0 and its numbers
  are bit-identical to the unsized-subset baseline -- implementation
  verified.)
- S4 = S1+S2+S3: FAIL -- same PRIMARY collapse (Sh 0.48, EV +0.07R,
  CI incl. 0) plus DD 14%/7% -- risk control works, edge does not
  survive the cap.

VERDICT (per frozen rule): single passer -> **S1 vol-target
selected** (the S3>S4>S1>S2 conservative tie-break did not bind).
The fundamental finding of the closed confirm track is confirmed
and inverted: the 2022 drawdown was a VOLATILITY-sizing problem,
not a correlation problem -- inverse-vol sizing alone brings the
same trade set inside every frozen risk gate while RAISING
Sharpe_NW to 1.50/2.84.  Concurrency caps are toxic to this signal
and are recorded as forbidden for any successor track.

Next stage per the track: live-scale prereg for S1-sized AVSL-cross
(sizing/venue/monitoring) remains a SEPARATE new prereg; nothing in
the frozen signal config moves.

#### PROMOTION (2026-09-22): S1-sized AVSL-cross -> engine/passed/

The configuration is planted into the core as
`engine/passed/avsl_cross_s1.py` (self-contained, no experiments/
imports; signal vendored via `ta` directly) with full docs in
`engine/passed/README.md` and pure-function unit tests in
`engine/tests/test_passed_avsl_cross_s1.py`.  Self-check
`uv run python -m engine.passed.avsl_cross_s1` reproduces the
frozen verdict numbers bit-for-bit (Sharpe 1.50/2.84, DD 22%/12%,
EV +0.17/+0.33R, CIs identical to runs/risk_overlay.log) ->
FROZEN GATES: PASS 5/5.  The frozen numbers are now a regression
contract: any change to the module that moves them voids the PASS.

#### EDGE-DECOMPOSITION PREREGISTRATION (2026-09-22, FROZEN BEFORE RUNS)

Goal: decompose the confirmed edge (NW-z +3.31/+3.85) into
components -- entry, TF, RR geometry, stop floor, sizing -- to learn
WHAT works, not just that "AVSL 4H S1 works".  Five ablation
experiments, ONE component changed at a time, baseline = the frozen
engine/passed/avsl_cross_s1.py config (untouchable).

META-RULES (binding):
- These are DIAGNOSTIC ablations of a PASSED module.  No outcome
  can un-pass it: its verdict was about the assembled config.
- If any ablation arm beats the frozen config, that observation
  does NOT change the frozen config; using it requires a NEW dated
  prereg (anti cherry-pick).
- Gates frozen before each run; order E1 -> E3 -> E5 -> E2 -> E4;
  no new arms may be added after a run.

E1 -- ENTRY vs RANDOM vs LAGGED (runs first; answers "is there a
signal at all"):
  Arm A: AVSL cross entries, frozen geometry (baseline, 2939 trades).
  Arm B: random-uniform entries, SAME per-asset entry count and SAME
         per-asset long/short ratio as A, drawn from all eligible
         bars [WARMUP, n-2], geometry at the sampled bar, frozen
         seeds 0..99 -> a NULL DISTRIBUTION, not a single draw.
  Arm C: AVSL cross signal delayed DELAY=100 bars (geometry computed
         at the delayed entry bar).
  Gates (PRIMARY and F3 separately):
  - E1a: A net EV > mean(B) + 0.05R
  - E1b: percentile of A net EV within the B distribution >= 95
  Kill (interpretation): E1a fails on either segment -> the AVSL
  entry carries no information beyond the 4H RR geometry; the edge
  is geometry/sizing, and remaining experiments are re-interpreted
  as geometry decomposition.  Arm C reported, not gated: it locates
  the information horizon of the signal.

E3 -- RR ABLATION:  arms = {stop floor on/off} x {wide TP/narrow TP}:
  A: frozen.  B: stop = 1xATR14 (floor off), TP {3,5,8}R.
  C: frozen stop, TP {1R, 1.5R}.  D: frozen stop, TP = reverse cross
  (trailing).  Gates: A > B + 0.05R and A > C + 0.10R on PRIMARY and
  F3 (net EV, fees make narrow stops structurally expensive -- that
  cost is part of the answer).  D reported vs A.  Kill: B ~ A -> the
  wide-stop floor is not critical; C ~ A -> the RR asymmetry is not
  critical and the edge is entry-side.

E5 -- REGIME SLICES (DESCRIPTIVE, no pass/fail): A-trades split by
  ATR percentile (top-20 vs bottom-20), SMA50-slope trend state,
  calendar year buckets (2020/2021/2022-bear/2023-24/2025-26).
  Frozen read-out: per-slice n, net EV, NW-z; verdict vocabulary:
  "universal" (all slices > 0.05R) / "vol-concentrated" / "trend-
  concentrated" / "beta-like" (edge only in long-bull slices).
  Multiple slices = descriptive, explicitly NOT gated.

E2 -- TF ABLATION: 1D resample added; 1H and 15m already failed at
  screen (WR3R ~ break-even, runs/avsl_cross_tf.log) and are
  re-quoted, not re-run.  Gate: 4H net EV > 1D net EV + 0.05R on
  PRIMARY and F3.  Kill: 1D ~ 4H -> the edge is not 4H-specific.

E4 -- SIZING ABLATION on the frozen bar stream:
  A: unsized (1.0).  B: S1 vol-target (frozen).  C: PERMUTED S1
  sizes (shuffle B's sizes across A's trade order, seeds 0..99 --
  breaks the vol-size link, keeps the marginal distribution).
  D: constant 0.33.  Metrics: Sharpe_NW, DD (account stream);
  EV/trade is sizing-invariant and not a gate here.
  Gate: B Sharpe_NW > mean(C) + 0.2 on PRIMARY and F3.
  Kill: B ~ C -> vol-target timing carries no information (pure
  de-lever), record for successor tracks.

#### E1 RESULT (2026-09-22): FAIL on PRIMARY -- EDGE IS MOSTLY GEOMETRY, NOT ENTRY

runs/ablation_entry.log.  Sanity: generic-path arm A reproduced the
core collector (BTC n=270=270; total 2939).  Results per frozen
gates:

- PRIMARY: A EV +0.172R (n=2117, z=+3.33) vs random-geometry mean
  +0.135 +- 0.044R [min -0.002, max +0.291] -> A at the 81st
  percentile; E1a margin (+0.05R) NOT met, E1b (>=95th pct) NOT met.
  FAIL.
- F3: A EV +0.335R vs random +0.168 +- 0.068R -> 100th percentile,
  E1a/E1b PASS.
- Arm C (signal delayed 100 bars): EV +0.227R PRIMARY (n=2079,
  z=+4.40) / +0.225R F3 -- delayed entry BEATS A in PRIMARY and
  loses in F3 (descriptive, not gated).

VERDICT per frozen kill rule: **the AVSL cross entry carries little
to no information beyond the 4H RR geometry in PRIMARY** (the
+0.037R lift over random-mean is within the random spread).  The
dominant component is the GEOMETRY ITSELF: random 4H entries with
the frozen tight-structural-stop + 5R-TP profile average +0.135R
(P) / +0.168R (F3) net -- the RR profile on 4H crypto is the edge
engine; the entry adds a real F3-segment lift (+0.335 vs +0.168,
100th pct).  Consequences, pre-committed by the prereg:

1. E3 (RR ablation) is PROMOTED to the most informative experiment:
   the question is now which geometry component (stop floor, wide
   TP, horizon) generates the +0.135R random-geometry baseline.
2. The passed module keeps its PASS (diagnostic, not a kill of the
   config); no config change is allowed without a new prereg --
   including the tempting "C beats A in PRIMARY" observation, which
   is exactly the kind of post-hoc arm the anti cherry-pick rule
   freezes out.
3. Method takeaway for new tracks: test the RR geometry with RANDOM
   entries FIRST (cheap null baseline); an entry signal must beat
   that null, not zero.

#### E3 AMENDMENT (2026-09-22, BEFORE THE RUN -- extends prereg 68953e0)

- Arm E added (still before any E3 results): stop = 3xATR14 (floor
  off, wider vol stop), TP 5R -- tests stop WIDTH on the other side
  of the frozen 2x.
- Arm C clarified: evaluated at BOTH TP 1R and TP 1.5R (gates apply
  to each).
- Additional read-out (descriptive, frozen procedure): EVERY arm is
  also run on the SAME 100 random-entry draws as E1 (per-asset
  count and side ratio matched, seeds 0..99) -> per-arm random-
  geometry EV.  This decomposes the +0.135R/+0.168R null itself.
  The frozen A>B / A>C gates remain on the AVSL entries; random
  baselines are reported, not gated.

#### E3 RESULT (2026-09-22): NARROW TP KILLS EVERYTHING; STOP FLOOR CRITICAL ONLY ON PRIMARY

runs/ablation_rr.log (+ runs/ablation_rr_d.log appended for arm D,
omitted from the first pass by implementation error, rerun with the
identical frozen procedure).  Sanity: arm A reproduced E1 numbers
(+0.172/+0.335, MATCH).

Arms on AVSL entries (EV PRIMARY / F3, z):
  A  frozen (max(|c-line|,2xATR), 5R)   +0.172 / +0.335   3.33/1.70
  B  1xATR (floor off), 5R              +0.037 / +0.293   0.73/3.36
  C1 frozen stop, TP 1R                 -0.020 / +0.011  -0.90/0.30
  C15 frozen stop, TP 1.5R              +0.022 / +0.020   0.82/0.47
  D  frozen stop, reverse-cross exit    +0.447 / +0.422   3.28/2.99
  E  3xATR (floor off), 5R              +0.175 / +0.456   3.21/1.90

Random-geometry nulls (100 draws, mean+-sd):
  A  +0.135+-0.044 / +0.168+-0.068   (published E1, reused)
  B  -0.013+-0.060 / -0.011+-0.073
  C1 -0.010+-0.022 / -0.012+-0.033
  C15 -0.001+-0.027 / +0.008+-0.039
  D  +0.415+-0.124 / +0.145+-0.069
  E  +0.054+-0.046 / +0.064+-0.067

GATES (frozen): A>B+0.05 and A>C+0.10 both segments.
  A vs B: PASS on PRIMARY, FAIL on F3 (0.335 vs 0.293+0.05).
  A vs C1, A vs C15: PASS everywhere, by an order of magnitude.
Verdict per prereg: **stop floor is critical on PRIMARY only; the
WIDE TP is the absolute requirement -- narrow TP (1R/1.5R) reduces
both segments to ~zero for BOTH the signal and the null.**

Findings, in strength order:
1. TP asymmetry is the engine.  5R TP with any wide-ish stop is the
   only configuration with a nonzero null.  Narrow TP = no edge
   anywhere, even random.  Drift capture, not entry timing.
2. "Not too tight" is what matters for stops, not the line.  B
   (1xATR) collapses PRIMARY to +0.037 (null ~0) -- but on F3 B is
   fine (+0.293).  E (3xATR) matches A on PRIMARY and BEATS it on
   F3 (+0.456).  The frozen 2x/line-floor is not magic; the
   constraint is "wide enough to survive 4H noise".
3. D (reverse-cross trailing) beats the frozen config in BOTH
   segments (+0.447/+0.422 vs +0.172/+0.335), and its PRIMARY
   number is ~all null (+0.415 of +0.447).  Per the anti
   cherry-pick rule this does NOT change the passed module; a
   trailing variant requires a NEW prereg.
4. Entry lift over the matched null (F3): A +0.167, E +0.392, D
   +0.277 -- the AVSL entry's information shows up on the holdout
   across geometries, strongest with the wide stops.

Method takeaway for all successor tracks: the null is not one
number -- every geometry has its own null, and "signal vs null"
must be computed per geometry.

#### E5 AMENDMENT (2026-09-22, BEFORE THE RUN -- extends prereg 68953e0)

E5 stays DESCRIPTIVE (no gates).  Read-out extended BEFORE the run:
alongside the frozen A-trade slices (ATR pct top-20 vs bottom-20;
SMA50-slope up/down/range; year buckets <=2020 / 2021 / 2022 /
2023-24 / >=2025), the SAME slices are computed on the matched
random-geometry null (E1 procedure, 100 draws, seeds 0..99) so each
slice reports: A EV, null EV+-sd, and entry-lift = A - null.
Frozen slice definitions: ATR percentile = pct-rank of ATR14 within
the last 500 4H bars at entry (inclusive); SMA50 trend state =
up if sma50[t] - sma50[t-6] > +0.001*cp[t], down if < -0.001*cp[t],
else range; year from the entry bar's 4H bucket timestamp (UTC).

#### E5 RESULT (2026-09-22, DESCRIPTIVE): EDGE IS NOT UNIVERSAL -- LOW-VOL + 2025+ CONCENTRATED

runs/ablation_regime.log.  Arm A frozen geometry, 2939 trades;
matched-null slices (100 draws).  Format: A EV (z) vs null+-sd,
lift = A - null.

PRIMARY (in-sample, global-null +0.135):
  atr_hi  n=421:  +0.056 (+0.5) vs +0.195+-0.081 -> lift -0.139
  atr_lo  n=485:  +0.258 (+2.3) vs +0.210+-0.090 -> lift +0.048
  up      n=937:  +0.142 (+1.9) vs +0.147 -> lift ~ 0
  down    n=1030: +0.149 (+2.0) vs +0.119 -> lift +0.030
  range   n=150:  +0.511 (+2.3) vs +0.159 -> lift +0.352 (small n)
  years: 2022 +0.074 lift; 2023-24 +0.075; 2021 -0.064; >=2025
  +0.484 (n=38, noisy)

F3 (holdout, global-null +0.168):
  atr_hi  n=132:  +0.189 (+1.0) vs +0.122 -> lift +0.067
  atr_lo  n=208:  +0.722 (+3.8) vs +0.220 -> **lift +0.502**
  up      n=309:  +0.396 (+2.5) vs +0.206 -> lift +0.190
  down    n=418:  +0.242 (+1.0) vs +0.132 -> lift +0.110
  range   n=95:   +0.546 (+2.0) vs +0.165 -> lift +0.380 (small n)
  2023-24 n=157:  +0.007 (+0.0) vs +0.211 -> lift -0.204  **DEAD**
  >=2025  n=665:  +0.412 (+1.9) vs +0.161 -> lift +0.251
  (<2021, 2021, 2022: no holdout trades by construction)

Verdict per frozen vocabulary: **NOT universal.  Vol-concentrated
(LOW vol) + time-concentrated (2025+).**

Findings:
1. The F3 entry-lift (+0.335 EV overall) is carried almost entirely
   by the >=2025 slice (+0.412 EV, lift +0.251, n=665 of 822 F3
   trades).  The 2023-24 slice is FLAT on holdout (+0.007 EV, lift
   negative).  The "holdout confirmation" is really a
   "current-regime confirmation" -- a robustness caveat that must be
   stated in the live-scale prereg (regime may decay like 2023-24
   did).
2. Entry-lift on F3 concentrates in LOW ATR: +0.502 lift (atr_lo)
   vs +0.067 (atr_hi).  On PRIMARY the sign flips (atr_hi lift
   -0.139).  A "skip high-vol entries" filter is a candidate -- but
   per the meta-rules it requires a NEW dated prereg; nothing is
   filtered in the frozen module.
3. Trend state: lift present in BOTH up (+0.190) and down (+0.110)
   on F3 -> the entry is not a simple trend-follower; range lift
   (+0.380) is suggestive but n is small.  No trend filter
   justified by this data.
4. Method note: slice nulls vary a lot (e.g. >=2025 PRIMARY null
   +0.079+-0.222, range +-0.18-0.24) -- per-slice n is small, all
   slice comparisons are directional evidence only.

Live-scale implication recorded: for the S1-sized AVSL-cross live
prereg, add a "current regime = low-ATR" monitoring read-out (not a
filter) and pre-register expected decay if regime flips.

#### E2 RESULT (2026-09-22): PASS -- THE EDGE IS 4H-SPECIFIC

runs/ablation_tf.log.  Sanity: 4H arm reproduced E1 exactly
(+0.172/+0.335, n=2939, null +0.135+-0.044/+0.168+-0.068, MATCH).

Same frozen pipeline at 1D (deterministic 1H->1D resample; identical
params, horizon 500 bars OF THE RESPECTIVE TF):
  1D arm A:  PRIMARY -0.018R (n=166, z=-0.11)
             F3      +0.013R (n=138, z=+0.07)   -- dead
  1D null:   +0.134+-0.133 / -0.071+-0.154
             (A at 11th pct PRIMARY -- the cross entry is WORSE
             than matched random entries at 1D in-sample)

GATE (frozen): 4H > 1D + 0.05R both segments:
  PRIMARY: +0.172 vs -0.018 -> PASS
  F3:      +0.335 vs +0.013 -> PASS
Verdict per prereg: **PASS -- the edge is 4H-specific.**  Not
"TF-scale drift capture": at 1D both the geometry signal and the
entry lift vanish.

Caveats recorded: 1D n is small (166/138) and the 1D null sd is
large (+-0.13/+-0.15) -- the 1D point estimates are noisy, though
the direction is unambiguous and the gate passed with a wide margin
(+0.19R / +0.32R vs required +0.05R).

Combined with E3 arm E (3xATR stop works -> the AVSL line is not
magic for STOPS), E2 sharpens the picture: the 4H grid + cross
TIMING is where the line carries information.  The engine is the
4H wide-TP geometry; the AVSL cross at 4H is the (regime-bound,
see E5) amplifier -- and it has no 1D counterpart.

#### E4 RESULT (2026-09-22): PASS -- S1 VOL-TIMING CARRIES INFORMATION BEYOND DE-LEVER

runs/ablation_sizing.log.  Sanity: arm B reproduced the frozen
verdict bit-for-bit (Sharpe_NW 1.50/2.84, DD 22%/12%).

Arms (Sharpe_NW PRIMARY / F3, DD):
  A unsized (1.0):  +1.33 (DD 61%) / +2.05 (DD 38%)
  B S1 (frozen):    +1.50 (DD 22%) / +2.84 (DD 12%)
  D 0.33 const:     +1.33 (DD 27%) / +2.05 (DD 14%)
  C permuted S1:    +1.26+-0.18   / +1.98+-0.34  (100 perms)

GATE (frozen): B > mean(C) + 0.2 both segments:
  PRIMARY: +1.50 vs +1.26 -> PASS (B-C = +0.24; required +0.20 --
  passes by +0.04, the narrowest gate margin in the whole battery)
  F3:      +2.84 vs +1.98 -> PASS (B-C = +0.86, wide)

Findings:
1. The vol-size LINK is informative: knowing current realized vol
   (not just the size distribution) is worth +0.24 Sharpe on PRIMARY
   and +0.86 on F3 over permuted sizes.  Vol-target timing is NOT
   pure de-lever -- strongest exactly where the entry-lift lives
   (F3 / recent regime, consistent with E5's low-ATR concentration:
   the sizer and the entry read the same state variable).
2. De-levering alone (D 0.33) already fixes most of the DD disaster
   (61% -> 27%) with zero timing information; S1 buys a further
   DD 27% -> 22% PLUS the Sharpe lift.  S1's value is roughly half
   "smaller when volatile" (mechanical) and half "WHEN it is small"
   (informative).
3. Fragility note: the PRIMARY gate survives by +0.04 -- within the
   permuted-C noise (+-0.18).  The honest statement: vol-timing
   information on PRIMARY is NOT firmly established; on F3 it is.
   Record for the live-scale prereg: keep S1 frozen, monitor the
   realized-vol vs size correlation as a read-out.

#### DECOMPOSITION COMPLETE (2026-09-22): THE METHOD, EXPLICIT

With E1/E2/E3/E4/E5 all run per their frozen preregs, the project
has its first complete causal map of an edge.  Recorded here as the
standing METHOD for every future directional track:

EDGE MAP (AVSL-cross 4H + S1):
  engine    4H grid + wide-TP asymmetry        (E2, E3)
  amplifier AVSL cross, 4H only                (E1, E2)
  regime    low-vol + 2025+                    (E5)
  sizing    de-lever + vol-timing              (E4, marginal on PRIMARY)

Five facts, each pre-registered and verified:
1. TP asymmetry is the engine.  Narrow TP = zero everywhere, even
   on random entries; wide TP yields a +0.135R random-entry null.
2. The 4H grid is critical.  The identical pipeline at 1D is dead,
   and the cross entry sits at the 11th percentile of its own 1D
   null (worse than random).
3. The entry is an amplifier, not the source.  Random geometry
   already earns +0.135R; the AVSL cross adds +0.037R (PRIMARY) /
   +0.167R (F3) over its matched null.
4. The edge is regime-bound.  2023-24 is dead on the holdout
   (+0.007R); >=2025 carries it (+0.412R, n=665/822).  The F3 PASS
   is a current-regime PASS, not a robustness PASS.
5. Sizing = mechanical de-lever + vol-timing.  Const 0.33 already
   takes DD 61% -> 27%; the vol-size LINK adds +0.24/+0.86 Sharpe
   (PRIMARY margin only +0.04 over the gate -- not firmly
   established there).

NEW STANDARDS (binding for all successor tracks):
- Null per-geometry: a signal must beat a MATCHED random-geometry
  null (same count, same side ratio, same geometry, 100 draws,
  seeds 0..99): EV > null_mean + 0.05R AND >= 95th pctile.
- Wide TP is mandatory: any test at 1R/1.5R TP is void by
  construction (E3 C1/C15).
- The 4H grid is the default arena; other TFs need their own null
  and their own justification (E2).
- Old "dead pool" verdicts (z-score, Donchian, OB) were issued at
  narrow-TP geometries and are therefore UNRELIABLE.  Re-tests with
  the wide-TP frame are legitimate NEW preregs, explicitly NOT
  "revivals" of the old tracks.

RE-TEST QUEUE (prereg'd separately before each run): E6 z-score MOM
cross +-1.5 sigma (4H, window 28 = the original 168x1H), E7
Donchian(20) breakout + EMA(200) side filter (4H), E8 OB-retest
(block detector ported to 4H, params unchanged).  Common frame:
stop 3xATR (E-style, no line), TP 5R primary (3R/8R descriptive),
horizon 500, S1 sizing, full battery + per-geometry null gate.
Multiplicity note: three tests, family-level false-positive
expectation ~15% at the 95th-pct gate -- a single marginal PASS
will be labelled WEAK, not confirmed, until independently
replicated (e.g. delayed-entry or sub-period split).

LIVE RISKS (must appear as read-outs in any live-scale prereg):
regime collapse (a 2023-24-like stretch -> EV ~ 0) and vol-regime
flip (ATR hi/lo sign flipped between segments).  Monitoring, not
filters: rolling Sharpe (90d), ATR percentile (500-bar),
corr(realized vol, size).  Disaster brake (pause if rolling
Sharpe < 0 over 90d) is a prereg item, not a discretionary act.

The frozen AVSL 4H S1 module KEEPS its PASS.  E1..E5 are
diagnostics of WHY it passes, recorded so successors test the
theory, not the instance.

#### E6/E7/E8 PREREG (2026-09-22, FROZEN BEFORE ANY CODE/RUN)

Re-tests of three "dead pool" entries under the wide-TP frame.
NOT revivals: the old kills were issued at narrow-TP geometries,
which E3 showed are void by construction.  Each is its own
prereg/run; all three are frozen NOW (before E6 code exists) so the
family-level multiplicity is fixed in advance: 3 tests at the
95th-pct gate -> ~15% false-positive expectation; a single marginal
PASS is labelled WEAK (not confirmed) until replicated (delayed-
entry or sub-period split, itself a new prereg).

COMMON FRAME (frozen, identical for all three):
  grid      4H deterministic resample of the same 1H source
  geometry  stop = 3 x ATR14 (E-style, no line), TP = 5R primary,
            horizon 500 4H bars, stop-first, taker fee 10bp round
            trip, overlapping trades allowed; TP 3R/8R descriptive
  universe  BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP
  segments  PRIMARY = first 2/3 of the global 4H grid, F3 = rest
  sizing    S1 (frozen engine series) for the account stream;
            EV/trade and the null are UNSIZED (sizing-invariant)
  null      matched random-geometry draws, 100 seeds 0..99 (same
            per-asset count and long/short ratio as the entries)
  gates (ALL must hold on BOTH segments):
    E-a  entry EV > null mean + 0.05R
    E-b  entry EV >= 95th pctile of the null distribution
    E-c  Sharpe_NW(sized stream) >= 1.0
    E-d  portfolio DD <= 25%
    E-f  block bootstrap CI (block 500, seed 11) excludes 0
  verdict   PASS = all gates both segments; WEAK = E-a/E-b pass on
            both but the family multiplicity caveat applies; FAIL =
            any of E-a/E-b fails on either segment (kill; no re-params)

E6 -- z-score MOM re-test.  Entry (the original MOM-1 rule, moved
  from 1H to the 4H grid, window scaled 168 x 1H = 28 x 4H):
  z28 = (close - SMA28) / STD28 (ddof=1); LONG when z28 crosses
  above +1.5 (prev <= 1.5, cur > 1.5); SHORT when z28 crosses below
  -1.5.  Entry at the close of the cross bar.  Exit = frame (the
  original z-cross-0 exit is NOT used -- replacing the exit is the
  point of the re-test).  Eligible bars >= WARMUP 400.

E7 -- Donchian re-test.  Entry (original breakout rule): LONG when
  close crosses above the prior 20-bar high (hh20 over bars t-20..t-1),
  SHORT when close crosses below the prior 20-bar low; side filter
  kept from the original: long only if close > EMA200, short only if
  close < EMA200 (both on 4H closes).  Exit = frame (the original
  Donchian(10) exit is NOT used).

E8 -- OB-retest re-test.  Entry: the original block detector
  (supply/demand zones) ported to 4H with parameters unchanged;
  LONG at a demand-block retest bar, SHORT at a supply-block retest
  bar, within the original delay window.  Exit = frame.  (Detector
  port is implementation work, not a parameter change; if the port
  cannot reproduce the original 15m detector's taken-trade counts
  1:1 on a common subsample, E8 is postponed, not approximated.)

Fixed before code: runner `experiments/avsl/retest_entry.py`,
one invocation per entry, logs `runs/retest_{e6,e7,e8}.log`.  No
new arms, no gate changes, no params after the first run of each.

#### E6 RESULT (2026-09-22): FAIL -- z-LIFT IS REGIME-BOUND WITHOUT HOLDOUT SUPPORT

runs/retest_e6.log.  z-score MOM cross +-1.5 sigma (z28, 4H),
wide-TP frame, 10370 entries.

  PRIMARY: EV +0.155R (n=7410, z +3.0) vs null +0.061+-0.025
           -> E-a PASS, E-b 100th pct PASS; Sh(S1) +2.04, DD 24%,
           CI>0 -- in-sample everything passes.
  F3:      EV +0.077R (n=2960, z +1.9) vs null +0.085+-0.038
           -> E-a FAIL, E-b 41st pct FAIL; Sh +0.92, DD 31%,
           CI covers 0.
Verdict per prereg: **FAIL (kill).**  The z-entry does carry entry
information over the wide-TP null IN-SAMPLE (100th pct -- notable:
the old 1H kill at narrow TP was even right about the mechanism,
but the wide-TP null confirms a real PRIMARY effect), yet it has NO
holdout support -- the same 2023-24-dead pattern as E5, without the
>=2025 rescue.  Not a candidate; the old kill verdict stands under
the new frame.

#### E7 RESULT (2026-09-22): ENTRY INFORMATION IS REAL ON BOTH SEGMENTS; RISK GATES FAIL (DD)

runs/retest_e7.log.  Donchian(20) breakout + EMA200 side filter
(4H), wide-TP frame, 9530 entries.

  PRIMARY: EV +0.221R (n=6614, z +1.9) vs null +0.096+-0.028
           -> E-a PASS, E-b 100th pct PASS; Sh(S1) +1.42,
           DD 29% (E-d FAIL), CI>0.
  F3:      EV +0.185R (n=2916, z +4.4) vs null +0.096+-0.042
           -> E-a PASS, E-b 98th pct PASS; Sh(S1) +1.53,
           DD 38% (E-d FAIL), CI>0.
Verdict per prereg: **overall FAIL (not PASS: E-d DD>25% both
segments), and per the kill rule this is NOT a kill** -- the kill
criterion is an E-a/E-b failure, and both PASS on BOTH segments.

This is the AVSL-history pattern in reverse: a second entry (after
AVSL) that beats its matched random-geometry null on the holdout at
the 98th percentile.  What fails is risk, not signal: DD 29%/38%
despite S1 sizing (the Donchian entry is 3.2x denser than AVSL
cross and clusters in trends, where sizes stay high).

Recorded successor path (each a NEW prereg, nothing done now):
a sizing/risk-only overlay track for Donchian-4H wide-TP, exactly
mirroring the AVSL risk-overlay track (S1..Sn sweep, risk-first
gates).  If an overlay passes 5/5, the project gets its second
confirmed track and the first out-of-sample replication of the
METHOD (entry x wide-TP geometry x vol-target sizing).

#### E8 STATUS (2026-09-22): POSTPONED per prereg

The OB block detector port to 4H requires a 1:1 taken-trade
reproduction check against the original 15m detector on a common
subsample before any run (prereg condition).  Not yet performed;
E8 stays postponed, not approximated.

FAMILY MULTIPICITY LEDGER: 2 of 3 re-tests executed, 0 PASS, 0 WEAK
consumed -- no false-positive budget spent.

#### DONCHIAN-4H RISK-OVERLAY PREREG (2026-09-22, FROZEN BEFORE CODE)

Predecessor: E7 (commit 3f73442) -- the Donchian(20)+EMA200 entry
beats its matched random-geometry null on BOTH segments (100th /
98th pctile, CI > 0); only the risk gates fail (DD 29%/38% under
S1).  Signal confirmed, risk unsolved -> a risk-only overlay track,
the exact AVSL risk-overlay pattern (b6005ca -> e6b4b4d).

FROZEN SIGNAL (identical to E7 -- the numbers above were measured
on this geometry and it is NOT changed here):
  entry     Donchian(20) close-cross breakout, 4H, EMA200 side
            filter (long only above, short only below)
  stop      3 x ATR14 at the entry bar (E-style, no line)
  exit      TP 5R primary, MTM at horizon 500 4H bars, stop-first
  fee       10 bp round trip; overlapping trades allowed
  universe  BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP
  split     PRIMARY = first 2/3 of the global 4H grid, F3 = rest
DEVIATION NOTE (recorded deliberately): the initiating message
specified "stop = max(Donchian(10), 2xATR)" -- that is the OLD
track's geometry, on which the E7 lift was NOT measured.  Re-freez-
ing the stop to the old value would silently swap the signal under
the verified numbers.  The overlay therefore runs on the E7
geometry above; the old geometry may only be tested as ANOTHER new
prereg.

SIZING HYPOTHESES (frozen before code; per-trade sizes applied to
the E7 trade set, engine accrual semantics):
  S1  baseline vol-target: clip(0.20 / rv100, 0.25, 2.0)
      (= the engine S1 series; sanity: must reproduce E7's
      Sharpe 1.42/1.53, DD 29%/38%, EV +0.221/+0.185 bit-for-bit)
  S2  aggressive vol-target: clip(0.15 / rv100, 0.15, 1.5)
      (rationale: Donchian clusters 3.2x denser than AVSL cross;
      harder de-lever)
  S3  S1 + concurrency cap: max 5 concurrent open trades AND max
      total open exposure 3.0 size units; an entry that would
      breach a cap is SKIPPED (size 0, excluded from stream, EV and
      asset counts).  DONCHIAN-ONLY HYPOTHESIS: on AVSL the cap was
      measured toxic (Sharpe 0.22, EV +0.02R -- clustered entries
      carry that edge); on Donchian the clusters are trend-late
      entries and the question is OPEN.  A result either way is a
      new fact and goes to STATUS.
  S4  S2 + the same cap
  S5  S2 x regime halving: size x 0.5 when ATR14 percentile
      (500-bar inclusive window at entry) > 80; never a full skip
      (the AVSL S2 lesson: percentile scaling alone leaves DD loose;
      here it is stacked on S2, not used alone)

GATES (per config, on BOTH segments, taken trades):
  G1'  Sharpe_NW(sized accrual stream) >= 1.0
  G2'  portfolio DD <= 25%
  G3'  net EV >= 0.10R
  G4'  >= 7/10 assets with positive mean net EV
  G5'  block bootstrap CI (block 500, seed 11) excludes 0
SELECTION (risk-first, frozen): among configs passing ALL gates on
both segments, select the one with the lowest PRIMARY DD
(tie-break: lower F3 DD, then lower mean gross size).  One config
passing = that config.  None passing = track CLOSED FINAL (the
Donchian entry itself stays recorded as null-confirmed; only the
track is closed).
KILL / BOUNDARIES: entry, stop, TP, horizon, universe, split are
frozen; no S-variant may be added after the first run; F3 is never
tuned on; no combination with AVSL before both tracks are
individually confirmed (portfolio construction = a later prereg).

Runner: `experiments/avsl/donchian_overlay.py`, single invocation,
log `runs/donchian_overlay.log` (numbers duplicated into STATUS).

#### DONCHIAN OVERLAY RESULT (2026-09-22): NO CONFIG PASSES -> TRACK CLOSED FINAL

runs/donchian_overlay.log.  Sanity: S1 reproduced E7 bit-for-bit
(Sh 1.42/1.53, DD 29%/38%, EV +0.22/+0.18, CI identical).

  S1  P: Sh+1.42 DD29% EV+0.22 pos8 CI>0 (DD FAIL)
      F: Sh+1.53 DD38% EV+0.18 pos9 CI>0 (DD FAIL)
  S2  P: Sh+1.50 DD20% EV+0.22 pos8 CI>0  ALL PASS
      F: Sh+1.50 DD30% EV+0.18 pos9 CI>0 (DD FAIL -- 5pp short)
  S3  cap taken 156/9530 (exposure 3.0 saturates instantly);
      P: Sh+1.41 DD3% EV+0.89; F: Sh+0.63 EV-0.02 pos5 -> FAIL
  S4  same shape (159 taken); F: Sh+0.60 EV-0.08 -> FAIL
  S5  P: Sh+1.55 DD19% EV+0.22 ALL PASS
      F: Sh+1.18 DD31% EV+0.18 (DD FAIL)

VERDICT per prereg: **no config passes on both segments -> the
Donchian-4H track is CLOSED FINAL.**  The entry itself stays
recorded as null-confirmed (E7); what is closed is the track.

Three new facts for the method map:
1. **Cap toxicity REPLICATES on Donchian** (S3/S4: F3 Sharpe 0.6,
   EV <= 0).  The AVSL S3 lesson was not entry-specific: on both
   entries the clusters CARRY the holdout edge, and capping
   amputates it.  This is now a general law of the method, measured
   on two independent entries.
2. **Donchian DD is not sizing-fixable within the frozen family:**
   S2/S5 fix PRIMARY (DD 19-20%) but F3 sticks at 30-31%.  The
   holdout drawdown comes from clustered trend entries in the 2025+
   regime that the vol-target cannot see (their realized vol at
   entry is LOW -- consistent with E5's low-ATR lift concentration:
   the same state variable that carries the entry lift defeats the
   sizer).  Signal and risk are coupled through one variable.
3. The method's boundary is now measured: **entry lift transfers
   across entries (AVSL, Donchian), but risk-compatibility does
   NOT.**  A null-confirmed entry is necessary, not sufficient; the
   second gate is whether its DD is controllable by sizing alone.

Family ledger: re-tests 2/3 executed (E8 postponed), overlay 1
executed; confirmed tracks: AVSL-cross 4H S1 only.  No false-
positive budget spent (0 PASS issued in the family).

#### E8 PORT-CHECK RESULT (2026-09-22): FAIL -- E8 STAYS POSTPONED

runs/port_check_4h.log.  Diagnostic per the E8 gate (detector must
be 4H-usable before any run).  The detector RUNS on 4H OHLCV with
the "4h" preset and its geometry is sane:
  zone width med 1.35-2.16 ATR14 (inside the [1, 3] target),
  retest delays median 1-4 bars, 100% within 36 bars,
  supply/demand split balanced.
But block counts are 9-34 per asset over the full ~7y 4H history
(BTC: 10) -- two to three orders of magnitude below what an EV
comparison needs (the user-set criterion "not ~10" is exactly
violated).  Reference sanity: BTC 1H + "1h" preset gives 131 blocks
on 6x more bars -- the 4h preset is far stricter than the archived
working combo (its market-structure filter + complete-window
requirement dominate at this bar size).

Consequence per the frozen rule: **E8 stays POSTPONED; the OB
detector rework under 4H is a separate engineering task with its
own frozen acceptance criteria** (proposal, not yet a prereg: a
reworked preset must yield ~200-2000 blocks per asset on the 4H
grid, zone width med in [1, 3] ATR, delays <= 36 bars, and the
detector itself must remain repaint-free) -- only then can an E8
prereg be written.  Tuning preset parameters ad hoc to make E8
runnable is exactly what the port-check gate exists to prevent.

#### OB ENGINEERING PLAN (2026-09-22): BACKLOG, ACTIVATION-CONDITIONAL

Problem: the "4h" live preset yields 9-34 blocks/asset on the 4H
grid -- live-grade sparsity, useless for EV statistics.  Decision:
build RESEARCH presets as a separate artifact (live preset for
trading, research preset for statistics -- different products,
NEVER mixed), rather than tune anything "so E8 can run".

Diagnosis first (which filter kills the blocks -- measured, not
guessed): the "4h" preset stacks use_market_structure_filter=True,
require_complete_window=True, strength_age_penalty=True,
zigzag_distance=8, min_extreme_gap=8, reversal_atr_multiple=2.5
(ATR-calibrated reversal; there is no fixed online_reversal_pct in
this pipeline).  Ablate one filter at a time on BTC+ETH 4H and
record blocks/asset per ablation.

Research-preset candidates (detector logic UNTOUCHED, presets only;
repaint-free online ZigZag, look-ahead guards and determinism are
non-negotiable):
  R1 conservative   ~200-500 blocks/asset
  R2 balanced       ~500-1000
  R3 aggressive     ~1000-2000
  R4 no-ADX         (is the trend filter even doing anything?)
  R5 no-structure   (same question for the structure filter)
Likely levers: require_complete_window=False,
use_market_structure_filter=False (or min extremess relaxed),
zigzag_distance 6-7, min_extreme_gap 6-7; zone geometry, retest
logic and strength computation stay as-is.

ACCEPTANCE (frozen; all must hold on ALL 10 assets):
  200-2000 blocks/asset over the ~7y 4H grid; zone width med in
  [1, 3] ATR14; retest delay med <= 10 bars, p90 <= 36 bars; S/D
  each side 30-70%; repaint-free test still passes; byte-identical
  output on rerun; "1h" preset regression unchanged (131 blocks,
  BTC 1H) and "4h" preset regression unchanged (10 blocks, BTC 4H)
  -- research presets are additions only.

Then, and only then: E8 prereg (frozen entry = OB-retest 4H on the
selected research preset, wide-TP frame, gates as E6/E7) -> run.
Budget: ~9h engineering + ~1.5d E8.

PRIORITY: BACKLOG.  Activation triggers: TTF v1 AND P4 both FAIL,
or an explicit portfolio need for a second track.  Until then the
queue is: AVSL live-scale prereg -> AVSL productization -> TTF v1 /
P4 preregs.

#### OB ENGINEERING RESULT (2026-09-22, commit b6e2158): ACCEPTANCE PASS

Engineering was activated by user decision the same day (overrides
the backlog gate; documented, not hidden).  Measured by 3-round
ablation (runs/ob_ablation{,2,3,4,5}.log): the "4h" live preset's
block killers are the market-structure filter (x2), min_extreme_gap
8 (x2.3) and the breakout volume condition (x2.5); prominence and
zigzag_distance are no-ops for the online ZigZag; ADX is absent
from the "4h" preset entirely; the reversal lever saturates under
multiple_breakouts (0.8 -> 0.5 gives only +8%); dynamic->fixed
lookback is the aggressive lever.  Detector logic untouched --
presets only (experiments/ob/research_presets.py).

Acceptance (runs/ob_research_check.log): R1 273-672, R2 575-1146,
R3 793-1146 blocks/asset -- all in [200, 2000] on ALL 10 assets;
zone width med 1.56-2.09 ATR; delay med 2-3, p90 6-9 bars; S/D
35-56%; A6 regression exact ('1h'=131, '4h'=10); determinism OK;
detector tests 46 passed.  R4_diagnostic (structure ON, 99-251)
documents the filter cost and is reference-only.

#### E8 PREREG -- OB-RETEST 4H (frozen 2026-09-22, BEFORE run code)

Entry (frozen): OB-retest events on the 4H grid from RESEARCH
preset **R2** (balanced, ~575-1145 blocks/asset).  R2 chosen A
PRIORI as the workhorse (sample size vs selectivity); R1/R3 are
SENSITIVITY references, descriptive only, never gated -- no post-hoc
preset switching.  Side: demand-zone retest -> long, supply-zone
retest -> short; entry bar = the detector's retest bar; WARMUP 400.
Frame (identical to E6/E7): stop 3xATR14, TP 5R, horizon 500, fee
10bp RT, S1-sized account stream, SPLIT_FRAC 2/3.
Null: matched random-geometry, per-geometry, 100 draws seeds 0..99.
Gates: E-a (EV > null + 0.05R) and E-b (>= 95th null pct) on BOTH
segments; then E-c Sharpe >= 1.0, E-d DD <= 25%, E-f bootstrap CI > 0
(seed 11, block 500).  Kill on E-a/E-b failure.  PASS-entry-FAIL-risk
-> risk-overlay prereg (Donchian pattern).
Family note: E8 is the third and final dead-pool re-test; family
false-positive budget remains 0 until a PASS is issued.

#### E8 RESULT (2026-09-22, runs/retest_e8.log): FAIL -- KILL

Runner: experiments/avsl/retest_entry.py (kind "ob", prereg
7105724).  8538 entries (R2 preset).  Gates:
  PRIMARY: EV -0.034R (n=5872, NW z -1.08) vs null +0.043+-0.027
           -> E-a FAIL, E-b 0th pct FAIL; Sh +0.08, DD 48%,
           CI [-0.0092, +0.0124] -- ALL gates fail.
  F3:      EV +0.084R (n=2666, NW z +1.93) vs null +0.067+-0.049
           -> E-a/E-b FAIL (61st pct); E-c/E-d/E-f pass.
Per the frozen rule (E-a/E-b failure) this is a KILL; the old
dead-pool entry stays dead under the correct wide-TP geometry.

Reading (descriptive): OB-retest entries are ANTI-edge on PRIMARY
-- 0th percentile means structural-entry timing was systematically
WORSE than random bars pre-2025 in this frame; the mild F3
positive (+0.084, z +1.93) is the same post-2025 regime signature
as E5 but at half the AVSL lift and without gate support.  No
follow-up: a signal that loses to random geometry on 5872 trades
is not a tuning candidate.

Family ledger FINAL: re-tests 3/3 executed, 3 executed -> z-score
KILL, Donchian null-confirmed/risk-closed, OB KILL; overlay 1/1
CLOSED FINAL; 0 PASS issued -- false-positive budget unspent.
Only confirmed track: AVSL-cross 4H S1.  The dead pool is fully
adjudicated; no further dead-pool work is planned.

User directive after carry v3 PASS-with-decay (13.5 -> 3.75 ->
1.45 %/yr by fold, the user's "funding carry сжался до 4%" read):
three-track plan, amended by a live data audit before any prereg.

### TON -> GRAM (same day, data note)

Binance USDT-M rebranded TON: TONUSDT is now SETTLING, GRAMUSDT is a
NEW contract (history from 2026-07-02 -- not a continuous rename).
The TON-era klines (22 421 bars, 2024-03..2026-07) stay cached as
kl_TONUSDT_1h.parquet; oi_TONUSDT was empty (the OI endpoint refuses
settling symbols) and was removed.  load_binance maps
TON-USDT -> GRAMUSDT (SYMBOL_ALIASES) for all new collection:
kl_GRAMUSDT (1954 bars, 0 gaps) + oi_GRAMUSDT (744 rows, 31d) are in.
Universe for the frozen preregs is untouched -- TON-USDT is the OKX
inst name; only the Binance collection side is aliased.  Note: the
GRAM funding history starts 2026-07-02, so any future funding-carry
re-run on live Binance funding has ~2.7 months of depth for GRAM.

Layout bug fixed here: 18 moved modules (avsl_*, ensemble_ab,
funding_carry*, load_*, ob_*) computed REPO as three levels of
.parent -- correct at engine/experiments/ depth, one level too deep
after the move (stray projects/data/).  All now use .parent.parent.

### DATA FEASIBILITY (verified live 2026-09-21, decisive for the plan)

| source | real depth | verdict |
|---|---|---|
| OKX OI history (rubik open-interest-history) | ~8.3h (100 x 5m; `bar` ignored; pagination does not deepen: 500 rows within 0.35d) | backtest impossible |
| Binance OI (fapi openInterestHist) | hard cap ~30d (endTime 40d back -> HTTP 400, reproduced) | non-gated screen only |
| OKX long/short account ratio | 2d | useless |
| Binance topLongShortPositionRatio | ~21d (30d cap) | useless |
| Binance klines taker buy volume (field 9) | full history, oldest 1H bar 2019-09-08 | BACKTESTABLE |
| Binance funding 3y | cached (data/funding_binance) | carry v3 PASS |

Decision (user-approved): the OI-Price Divergence track AS WRITTEN
(gated walk-forward Sharpe on OKX OI 5m) is NOT registrable -- the
panel does not exist (8h vs the repo standard ~449d; the funding
track with 97d was already rejected as thin).  Amended: the
positioning signal is tested via taker-flow (taker buy volume from
Binance klines, 6y depth) = TTF v1 below; OI accumulation starts
now (infra, zero-regret); ProSP runs as barrier v2 with funding +
taker-flow features.  LGBM, not XGBoost (repo standard, declared).

### Infra added (no gates)

- `engine/infra/marketdata/binance_fetch.py`: `fetch_klines`
  (full history, incremental page-cache, closed bars only,
  keeps `taker_buy_volume`) and `fetch_oi_history`
  (merge-append 30d window; running >= 1x/30d accumulates an
  unbounded panel).  Driver `engine/experiments/load_binance`
  (universe = the funding UNIVERSE mapped to Binance symbols,
  cache data/binance/).  Tests: engine/tests/test_binance_fetch.py
  (6: merge keep-old/dedup/no-shrink, kline parse, in-progress bar
  dropped).
- OI ACCUMULATION TRACK: run
  `python -m engine.experiments.load_binance <SYM> oi` at least
  every 30 days per symbol (weekly cron recommended).  No backtest
  until >= 180d contiguous; the eval prereg will be written BEFORE
  the first backtest.  No peeking at the accumulating panel for
  signal design.

### TTF v1 (taker-flow divergence) -- PRE-REGISTRATION (fixed BEFORE run)

Backtestable replacement for OI-Price Divergence: aggressive-flow
divergence against price, same four-regime logic, order-flow proxy
instead of OI.  Data: Binance USDT-M 1H klines, 6 majors (BTC, ETH,
SOL, BNB, XRP, DOGE), ~6y.

Frozen parameters (from the user's plan, no tuning):
  tbv_share = taker_buy_volume / volume (1H bar)
  s = Z(tbv_share, trailing 336 bars)
  r = close-to-close return over trailing 24 bars
  LONG regime: r < 0 AND s >= +2.0 (buy aggression into decline =
  accumulation); SHORT mirrored: r > 0 AND s <= -2.0.
  Confirmation: signal bar closes in the intended direction
  (close > open for long).  Entry at next bar open.
  Exit: |s| < 0.5, or opposite divergence, or stop.
  Stop: 2.0 x ATR(24 bars) from entry; no take-profit.
  One position per asset; notional 1.0.
  Costs: taker both legs, 0.075% per side (= 0.15% round trip),
  charged at entry and exit halves.
  Signals use completed bars only (no lookahead).

Evaluation: F1 = 2021-01-01..2023-08-31, F2 = 2023-09-01..2025-08-31,
PRIMARY = F1+F2 pooled; F3 = 2025-09-01..now = confirmation,
reported not gated.  Daily net streams per asset; Sharpe_NW with
the funding_carry_v3 estimator (Newey-West lags 1..5, factor
clamped [1, 5]); activity floor 60d.

PRE-REGISTERED gates (all on PRIMARY, else the track is closed,
no re-tuning):
  T-G1: Sharpe_NW >= 1.0 on >= 3 of 6 assets.
  T-G2: portfolio (equal-weight, flat contributes 0) Sharpe_NW >= 1.0.
  T-G3: portfolio max drawdown <= 20%.
  T-G4 (sanity): gross (pre-cost) portfolio Sharpe > 0 -- if the
     signal cannot beat zero before costs it does not exist.
  Sanity outputs, not gates: n trades per asset (if n < 200 on
  PRIMARY the result is INCONCLUSIVE, not PASS), fold-by-fold
  table, gross-vs-net per fold.

#### TTF v1 RESULT (2026-09-24; prereg frozen 2026-09-21 BEFORE
#### code; runner experiments/ttf/ttf_v1_check.py, one-shot)

Runner conventions declared in the docstring (prereg-silent
execution details, not parameters): z ddof=1, stop-first
intrabar with gap fill at open, ATR frozen at signal bar,
daily MTM streams, portfolio = sum/6 fixed denominator.
Process note: two earlier executions crashed on mechanical
bugs (missing __main__ guard; ms-vs-day-id units in
searchsorted) BEFORE any metric existed; the portfolio-level
numbers were identical across both complete outputs.  No
parameter or logic choice followed a look.

RESULT -- CLOSED per prereg (T-G1, T-G2, T-G4 fail; no
re-tuning):
- Trade counts (PRIMARY): 647..779 per asset -- all >= 200,
  so the result is CONCLUSIVE, not INCONCLUSIVE.
- T-G1: 0/6 assets >= 1.0 net Sharpe_NW (range -1.07..-3.01).
- T-G2: portfolio net Sharpe_NW = -4.75 (fail).
- T-G3: portfolio maxDD = 1.3% (passes trivially -- the track
  loses slowly rather than drawing down).
- T-G4 (kill): gross portfolio Sharpe = -0.77 <= 0 -- per the
  prereg's own wording, the signal does not exist before
  costs.
- Folds (gross/net portfolio): F1 -0.23/-3.89, F2 -1.73/-6.38,
  F3 +1.21/-4.54 (F3 reported, not gated).  Gross is negative
  in both PRIMARY folds; the lone positive F3 gross is far
  below its own cost drag and gates nothing.

Mechanism recorded: aggressive-flow divergence (buy aggression
into decline = accumulation) is ANTI-signal at the 1H scale on
these six majors -- gross negative means continuation dominates
the presumed reversal, the opposite of the divergence premise.
Independent of direction, the frame's turnover (~0.4 round
trips/asset/day) at 15bp RT needs a per-trade edge this signal
family does not have.  TTF family: the flow-DIVERGENCE variant
is closed by mechanism.  ProSP v2 remains prereg'd and open
(it uses tbv features as probabilities under a walk-forward
protocol, a different claim); P4 low-cap carry and basis trade
remain the breadth queue.


### PROSP v2 (probability-based portfolio) -- PRE-REGISTRATION (fixed BEFORE run)

Successor to barrier-probability v1 (CLOSED: model Brier 0.21747 >
baseline 0.21688 on price/vol/structure features).  v2 tests the
declared missing ingredient -- flow/positioning features -- as
tail-event probabilities, not point returns.

Data & labels: Binance USDT-M 1H, the 29-asset Binance universe.
Labels per (asset, bar t, daily): label_up = 1 iff close(t+24)/
close(t) - 1 > +2%; label_dn mirrored (< -2%).  Labels from future
bars only; the 7d embargo guards the label gap.

Features (frozen list): tbv_share z(336), tbv_share delta(24),
funding z(3d, from data/funding_binance), ret(24), ret(168),
ATR(24) z(336), volume z(336), range/close z(336).  No price level,
no calendar features.

Model: LightGBM binary classifier, two tasks (up-tail, dn-tail),
pooled across assets.  Params frozen at the repo defaults
(n=400, lr=0.05, leaves=15, mcs=40); isotonic calibration on the
56d window before the embargo gap (barrier v1 protocol).

Walk-forward: 8 folds x 56d, expanding train, 7d embargo, per the
repo WF protocol; predictions only on embargoed TEST bars.

Portfolio rule (frozen): daily, rank assets by
P(up-tail) - P(dn-tail); long top 3, short bottom 3, equal weight,
rebalanced daily; cost 0.15% RT per leg change; skip a leg if the
asset's panel row is incomplete.  No vol targeting in v2 (declared).

PRE-REGISTERED gates (pooled TEST, else v2 closed, no re-tuning):
  P-G1 (kill, user's criterion): mean calibrated Brier (both tasks)
     < constant class-rate baseline, AND per-fold improvement > 0
     on >= 5 of 8 folds.
  P-G2: top-minus-bottom tercile net daily EV > 0 on pooled TEST.
  P-G3: portfolio net Sharpe_NW >= 1.0 on pooled TEST.
Reported, not gated: reliability deciles, per-fold portfolio
Sharpe, long-only vs long-short split.

Standing rule honored: no parameter was fit on any test window;
TTF/ProSP params come from the user's plan and repo defaults, and
were written here before either experiment runs.

## 2026-09-20 — ranker ensemble package (`engine/ensemble/`)

- `engine/ensemble/`: `base` (RankerComponent interface, ComponentConfig,
  rank_normalize), `lgbm` / `catboost` / `logreg` components, `combine`
  (EnsembleRanker: mean / weighted / rank_mean / stacking), `meta`
  (stacking meta-learner trained on past-only OOF component scores —
  no in-sample meta weights).  Determinism kit per component:
  LGBM deterministic+force_row_wise+1 thread; CatBoost thread_count=1;
  catboost is an OPTIONAL dependency (lazy import, CATBOOST_AVAILABLE).
- `protocol.train_ensemble_ranker`: ensemble twin of `train_ranker`
  (same contract — past-only train_ix, scores for all rows in input
  order), so replay/experiments switch heads by config alone.
- `experiments/ensemble_ab.py`: pre-registered grid of 6 configs
  (lgbm_only / catboost_only / logreg_only / lgbm+catboost /
  all_three / stacking) through one WF protocol + replay; metrics:
  pooled R / dd / sharpe, decile spread, top-decile EV, flips@1e-6,
  peak gate EV; `--quick` smoke mode.  Acceptance: ensemble beats the
  best single component, dd not worse — else keep LightGBM-only.
- Tests: `engine/tests/test_ensemble_*.py` (45 tests: determinism
  byte-for-byte, dtype discipline, scaler convergence, enable/disable
  vs weight=0, stacking past-only OOF, mini-WF regression, protocol
  integration) + `ens_synth.py` synthetic panel helper.  catboost
  tests skip cleanly when the lib is absent.
- catboost added to root dependencies (installed 1.2.10 locally).
- Fixed a latent restructure bug: `protocol.REPO` pointed at
  `engine/` instead of the repo root (data paths were computed from
  the pre-move location) — experiments had not been re-run since the
  move, first caught by the ensemble_ab smoke run.
- Quick smoke (last 3 folds, catboost 60 iters): lgbm_only leads
  (pess −0.020, spread +0.169); no blend beats it yet.
- FULL run verdict (8/8 folds, all configs, catboost 300 iters,
  runs/ensemble_ab.json): the whole grid is negative (dead pool —
  TZ item 8 predicted the ensemble cannot revive it).  lgbm_only:
  −0.017R (dd 12.6).  No config passes acceptance: lgbm+catboost is
  the only positive-peak-gate head (+0.001 vs −0.014) with the best
  top-decile EV (−0.002) and spread +0.131 (vs +0.062), but worse dd
  (18.1R) and mean R; stacking edges mean R (−0.014) with equal dd
  but weak spread.  DECISION (per TZ item 6): keep LightGBM-only;
  the ensemble package stays as infrastructure, lgbm+catboost 0.5/0.5
  is the only blend worth re-visiting if the pool turns positive.

## 2026-09-20 — tests co-located in engine/, CI subordinated to the layout

- `tests/` -> `engine/tests/`: the unit suite lives inside the package
  it tests (git mv, history preserved).  Depth-dependent paths updated
  (config yaml lookup, ob-pipeline sys.path bootstrap).  dsl/tests
  stays in its own package by design.
- CI now follows the layout exactly: `ruff check engine dsl` (tests are
  inside engine/), `mypy engine` covers the whole package including
  tests, `pytest` runs on `testpaths` from pyproject (engine/tests +
  dsl/tests).  The dead `[tool.mypy-engine]` section (never read by
  mypy) is gone; the strict flags now actually apply via `[tool.mypy]`
  with `ignore_errors` overrides for engine.experiments/.datasets/
  .tests (unannotated by design).
- Root `conftest.py` marker map updated (`-m engine` works on the new
  path); pytest `testpaths` and ruff test ignores generalized to
  `**/tests/**`.

## 2026-09-20 — engine restructure: subpackages, no scripts/, no ID naming

- `scripts/` removed entirely; every experiment driver is now a library
  module under `engine/experiments/` without ID prefixes (wf_ab ->
  walk_forward_ab, d13c_cost_cap -> cost_cap, d13g_ranker_only ->
  ranker_only, d14_feature_family -> feature_family, d14_funding_carry
  -> funding_carry, d13d_regime_diag -> regime_diag).  Experiment
  entry points that lived inside library modules (D.6 joint rank in
  sim, D.11 admission compare, D.12 maker grid) were extracted into
  `engine/experiments/{joint_rank,admission_policies,maker_entry}.py`.
  Artifact filenames in `runs/` for NEW runs lose the d-prefix too
  (old artifacts keep historical names, referenced below).
- `engine/` decomposed into functional subpackages:
  `infra/` (config, datatypes, io, marketdata), `features/`
  (indicators, mtf, panel, dsl_feed, spec, provider, events),
  `structure/` (zones, candidates), `sim/` (engine, maker,
  state_machine, admission), `backtest/` (protocol), `model/`
  (ranker), `metrics/` (trade: trade_curve_stats / per_trade_sharpe /
  bucketed_sharpe / pooled_stats - extracted from the ranker head and
  protocol), `datasets/` (okx, mtf, stops - the former dataset-build
  scripts).
- d-naming scrubbed from code: `ENCODING_D13` -> `ENCODING_ZEROED`,
  `ENCODING_D8B` -> `ENCODING_NATIVE`, docstrings/comments rewritten
  without D.NN experiment IDs (history stays here; archived specs moved
  to `legacy/dev_docs/`).
- Encodings renamed to names again: ENCODING_ZEROED (float32,
  NaN/inf->0) and ENCODING_NATIVE (float64, NaN kept).
- Gates: pytest 327 passed; ruff clean on engine+tests+dsl (research-
  grade zones `engine/experiments/**` and `engine/datasets/**` carry
  explicit per-file-ignores in pyproject); mypy clean on the library
  core (25 files).

## 2026-09-19 — package rename ai -> engine, scripts cleanup

- `ai/` -> `engine/` (the package is the whole research engine, not just
  models): `dte-engine` in the uv workspace, `[tool.mypy-engine]`,
  pytest marker `engine`, `configs/engine.yaml`.
- Library-grade scripts moved into the package: `zones`, `sim`
  (ex `sim_engine`), `maker` (ex `maker_entry`), `admission`,
  `okx_dataset` (ex `prepare_okx_dataset`).  Their demo pipelines
  (D.6/D.11/D.12) now run via `python -m engine.<mod>` behind
  `__main__` guards - importing the package is side-effect free.
- `scripts/` keeps experiment drivers only (wf_ab, nested_cv,
  matrix_2x2, ranking_baselines, adaptive_tp, execution_costs,
  robustness, portfolio, build_*_dataset), linted at F,E9 tier.
- CI fixed: the lint step had a malformed (nested) YAML list; pushes
  now trigger on `dev` too.  Lint/mypy retargeted to `engine/`.
- Numbers re-validated after the move: B pooled 6/8, admission
  REPLACE-low +466.0R / 2.44R DD, D.6 gated test pess +0.302, D.12
  maker lift -0.414 - all identical to the pre-refactor state.

## Implemented ✅ / core 🔨

| Module | Status | Tested/verified |
|--------|--------|-----------------|
| `ta/` indicator library | ✅ 84 indicators in DSL (TZ-03 wave 2) | 1975 tests |
| `dsl/` trading DSL | ✅ TZ-01 | 154 tests |
| `strategies/` strategy layer | ✅ TZ-02 | 25 tests |
| `backtest/` backtest | ✅ core; risk-gate ✅ TZ-04 | 34 + 12 integration |
| `risk/` risk engine | ✅ config-driven TZ-11 | 22 + 12 integration |
| `engine/` model | 🔨 core; trained on real data (OKX 7×4TF), best classifier of the baseline run — edge not yet achieved (gate not passed) | 71 tests + first backtest vs 7 baselines |
| `infer/` CLI | ✅ TZ-05 | 9 tests |
| `rag/` RAG | 🔨 core; pass@1 unmeasured | 47 tests |
| `main/` DI+bridge+REST+PG | 🔨 core; e2e on in-memory broker + SQLite | 12 REST + 10 db + e2e |
| `okx/` venue adapter (TZ-15) | ✅ core v1 + ✅ live public md (REST warm-up + WS business stream) | 39 tests (36 unit + 3 live smoke) |

**Status of the deterministic path:** complete end-to-end on **synthetic** data:
`ta → DSL → signals → Risk Engine → backtest with reject-audit`.

## Not implemented / remaining ⬜

1. **Live production backends never wired** — in-memory RabbitMQ / SQLite / mocked Ollama only;
   `docker compose up` with real RabbitMQ/PG/Qdrant/Ollama is untested.
2. **Local backtest runner in `main/`** — cmd.backtest returns "failed: no runner" stub.
3. **Model has no trading edge yet** — artifacts exist (`runs/okx7/best.pt`); the first
   real-data backtest vs 7 baselines (RF/LogReg/Ridge/MLP/LightGBM/XGBoost/random) showed
   the transformer is the best *classifier* (acc 0.719 / F1 0.710) but all models lose
   with costs; **baseline gate not passed** (keeps the live contour closed, TZ-00 §5).
   Improvement criteria + next attempts (incl. DSL indicator-config search):
   `legacy/dev_docs/ai_baseline_report.md`.
4. **pass@1 ≥ 70%** (RAG criterion) — implemented, not measured on a live LLM.
5. **OKX trading contour (TZ-15)** — public market data is live (REST + WS, verified
   against the real venue); private channels, order placement and algo SL/TP stay
   closed until the baseline gate; PG-backed `InstrumentMap` not wired.
6. Manual T-Invest run (TZ-05); aiogram bot, JWT, TLS/tokens, lag metrics (TZ-09/TZ-10).
7. **AI**: OB-encoder batching, <5 ms measurement, real-data training, SIV run.

## PLAN v2 — wide-geometry pivot (approved 2026-09-19) 🎯

Supersedes the old experiment queue. Rationale: see "Findings" below — the old
label profile (TP 2×ATR/SL 1.5×ATR) has negative expectancy net of costs on
every TF (proven by the oracle test), while the **decoupled wide geometry**
(1m OB entries, hour-scale TP/SL) shows in-sample positive expectancy.

**Named risk profiles** now live in `configs/engine.yaml`: `risk_profile: default`
reads the `risk:` block; `--risk-profile wide` (prepare/backtest/dsl_stage0)
reads `risk_wide:` (TP 108×ATR(1m) ≈ 5.9%, SL 27× ≈ 1.5%, hold 480×1m = 8h).

### Phase 1 — validate wide geometry out-of-sample. GATE 1 ⏳

```bash
# 1) build a compact wide-profile dataset for BTC from the shared raw cache
uv run python scripts/prepare_okx_dataset.py --stage worker \
  --bars 1m 15m 1H --base 1m --years 2.5 --assets BTC-USDT \
  --cache-dir data/okx21 --out data/okx21_wide --risk-profile wide
# add ETH/SOL the same way once the okx21 workers stop writing their caches,
# then merge:
uv run python scripts/prepare_okx_dataset.py --stage merge \
  --bars 1m 15m 1H --base 1m --years 2.5 --out data/okx21_wide
# 2) GATE 1: oracle backtest (labels as signals) on the last 15%
uv run python scripts/backtest.py --data data/okx21_wide \
  --model runs/okx7/best.pt --skip-transformer --oracle \
  --risk-profile wide --out runs/okx21_wide/backtest_oracle.json
```
Pass = oracle positive OOS on ≥2 assets → Phase 2. Fail = stage-0 geometry
grid (max ~10 configs), then honest "OB carries no alpha" verdict.

### Phase 2 — full dataset + training. GATE 2

When the okx21 workers finish → merge `data/okx21` (commands kept below),
rebuild the 1m layer as wide, then `train_okx.py --data data/okx21_wide`
(6L×192H, 10 epochs). Success metric: **entry-class WR OOS > breakeven** (not
accuracy). RAM contingency: drop the 1m base if OOM.

### Phase 3 — backtest matrix + threshold grid

`backtest.py --risk-profile wide` vs all baselines + oracle; `--threshold`
0.5…0.7 grid; report cost/TP per slice and per-class entry precision/recall.

### Phase 4 — DSL search (parallel)

`dsl_stage0.py --profile wide` grids (AVSL inversion, atr_period, risk
params), ranked by edge over breakeven; survivors verified with oracle OOS
before any training. Optional `dsl_stage1.py` LightGBM proxy.

### Phase 5 — only after Phases 1–4

MFE/MAE head (model places TP/SL), purged walk-forward CV, PnL-weighted
loss, maker-execution profile (0.02%/side), error analysis by regime.

### Reference: okx21 (default profile) pipeline, kept for comparison

```bash
# 1) merge staged assets -> final split files + meta.json
uv run python scripts/prepare_okx_dataset.py --stage merge \
  --bars 1m 5m 15m 30m 1H 4H 1D --base 1m 5m 15m 1H --years 2.5 --out data/okx21
# 2) train (6x192, 10 epochs)
uv run python scripts/train_okx.py --data data/okx21 --device cuda \
  --max-ob 64 --save runs/okx21/best.pt --log-dir runs/okx21/tb
# 3) backtest vs baselines (84 slices)
uv run python scripts/backtest.py --data data/okx21 --model runs/okx21/best.pt \
  --out runs/okx21/backtest.json
```

8. **TZ-12 final**: ±10% reruns, TA-Lib optional CI job.

## Remaining work order (from TZ-00 §3.2)

1. Local backtest-runner in `main/` + TZ-04 msgspec report contracts
2. TZ-07 pass@1 eval (live Ollama) + `rag_integration` marker (live Qdrant/Ollama)
3. TZ-10 finish: aiogram bot, JWT, live PG in CI
4. TZ-09 finish: live RabbitMQ, TLS/tokens, lag metrics
5. TZ-04/TZ-06 on real data: SIV run, training, baseline gate; OB batching, <5 ms —
   **first training+backtest done, gate not passed**; iterate per
   `legacy/dev_docs/ai_baseline_report.md` (thresholds, costs, horizon, DSL-config search)
6. TZ-12 final: ±10% reruns, TA-Lib CI job
7. TZ-15 finish: private WS channels + order placement (after baseline gate), algo SL/TP, PG `InstrumentMap`

## Quality gates

- Full suite: **2461 passed / 123 skipped / 0 warnings**; ruff + mypy clean
  (only accepted tech-debt: docstrings in `ta/src/overlap/mama.py`).
- **Baseline gate** (TZ-04 §4.6.1) is the project's main filter: nothing is valid without
  passing comparison vs Buy & Hold / logistic regression / RF/XGBoost.
- RAG success: **pass@1 ≥ 70%** (valid DSL ≤ 2 repair iterations).
## Findings 2026-09-19 — где на самом деле ломается edge 🔬

Decisive experiment: added `--oracle` to `scripts/backtest.py` — feeds ground-truth
labels into the simulator (perfect-model upper bound).

- **Oracle LOSES: −74.1% mean / −26.6% on 1H slices** (`runs/okx7/backtest_oracle.json`).
  ⇒ **No parity bug, no model-precision bottleneck: the label strategy itself
  (OB + TP 2×ATR / SL 1.5×ATR) has negative expectancy net of costs.**
- Cost arithmetic per TF (BTC, measured on real cache, round-trip = 0.30%):
  | TF | ATR | TP(2×ATR) | cost/TP | verdict |
  |----|-----|-----------|---------|---------|
  | 1m | 0.037% | 0.075% | **4.0×** | −100% guaranteed for ANY model |
  | 5m | 0.123% | 0.246% | **1.22×** | unwinnable (TP < costs) |
  | 15m| ~0.25% | ~0.5% | ~0.6× | marginal |
  | 1H | 0.621% | 1.242% | 0.24× | only winnable TF |
  The −89.8% vs −90.7% transformer-vs-random gap aggregates 28 slices of which
  half are mechanically unwinnable; all real signal lives on 1H/15m. Gate metrics
  should be computed on cost/TP < 1 TFs only.
- TP/SL geometry grid (stage-0, 1H, BTC/ETH/SOL): TP 3–4×ATR, SL 1.0–1.5×ATR
  (`runs/dsl/stage0_tpgrid.json`) — win rates land **at or below breakeven**
  (e.g. TP3/SL1.5 needs WR>0.405, actual 0.35–0.37). Only ETH TP4/SL1.0–1.5
  scrapes marginally above. ⇒ OB entry signal quality is the binding constraint,
  not TP/SL geometry, not the transformer.
- Note: stage-0 `avg_r` on binary outcomes equals win_rate (no R information);
  fixed `_label_stats` to exclude `outcome==2` rows.

Priority queue reshuffle:
1. **Entry-signal quality** is now the #1 target: stage-0 indicator grids
   (AVSL etc.) score label stats — look for configs with WR > breakeven, then
   verify with `--oracle` in backtest before training anything.
2. **Cost model**: 0.1%/side taker is conservative; maker/limit entries (~0.02%)
   would move breakeven WR from ~0.40 to ~0.35 at TP3/SL1.5 — decide the
   execution assumption explicitly in configs/engine.yaml `risk`.
3. Per-TF reporting: backtest report should include cost/TP per slice and
   per-class entry precision/recall (reviewer note — valid).
4. Purged walk-forward CV and PnL-weighted loss — still queued, but secondary
   to (1)–(2): no loss function fixes a negative-expectancy label.

### Wide-geometry experiment (2026-09-19, 1m BTC, 2.5y, hold <= 480x1m)

Decoupled entry TF from target size: OB entries on 1m, TP/SL at hour+ scale.
Breakeven WR = (SL + 0.3%) / (TP + SL); noise baseline = SL / (TP + SL).

| TP / SL | trades | WR | breakeven | noise | edge vs noise |
|---------|--------|------|-----------|-------|---------------|
| 0.74% / 0.37% | 12856 | 0.319 | 0.602 | 0.333 | -1.5 p.p. |
| 1.49% / 0.37% | 10295 | 0.266 | 0.362 | 0.200 | +6.6 p.p. |
| 2.20% / 0.55% | 8009 | 0.305 | 0.309 | 0.200 | +10.5 p.p. |
| **2.97% / 0.74%** | 6931 | **0.333** | **0.281** | 0.200 | **+13.3 p.p.** PASS |
| **5.94% / 1.49%** | 5663 | **0.372** | **0.240** | 0.200 | **+17.2 p.p.** PASS |

In-sample only; GATE 1 (oracle OOS) decides. Edge grows monotonically with
target size - the OB signal has slowly decaying predictive power that drowns
in 1m noise at short targets. Best configs are worth +0.3..0.7R per trade
net of costs.

### GATE 1 result (BTC, wide profile): FAIL - edge does not survive OOS :red_circle:

`runs/okx21_wide/backtest_oracle.json`: oracle (long labels as signals,
OOS last 15%) = **-74.2%**, 434 trades, WR 0.327, PF 0.464.

Root causes, in order of importance:
1. **Regime decay, not a bug**: OOS only 6/434 trades (1.4%) reach the +5.3%
   TP within 8h - the test window (May-Sep 2026) is flat/down; wide long
   targets need a trending regime. In-sample WR 0.372 (train 0.375 / val
   0.386 / test 0.327) was carried by TP hits in the 2024-25 trend plus
   near-zero hold-exits; label "WR > breakeven" is misleading when most
   trades resolve via max-hold (the breakeven formula assumed TP-sized wins).
2. **Simulator semantics artifact found & fixed**: mapping label action 2
   (short entry) to the sim's exit signal truncated ~75% of oracle trades;
   the oracle now maps long labels only. The label generator and stage-0
   never had this problem (each entry resolves via TP/SL/hold internally).
3. Consequences for the plan: (a) stage-0 must report mean R / EV per trade,
   not WR (hold-exit noise inflates WR); (b) Gate 1 verdict needs the other
   assets + short side + trend_filter variants; (c) walk-forward across
   regimes is now mandatory, not optional.

### Stage 0.5 — strategy search (rule templates, not hand-picked numbers) :white_check_mark:

`scripts/dsl_strategy_search.py` composes candidates from explicit rules -
entry (OB touch / +trend filter up-down) x stop (structural `zone:b` =
behind the block zone +/- b*ATR, or volatility `atr:m`) x target (`k`R of
risk) x hold - and scores each with `generate_labels_from_strategy` in
R-multiple mode: **mean realised R per trade net of costs (EV)**, split by
train/val/test. `--min-risk-atr` rejects entries whose stop is too close
for round-trip costs to be survivable (a cost floor expressed in ATRs).

Run `runs/dsl/strategy_search.json` (BTC-USDT 1m, 2.5y, hold 480,
min-risk-atr 15, 48 candidates / 36 with trades):

- **Every candidate is EV-negative in every split.** Best (short,
  atr:27, 2R): train -0.22 / val -0.22 / test -0.31 R per trade.
- EV ~ -0.22R == the 0.3% round-trip cost expressed in R of a 1.5%-risk
  stop. **Gross edge of the OB-touch entry family is ~zero, and it is
  stable** - the same in all regimes, which also retroactively explains
  the Gate-1 wide-geometry failure without invoking regime decay alone.
- Structural zone stops only work when the zone edge is >=15 ATR away;
  closer stops are pure cost bleed (earlier runs without the floor showed
  -2..-7R). The min-risk-atr floor is therefore a mandatory strategy
  rule, not a tunable nicety.
- Note: `use_structure_filter` is a no-op with base-TF
  `detect_order_blocks` (all blocks carry `structure_label`); it only
  becomes meaningful with HTF/DSL labels at stage 1+. Structure-variant
  rows were duplicates and were removed from the grid.

Verdict: no entry rule from this family is tradable net of 0.3% costs.
The remaining path is exactly the planned one - train the model to pick
the subset of OB entries where EV > +cost (Phase 2) - but now with
honest labels: best candidate (short, atr:27, 2R, hold 480) as the
labeling strategy, EV per trade as the ranking metric, and walk-forward
splits built in from the start.

### Stage 0.5b — indicator-anchored stops as fixed rules: worse :red_circle:

`--stops` now also accepts `anchor:<name>:<b>` rules (AVSL / AVSR /
HiLo activator / Supertrend / Bollinger bands, side-aware, computed
causally via the `ta` package). Result (`runs/dsl/strategy_search_anchors.json`,
56 candidates, BTC 1m 2.5y): every anchor family is *worse* than the
wide ATR stop - best anchor EV -0.75R (avsr) vs -0.22R (atr:27); st/hilo/bb
are -1.7..-4.7R. Anchors sit too close to price: cost-to-risk ratio kills
them. Fixed rules are the wrong tool for these levels.

### Stage 0.7 — stop-selection dataset for the model :white_check_mark:

`scripts/build_stop_dataset.py` builds `data/stop_dataset/BTCUSDT.parquet`:
every OB entry (reference strategy atr:27/2R, 6069 entries, both sides)
is evaluated under a *panel* of 11 stop rules x 2 targets with
generator-equivalent execution (next-open fill+slippage, SL-first,
hold exit, costs net). Features: per-entry distances to every anchor in
ATR units, ATR%, zone distance, OB structure/trend, side.

Key numbers (2R target, full period):
- per-rule EV: atr:27 -0.28, atr:54 -0.15, zone ~-0.19, anchors -0.76..-2.0;
- **oracle-of-choices (best rule per entry, hindsight): train +0.01 /
  val+test -0.02 EV** - the hard ceiling of per-entry stop selection.

Interpretation: a stop-selection model can realistically recover most of
the ~0.28R gap from reference to oracle (i.e. approach breakeven), but
**cannot produce positive EV on its own** - the binding constraint is the
entry signal (gross edge ~0), not the stop geometry. Therefore Phase 2
priorities: (1) entry-filtering model (which OB touches to take at all)
as the alpha source, (2) stop-selection model on top of it as a
cost-recovery layer, (3) cost reduction (maker entries) as the cheapest
+0.07..0.2R. Next: train both models on this table with chronological
splits, then Gate-2 the combo in the oracle.

## Plan v3 — MTF rebase (base TF 1h/4h, 6 candidate families)

Decision: move the base TF off 1m to 1h (primary) / 4h (variant) and
look both up (1w/1d/4h zones, trend, room-to-target) and down (15m/5m/1m
confirmation: sweeps, LTF OBs, impulse). Wide 1m geometry was an
indirect emulation of 1h stops; on 1h the cost-to-risk problem
(-0.2..0.3R) largely disappears. Entry selection stays the alpha source;
regime (trend dir/strength/vol) enters both the features and a Gate-2
requirement (EV>0 per traded regime class).

### Stage A.1 — MTF resampling :white_check_mark:

`ai/src/mtf.py`: deterministic 1m -> 5m/15m/30m/1h/4h/1d/1w via polars
`group_by_dynamic` (epoch-aligned windows). Bars are emitted only when
complete (trailing partial dropped); every row carries
`known_ts = ts + dur` and `asof_rows()` enforces causality for
consumers. Tests: `ai/tests/test_mtf_resample.py` (8 unit tests:
aggregation, incomplete tail, causality, gaps, invalid inputs).

### Stage A.2 — six entry-candidate families :white_check_mark:

`ai/src/candidates.py`: causal detectors on the base TF -
`ob_touch`, `ob_retest` (2nd zone touch), `sweep` (wick pierce
>= b*ATR + reclaim close), `fvg` (3-bar imbalance, entry on return),
`avsl_bounce` (AVSL/AVSR touch + turn bar), `break_retest` (zone break
then re-entry from the far side). `collect_candidates()` runs all six
and dedupes by (entry_idx, side) with priority sweep > ob_retest >
ob_touch > fvg > avsl_bounce > break_retest, flagging overlaps.
Tests: `ai/tests/test_candidates.py` (11 unit tests, synthetic
fixtures, causality + dedup priority).

Live smoke on real okx BTC-USDT 1m cache (379 days): 1h base ->
9093 bars, 415 OBs, **1988 candidates** (fvg 860, sweep 289, ob_retest
284, ob_touch 327, break_retest 228; overlap share 8.2%). 4h base ->
515 candidates. Volume estimate holds: ~2k/yr/asset on 1h, ~6k with
ETH+SOL - enough for the Plan-v3 model once HTF/LTF context features
and regime vectors (stage A.3) are added.

Next: A.3 `build_mtf_dataset.py` (MTF features + regime vector + stop/
TP panel per candidate + execution modes), A.4 purged walk-forward
splits, A.5 regime x family x stop-rule EV matrix.

### Stage A.3-A.5 — MTF dataset built :white_check_mark:

Cache bonus: the build walked OKX pagination to its history limit -
BTC 1m cache grew 545k -> 1.35M bars (~2.5y, back into 2023-24 cycles).

`scripts/build_mtf_dataset.py` + `ai/src/mtf_dataset.py` (pure helpers:
causal rolling percentile, purged splits with embargo, pessimistic
limit fill, nearest-zone distances, SMA trend state; 8 unit tests).
Dataset `data/mtf_dataset/BTCUSDT_1h.parquet`: **3576 candidates (all
6 families incl. avsl_bounce), 235,950 rows, 39 cols**; per candidate:
11 stop rules x 2 targets x 3 executions (market / limit:edge /
limit:mid with pessimistic buffer fill) x purged splits (train/val/
test, hold=48 embargo, 1650 rows in gaps).  Features: base context,
regime vector (SMA50 z/slope, causal rolling percentiles of ATR% and
BB width), HTF 4h/1d asof trend + zone distances in base ATRs, LTF 15m
asof impulse/volume.  Note: `_compute_anchors` AVSL/AVSR is all-NaN on
resampled frames (talib SMA poisons through warm-up NaNs) - script has
a numba `nan_policy='ffill'` rebuild (`_anchors_nan_safe`).

A.5 headline (EV pivot, market, 2R, net):
- rule `atr:14`: all families -0.15..+0.08 everywhere - dead;
- rule `zone:1.0` (stop behind zone): train **+0.17..+0.26**, val
  **+0.25..+0.38**, test **-0.07..+0.02** - every family positive in
  train+val, then regime decay in the 2026 test window (GATE-1
  artifact again, now visible in every family).

Interpretation: zone-stop geometry on 1h has real positive EV outside
the adverse regime - costs no longer bind.  The model's job is exactly
the plan's premise: regime conditioning (which regime trades which
family) + entry filtering + limit execution layer (fill rates 33-74%
by family at zone edge).  Next: B (model towers) + Gate 2 per regime.

### Stage B — model towers, first Gate-2 numbers :white_check_mark:

`ai/src/mtf_model.py` (pure helpers: reference/stop row selectors,
LightGBM feature assembly with native categoricals + NaN pass-through,
EV-threshold calibration, per-regime Gate-2 table, stop-policy EV;
7 unit tests) + `scripts/train_mtf_model.py` (LightGBM towers).
Outputs: `data/mtf_model/{entry,stop,tp}_head.txt` + `report.json`.

Gotchas found: polars NaN comparisons pass `> 1.0` filters and NaN
mean() never wins `>` - invalid rule rows (anchor on the wrong side,
zone stops on zoneless avsl_bounce candidates) must be dropped with
`is_not_nan()` before any EV math.  tp head (E[r_net] regression) is
dead: spearman ~0 on val/test - dropped as signal source.

Results (BTC 1h, purged splits, net EV per trade, market, 2R):

| config | train | val | test |
|---|---|---|---|
| fixed zone:1.0 (no model) | +0.21 (2060) | +0.30 (704) | **-0.02** (679) |
| stop-head policy (argmax rule) | +0.44 (1883) | +0.38 (648) | **+0.25** (640) |
| + entry filter (thr 0.28 on val) | +0.46 (1197) | +0.38 (475) | **+0.25** (469) |

Entry head alone: improves test from -0.02 to -0.00 and shows the
regime split (test: up +0.06 / down -0.06 / range -0.05), but does not
rescue the adverse window.  The stop head carries the signal: choosing
the stop rule per candidate turns the 2026 test window positive -
val and test agree (+0.38 / +0.25), n=640, per-trade SE ~0.055R so the
effect is ~4.5 sigma before multiple-selection caution (argmax over 11
rules per candidate inflates; the honest number needs nested CV or a
tradeable re-fit, see next stage).

Interpretation: stop-rule geometry is the alpha carrier - "where is
the structural invalidation" is predictable per candidate, and the
entry filter's job is capacity/quality (same EV, -27% trades), not
direction.  Next: tighten honestly (nested/refit policy, per-regime
rule tables), limit-execution layer on the policy subset, then Gate 2
writeup vs the +0.02R baseline bar.

### Stage B.2 — hardening: the alpha survives honest tests :white_check_mark:

Two data/eval bugs found and fixed first:
1. **limit risk collapse**: with a limit fill near an anchor stop,
   `risk_unit = |fill - sl|` degenerates and R-multiples explode
   (values like -17R).  Fix: rows with `risk_unit < 0.5*ATR` are
   marked invalid (`r_net = NaN`) at build time; dataset rebuilt.
2. **candidate key**: long and short candidates share `entry_idx` -
   all per-candidate policies now key on `(entry_idx, side)`.

Hardening results (BTC 1h, market, 2R, net EV):

| policy | train | val | test |
|---|---|---|---|
| fixed zone:1.0 | +0.20 | +0.30 | -0.02 |
| stop-head policy (LGBM) | +0.41 (2114) | +0.37 (717) | **+0.21** (716) |
| + entry filter | +0.60 (1368) | +0.42 (534) | **+0.24** (547) |
| no-ML rule table (regime x side -> rule) | +0.36 | +0.36 | **+0.23** (670) |
| random rule | -0.01 | +0.01 | -0.09 |
| oracle ceiling | +0.93 | +0.98 | +0.85 |

Paired bootstrap policy-vs-fixed on test: diff **+0.234R**, CI
[0.175, 0.292], p(diff<=0) ~ 0 (train +0.21 CI [0.18,0.23]; val +0.08
CI [0.03,0.12], p=0.002).  The effect is not an artifact of one split.

**The headline artifact is embarrassingly simple**: a lookup table
`regime_dir x side -> stop rule` fit on train-only counts (best-EV
rule with a 30-trade floor, zone fallback) matches the LGBM policy on
test (+0.23 vs +0.21) with zero ML.  The LGBM/entry-filter stack adds
mostly capacity control (-27% trades at equal/higher EV).  The rule
table chose e.g. `down|long -> anchor:st`, `up|long -> zone:0.5`,
`range|long -> zone:0.5`.

Limit execution on policy picks (test): limit:edge fill 53% /
EV|filled +0.29 / EV per signal +0.15; limit:mid fill 71% / +0.24 /
+0.17; market +0.21 per signal.  Costs do not bind - market execution
is fine; limits buy entry quality, not EV.

Gate-2 assessment vs the +0.02R bar: **PASSED with the simple rule
table + entry filter stack** (test +0.24R/trade over ~550 trades in
the adverse window, all baselines beaten, CI clear of zero).  Caveats:
single asset (BTC), single base TF (1h), regime labels from the same
causal features (no lookahead by construction), argmax-selection
inflation bounded by the table-vs-LGBM agreement.  Next: multi-asset
replication (ETH etc.), 4h base TF, then portfolio layer.

### Stage B.2.1 — reversal-safety + B.3 ML upgrades :white_check_mark:

**Reversal protection**: long/short candidates sharing a bar were
merged by every per-candidate policy (grouped on `entry_idx` alone) -
fixed in B.2 ad hoc, now institutionalised: `candidate_key(df)` in
`ai/src/mtf_model.py` is the single key builder, used everywhere in
`train_mtf_model.py`; regression tests pin long+short same-bar
separation and paired-bootstrap alignment when one side's rule set is
NaN.  Requirement recorded for the future execution layer (stage D):
explicit transition tests long->flat->short, single-signal reversal,
same-bar SL + reverse.

**Risk metrics** added: `trade_curve_stats` (t-stat, max DD in R,
profit factor) - 4 tests.  New `ml_upgrade` report section (calibrated
on val only, evaluated on test):

| variant | val EV / t / DD | test EV / t / DD | test PF |
|---|---|---|---|
| policy (baseline) | +0.37 / 15.7 / 6.2R | +0.21 / 7.3 / 15.1R | 1.95 |
| consensus gate | +0.50 / 20.4 / 3.4R | +0.46 / 14.1 / 8.0R | 5.44 |
| **consensus + sized** | **+0.55 / 21.5 / 2.6R** | **+0.51 / 15.3 / 5.3R** | **6.51** |
| sized policy (train-tertiles) | +0.43 / 18.2 / 3.6R | +0.28 / 9.7 / 9.5R | 2.46 |
| table fallback on disagreement | +0.35 / 12.4 / 17.9R | +0.21 / 7.2 / 24.0R | 2.00 |

Answer to "can ML improve": **yes** - not by replacing the table but
by (a) trading only the LGBM/table consensus (test EV x2.2 at half the
trades, DD halved, PF 5.4), and (b) confidence-based sizing (train
probability tertiles -> 0.5/0.75/1.0 trade fractions; val-selected,
test-transferred).  The two effects STACK: consensus+sized reaches
test +0.51R (2.4x policy, DD /2.8, PF 6.5).  Fallback-to-table on
disagreement does NOT help (skipping is better than hedging).  Both
val and test agree on the variant ranking: consensus+sized >
consensus > sized > policy > fallback.

Remaining research (not started): pairwise ranking objective for the
stop head (full-panel supervision), joint (rule x target) action
space.  Next: stage C - multi-asset replication (ETH + 4h base).

### Stage C (in progress) — replication :construction:

**BTC 4h base TF** (868 candidates vs 3576 on 1h; test n=174):
policy EV +0.444 vs random +0.05, table +0.11, oracle +0.84 - level
is higher (bigger R multiples per bar), but the paired policy-vs-zone
edge on test is marginal: +0.052, CI [-0.012, +0.118], p=0.059 (val
was clear: +0.167, CI [0.095, 0.247]).  Reading: at 4h the zone rule
already captures most of the value and few candidates leave little
room for pick-selection to show incremental edge - the 1h consensus
gate story does NOT yet replicate at 4h with this sample size.
Consensus gate on 4h: val-selected, test 0.466 vs policy 0.444 (n=63,
DD 0.3R - too few trades to celebrate).  Rule table itself differs
from 1h's (geometry interacts with TF) - argues for per-TF tables.

### Stage C — replication :white_check_mark:

**ETH-USDT 1h** (3384 candidates, 223k rows; test n=725): replicates
BTC 1h, stronger on every metric:

| metric (test) | BTC 1h | ETH 1h |
|---|---|---|
| policy EV | +0.211 | +0.362 |
| policy-vs-zone paired diff (CI) | +0.234 [0.175, 0.292] | **+0.300 [0.259, 0.345]**, p=0 |
| rule table EV | +0.230 | +0.283 |
| random / oracle | -0.09 / +0.85 | -0.07 / +0.86 |
| consensus EV (n) | +0.462 (319) | +0.469 (388) |
| consensus+sized EV | +0.508 | **+0.538** |

Three replication findings:

1. **The no-ML rule table is asset-invariant at 1h**: ETH's fitted
   table matches BTC's cell-for-cell (up|long=zone:0.5, range|long=
   anchor:st:0.5, down|long=anchor:st:0.5, up|short=anchor:st:0.5,
   down|short=zone:0.5, range|short=zone:1.0, unknown|=zone:1.0).
   The alpha carrier is stop-rule geometry, not asset-specific.
   (The 4h table DIFFERS from 1h - geometry is TF-specific, so per-TF
   tables are required, per-asset ones are not.)
2. **Val->test transfer of the variant ranking holds on both assets**:
   consensus+sized > consensus > policy everywhere, always
   val-selected and test-confirmed.
3. **The consensus gate is not BTC-specific**: it improves EV on ETH
   too (+0.538 vs +0.362 policy, DD comparable, ~half the trades).

**BTC 4h** (868 candidates; test n=174): policy EV +0.444 vs random
+0.05, table +0.11, oracle +0.84 - level is higher (bigger R per
bar), but the paired policy-vs-zone edge on test is marginal: +0.052,
CI [-0.012, +0.118], p=0.059 (val was clear: +0.167, [0.095, 0.247]).
Reading: at 4h the zone rule already captures most of the value and
few candidates leave little room for pick-selection; the consensus
gate direction is consistent (test 0.466 vs 0.444) but n=63 is too
small to call.  4h stays a secondary TF.

Stage C verdict: **strategy generalizes across assets at 1h**.  The
core artifact is per-TF: rule table (8 cells) + consensus gate +
confidence sizing, all calibratable on train/val alone.  Remaining:
pairwise ranking stop head, (rule x target) action space, portfolio
layer with the long->flat->short state machine tests (stage D).

### Stage D.2 — EntryExitTransformer A/B :x: (rejected, cheaply)

Question: does the repo's existing EntryExitTransformer (dual encoder
time-series + order blocks, ai/src/transformer.py) add signal as a
third voice in the consensus gate?  Protocol: retrain it on MTF rules
(not its legacy per-bar action labels) - windows of 64 1h bars ending
at each candidate's decision bar, normalised OHLCV+ATR+side channels,
target = "best stop rule wins" (best market r_net > 0), same purged
splits; probability p_trf then gates the consensus subset with a
val-calibrated threshold; two-sample bootstrap of gated-vs-dropped EV.

Files: scripts/build_transformer_dataset.py,
scripts/train_entryexit_mtf.py (small config: 2 layers, hidden 64 -
only ~2.1k train windows), scripts/eval_trf_ab.py.

Results (BTC 1h): model quality - train AUC 0.60, val AUC 0.40 (below
coin flip), test AUC 0.57.  Gate effect - val: gated EV +0.498 vs
dropped +0.495, diff +0.004, CI [-0.10, +0.11] (no separation; val
grid flat over all thresholds).  Test: gated +0.577 (n=161, DD 2.2R)
vs dropped +0.345, diff +0.232, CI [0.11, 0.36] - looks great, but
**val did not predict it**, so by our own protocol (val decides,
test confirms) this is period-specific noise, not a validated edge.
Taking it would be selection on test.

Verdict: **transformer voice rejected**.  Confirms the earlier read:
at ~3.5k candidates the flat MTF features already carry the context,
and a sequence encoder has nothing reliable to add.  The experiment
cost ~1 hour and the infrastructure (window builder aligned to MTF
candidates) is reusable for the ranking stop head.  Kept for the
record; not wired into the production stack.

### Findings synthesis — where the alpha actually lives

Correction of an earlier simplification ("LGBM predicts stops and
takes"): **only the stop head predicts anything.**  The tp head is
dead (spearman ~0); the entry head barely moves test EV (-0.0215 ->
-0.0103, n 677 -> 513 - it is capacity control, not alpha).  The
legacy OKX result (transformer best classifier, acc 0.719 vs 0.703)
was won on a mechanically untradeable dataset (cost/TP ~ 4x on 1m) -
a classification win worth nothing.

| layer | alpha carrier | role |
|---|---|---|
| candidate search | rule-based (OB, sweep, FVG, AVSL...) | finds entries |
| **stop choice** | **LGBM stop head + rule table** | the alpha: -0.02 -> +0.21 test |
| entry filter | LGBM entry head | capacity control (-0.02 -> -0.01) |
| position size | consensus gate + confidence sizing | +0.21 -> +0.51 test |
| take-profits | nobody | tp head dead; TP fixed at 2R |
| transformer | nobody | rejected (val AUC 0.40) |

The alpha is in the **problem formulation** - predicting stop-rule
geometry per candidate, not entry or take-profit timing.  The
transformer lost not because "transformers are worse" but because on
3.5k examples with the same tabular features a sequence encoder has
nothing to learn, while trees extract the signal.  Its realistic path
back: the ranking task (11 rules x 3560 candidates ~ 39k pairs) or
10-30x more data.

#### D.2 roadmap — four legitimate uses of the rejected artifact

Not "replace LGBM" but "do something else".  Return only with a new
hypothesis; "try a smaller learning rate" is not a hypothesis.

1. **Ranking head** (HIGH; after nested CV, state machine,
   walk-forward): predict the best stop rule out of 11 per candidate
   - 3560 x 11 ~ 39k pairwise pairs vs 3.5k classification examples;
   comparative objective (RankNet/LambdaRank), tabular features.
   Success criterion: beats LGBM stop head on test.  Win ->
   rehabilitated as an extra voice; lose -> topic closed for good.
2. **Attention diagnostics** (MEDIUM; anytime, cheap): inspect what
   the trained encoder attends to before the decision bar.  A
   concentrated pattern (e.g. last 3-5 bars) -> hypothesis features
   for LGBM; flat attention -> no temporal structure, trees right.
   Success: a new feature that improves LGBM val EV.
3. **Warm-start** (LOW): encoder weights as init for future tasks on
   the same OHLCV windows (volatility, MFE/MAE, regime).
4. **Reference implementation / README** (LOW): an honest
   build->train->A/B->reject example on numeric data.

Forbidden: returning it to prod as-is, hyperparameter fishing, using
it as a "second opinion" in the consensus gate (tested in D.2),
presenting it as an achievement.

### Stage D.1 — pure state machine :white_check_mark:

Spec (ai/src/state_machine.py, documented in module docstring):
signal at bar d fills at d+1; one slot; while in position ALL new
signals skipped (reverse ignored by default); same-bar exit+signal
skipped (SL-first pessimism); cooldown blocks N bars after exit;
same-bar signals resolved by stop-head priority; exit_idx now stored
per dataset row (builder patched, candidate counts unchanged byte-
for-byte: BTC 3576/235950, ETH 3384/223344).

Tests: 7 transition tests (SL close, reverse ignored / allowed,
same-bar SL+reverse, cooldown, priority, isolated-equivalence).

Replay on BTC 1h consensus picks (cooldown=0, reverse off):

| split | isolated | machine | EV gap | DD |
|---|---|---|---|---|
| val | +0.496 (n=385) | +0.542 (n=154) | **+9.3%** | 3.4 -> 3.0R |
| test | +0.462 (n=319) | +0.454 (n=149) | **-1.8%** | 8.0 -> 5.7R |

Reading: the isolation illusion costs only ~2% EV on test (and helps
on val), because consensus picks are sparse (~half the trades get
skipped for occupancy but the machine's priority-by-confidence
filters replace them with nothing bad).  DD improves in both splits.
The feared 20-40% EV loss does NOT materialise at 1h consensus
frequency.  Next: D.3 execution semantics (pessimistic fill), then
D.2 portfolio layer (BTC+ETH, correlation limits, kill-switch).

### Stage D.3 — execution semantics :warning: (diagnosed: pessimistic criterion failed, root cause identified)

Pre-D.3 checks: skipped trades have LOWER stop-head confidence than
taken on all splits (p 0.830/0.779 train, 0.831/0.763 val, 0.809/0.807
test) - occupancy is a quality filter, not random loss; train replay
gap +3.0% (not +10%) => the val +9.3% is small-n noise, honest gap
~0 +/- 0.05R; priority is calibrated on train, no circularity.

D.3 dataset: builder now stores per-trade execution details (fill/sl/
tp prices, risk_unit, atr, exit_reason/price).  Pessimistic cost model
on state-machine trades: entry slip x2, SL exit slip x2 (SL is a
market order), gap-through-stop buffer 0.25xATR (base) / 0.5xATR
(stress); TP stays a free limit fill.

| split | optimistic | pess_base | pess_stress |
|---|---|---|---|
| val | +0.542 | +0.279 (ratio 0.51) | +0.153 (0.28) |
| test | +0.454 | **+0.150 (ratio 0.33)** | +0.016 (0.03) |

**Criterion EV_pess/EV_opt >= 0.75 FAILED** (0.33 base).  Root cause:
tight stops.  Consensus picks run risk_unit ~0.4-0.5% of price, so
every fixed % of price is ~0.25R; the generator ALREADY charges
~0.5-0.6R of costs per trade (0.25% of price), and doubling slippage
adds another ~0.25-0.3R.  The strategy is not execution-fragile
because of bad fills - it is fragile because its edge (~1R gross) is
only ~2x its cost base.

Consequences and levers (in order):
1. realistic live is likely BETWEEN optimistic and pess_base (0.05%
   entry slip on a 0.01%-spread perp is already conservative; gaps of
   0.25 ATR/hit are rare) -> live-EV estimate ~ +0.15..+0.45R/trade;
2. the structural fix is WIDER stops: cost in R scales as
   price_cost/risk_unit - ranking head should be cost-aware (prefer
   zone:1.0/atr stops over zone:0.5 when EV-net is close);
3. maker entries (limit:edge) cut the entry cost but fill ~50-70% -
   revisit only after D.2;
4. D.2 portfolio decisions must use pess_base numbers as planning
   baseline: test +0.150R/trade is the defended number, not +0.454.

### Stage D.6 - joint (stop rule x TP target) ranking :x: REJECTED

Ranked all (rule, target) pairs - targets 2R/3R in the panel - by
pess R (same protocol as D.4).  joint+gate: test pess +0.302
(D.5 baseline +0.490), ungated +0.078; val/test divergence too.
Conclusion: TP must come from the MFE path model (D.5), not from the
ranking objective - terminal R is too noisy a label for target
choice and the ranker overfits it.  Priority-4 reserve is NOT in
joint ranking; D.4 ranker (stops) + D.5 adaptive TP (MFE) remains
the stack.  Planning number unchanged: test pess +0.490R.

D.6b retry (label/objective/regularization): strong-reg LambdaRank
+0.319, regression +0.119 - both below D.5 baseline; r_reach label
(min(mfe,target)) degenerate without per-group normalization (n=1).
Joint ranking rejected on 3 configurations; remaining lever would be
group-normalized reach labels, low expected value - parked.

### Stage D.5 - MFE/MAE head, adaptive TP, regime rule (done, mixed)

Builder now stores TP-free path stats per row (mfe/mae in ATR and R,
before SL hit; _excursions in build_stop_dataset).  LGBM regressor
predicts MFE (R) from entry-time features only (val RMSE 1.18R).
TP scenarios re-simulated on raw 1m->1h bars (resample_ohlcv; sanity
vs stored r_net: mean |diff| = 0.009R), ranker+gate picks, D.3-style
pessimistic costs (no gap term here - comparisons are internal):

| TP rule | val pess | test pess | test n | test DD |
|---|---|---|---|---|
| fixed 2R (baseline) | +0.677 | +0.579 | 106 | 2.9R |
| regime 3R/1R | +0.676 | +0.571 | 108 | 2.9R |
| adaptive k=0.8, RR 1/3..1 | +0.644 | +0.588 | 114 | 1.4R |
| adaptive scalp RR 1/5..1/3 | +0.623 | +0.542 | 116 | 1.4R |

UPDATE (gap term unified with D.3/D.4 + bootstrap CI): fixed 2R test
pess +0.474 CI[+0.390,+0.547] ratio 0.68; adaptive k=0.8 RR 1/3..1
+0.490 CI[+0.427,+0.540] DD 1.4R vs 3.4R; diff CI [-0.113,+0.082] ->
EV statistically indistinguishable, DD win stands.  Unified planning
number (ranker+gate, gap incl., adaptive TP): test pess +0.490R.
Verdicts: (1) regime-conditioned TP REJECTED (noise-level change);
(2) adaptive TP holds EV while cutting DD ~2x and adding trades -
the RR 1/3..1 config is the best risk-adjusted choice; user-spec
scalp RR 1/5..1/3 trades most with -6% EV, useful for frequency.
(3) MFE is predictable enough to TIME exits, not to add EV - same
pattern as the stop head.  Pending: fair transformer fight (same tabular features and cost/rank
protocol - the original comparison was handicapped); n=106-116 means
only DD differences are interpretable, EV diffs need CI (done above).
Next priorities: fair transformer fight -> cost-aware ranking for
stops (adaptive TP is already the cost-aware exit layer) -> D.2.

### Stage D.4 — cost-aware ranking head :white_check_mark: (criterion PASSED)

LambdaRank LGBM (300 trees, groups = candidates) over the 11-rule
panel (32787 rows); label = pess_base R from D.3 (planning metric by
construction); features = stop-head set + risk_pct + cost_R.
Replay (state machine, BTC 1h):

| head (gate) | val pess | test pess | test ratio | test n | test DD |
|---|---|---|---|---|---|
| stop-head + table (D.3) | +0.279 | +0.150 | 0.33 | 149 | 12.6R |
| ranker, no gate | +0.258 | +0.227 | 0.66 | 86 | 2.3R |
| **ranker + table gate** | **+0.275** | **+0.332** | **0.68** | 80 | **1.1R** |

Criterion (test pess > +0.25R, ratio > 0.5): PASSED (+0.332, 0.68).
Planning number up **+122%** vs D.3 baseline (+0.150 -> +0.332), DD
12.6R -> 1.1R, trades -46% (0.6 -> 0.3/week on BTC alone -> D.2
portfolio layer is now mandatory for frequency, not optional).
Caveats: single asset, single seed, no nested CV yet - treat as
hypothesis confirmed on val+test, not as final. Script:
scripts/d4_ranking.py.

D.3 -> D.4 dependency confirmed: ranking the SAME rules by pess R
flips the pick toward wider stops and repairs the pessimistic ratio.

**D.3 -> ranking dependency:** tight stops (risk_unit ~0.4-0.5%) burn
~0.3R/trade in costs.  Structural fix - cost-aware ranking:
cost_in_R = price_cost / risk_unit(i, j); prefer wider stops at
close EV-net.  This is a NEW hypothesis with a measurable criterion
(test pess_base EV > +0.25R, ratio > 0.5), not hyperparameter
fishing.  Ranking runs BEFORE / in parallel with D.2: it determines
whether the portfolio layer is worth building at all.  Planning
number to present: +0.150R (pess_base), never +0.454 (optimistic).
Realistic live target after ranking + D.2 + nested CV + walk-forward:
+0.10..0.20R/trade.


**Attention diagnostic run** (scripts/attention_diagnostics.py, val+
test windows, layer-0 self-attention, heads averaged, query = decision
bar): entropy 5.98 vs 6.00 max bits - attention is essentially
UNIFORM.  Top offsets are the oldest bars (-49..-60, a positional
artifact), mass on the last 5 bars is 0.062 vs 0.078 uniform
expectation.  No concentration near the decision bar => no learnable
local temporal structure for features.  Two readings, both
conclusion-preserving: (a) the window carries nothing the flat
features don't; (b) a model that failed to learn (val AUC 0.40) can't
show structure either way.  Item 2 result: no new LGBM features
mined; the sequence-vs-table question is settled for this data size.















### Repo restructure (2026-09-19)

After D.12 the repo was rebuilt around the live research pipeline:
- **Archived to `legacy/`** (documented in `legacy/MANIFEST.md`, nothing deleted):
  the former monorepo packages (dsl, strategies, infer, rag, risk, backtest,
  main, tinvest, contracts, migrations, docker/alembic infra), 13 legacy/
  superseded scripts (train_*, eval_*, dsl_*, d6b, d7, replay, run_pipeline,
  attention_diagnostics, build_transformer_dataset), 8 dead ai modules
  (bundle, contracts, dataset, device, losses, metrics, quickstart, training)
  and their test files.
- **Flattened**: `ai/src/*` -> `ai/*` (one layer less); `marketdata/` folded
  into `ai/marketdata/`; okx fetch revived as `ai/marketdata/okx_fetch.py`
  (it is on the live data path).
- **Renamed scripts** (d-prefixes dropped, artifacts keep historical names):
  d3->execution_costs, d4->ranking_baselines, d5->adaptive_tp,
  d6->sim_engine, d8->matrix_2x2, d8b->wf_ab, d9->portfolio, d9b->robustness,
  d10->nested_cv, d11->admission, d12->maker_entry. Stop-rule engine
  extracted from the archived dsl_strategy_search into `scripts/zones.py`.
- **Root now**: ai/ scripts/ tests/ ta/ dsl/ (minimal subset for ta)
  legacy/ data/ runs/ dev_docs/ + meta files. 15 dirs -> 9.
- **Config**: uv workspace members [ai, ta]; pytest testpaths=[tests];
  mypy strict on ai; CI lint = strict (ai, tests, dsl) + F-class (scripts).
- **Tests**: live suite pruned to 93 kept + 27 new unit tests for the core
  (sim_engine cost model, maker_entry fee/geometry, zones stop rules) =
  118 passed / 2 skipped. Full smoke after restructure: wf_ab.py
  reproduces A +0.401 / B +0.450 / 2891 signals exactly.
- Found and fixed along the way: missing numpy.typing import in
  ai/candidates.py (F821), orphan dead code after return in
  ai/candidates.py, missing niquests dep declaration (ai/pyproject).

### Repo restructure v2 (2026-09-19, same day)

Post-restructure audit pass:
- **`configs/ai.yaml` restored** — it had been dropped during v1 (the
  configs/ dir was inspected for *.py only). It is required by
  `load_config(risk_profile=...)` in build_mtf_dataset / build_stop_dataset /
  prepare_okx_dataset; without it the builders crash. Back in place from
  git history, verified `load_config(risk_profile='wide')` works.
- **Transformer fully archived**: `ai/transformer.py` ->
  `legacy/ai/transformer.py` (matrix_2x2 has its own inline TRF, so the
  module had zero live importers); tests/test_transformer.py and the two
  transformer-reference tests in test_ob_pipeline.py ->
  `legacy/tests_ai/`; `ai/docs/` (old transformer-system docs) ->
  `legacy/ai_docs/`; transformer-only conftest fixtures
  (sample_batch / model_params / sample_action_outcome_labels /
  sample_parquet_files) removed; tensorboard + torch-directml/onnx extras
  dropped from ai deps (torch stays: matrix_2x2 uses it).
- **Dead locals removed**: unused `sign` in the pess-helpers of
  sim_engine / ranking_baselines / adaptive_tp / execution_costs;
  unused `seq_len`/`cache`/`cfg` in prepare_okx_dataset's split-stage;
  stale T-Invest mentions dropped from prepare_okx_dataset docstrings.
- **`dsl/` restored in full**: v1 had replaced the original dte-dsl
  package with a hand-made 5-file subset; the full package (engine,
  providers, docs, own suite of 26 tests) is live again at `dsl/`,
  workspace member, tests in the default run and CI. Ghost `pandas`
  dependency declared explicitly (root + ai pyprojects).
- **Validation**: 266 passed / 6 skipped (112 research + 154 dsl,
  6 transformer tests left with the module), mypy strict clean,
  ruff clean incl. F/E9 on scripts;
  smokes byte-identical: wf_ab A +0.401 / B +0.450 / 2891 signals,
  REPLACE-low +466.0R / 2.44R, maker lift -0.414.

### NEXT

1. **Data expansion** (more assets incl. low-liquidity alts, longer history
   per asset, 15m bars; LGBM only): the data path
   (prepare_okx_dataset -> build_mtf_dataset/build_stop_dataset) is the
   thing to scale; watch the candidate yield on illiquid names.
2. **Live execution layer**: OKX adapter implementing the REPLACE
   admission rule (D.11) + state machine, market entries; paper trading
   first. The archived `legacy/packages/okx/` design (ws/executor/signing,
   tested) is the starting point.

### Stage D.7 - FAIR transformer fight :x: (fourth rejection, now fair)

All four equalizers applied (scripts/d7_trf_fair.py): same 33+3
features broadcast over a 64-bar window (raw OHLCV channels kept),
same pess-R label, RankNet over candidate groups (LambdaRank
protocol), same gate + unified d6 simulator, fixed TP for both heads.  Arch:
2 encoder layers, 4 attention heads per layer, d_model 64, FFN 256,
dropout 0.1, mean+last pooling, ~110k params.
Training protocol (upgraded after review): warm-up 2 + cosine decay,
weight decay 1e-4, EARLY STOPPING patience 5 on val ranknet loss,
best-checkpoint restore, max 50 epochs.  Curve (runs/d7/loss_curve.json):
best val 0.6791 at epoch 4, stop at 9; train loss kept declining
(52.2 -> 50.1) while val oscillated up -> mild overfit after epoch 4.
The earlier fixed 8-epoch run was slightly past optimum, same regime.
Results at best checkpoint: val pairwise AUROC 0.558 (crit > 0.55:
nominally passed, still chance+eps; was 0.40 handicapped - fairing
lifted discrimination, ceiling did not move).  Replay: TRF test pess
-0.134R (n=28, ratio 3.11) vs LGBM +0.349 (n=80, ratio 0.70);
bootstrap LGBM-TRF diff CI [+0.234, +0.786] - excludes zero, LGBM
decisively better.  Alive requires ALL criteria; EV fails hard.  Attention-entropy diagnostic
technically broken (SDPA backend returns no weights -> NaN) - moot:
the EV criterion already failed hard.  Pre-registered 70/30 forecast
confirmed: 4th structural rejection, now with a full training curve.
Sequence context adds nothing on top of tabular features at this data
scale.  PRE-REGISTERED (not run): scale-up to 4 layers / 128 dim /
8 heads at n=3574 candidates will yield EV <= 0 (440k params on 3574
examples = 8 examples/param -> overfit); revisit only at 30k+
candidates (ETH+SOL, 15m base).  Transformer roadmap stays parked.

### Stage D.8 — 2x2: per-asset vs multi-asset x LGBM vs TRF :white_check_mark: (causal decomposition)

Motivated by the confound in "multi-asset": model and data volume change
together unless isolated.  Matrix (scripts/d8_2x2.py, runs/d8.log):
A = per-asset LGBM, B = multi-asset LGBM (+asset_id), C = per-asset
FairTrf (d7 recipe), D = multi-asset FairTrf (asset code in tab vec).
Data: BTC 3,574 + ETH 3,384 + SOL 3,663 = 10,621 candidates (97,492
rows; ETH rebuilt to current schema, SOL built fresh).  Same pess-R
label, per-asset gate, unified sim, state machine.

| cell | BTC | ETH | SOL | POOLED |
|------|-----|-----|-----|--------|
| A | +0.254 | +0.211 | +0.398 | +0.296 (n=226, dd 2.9R) |
| B | +0.298 | +0.406 | +0.518 | +0.411 (n=248, dd 3.0R) |
| C | -0.151 | +0.315 | -0.603 (n=2) | +0.072 (n=46, dd 5.7R) |
| D | -0.052 | +0.121 | +0.333 (n=5) | +0.067 (n=73, dd 6.7R) |

Isolation (bootstrap 1000, pooled): **D-B = [-0.507, -0.188]** (model
effect strongly against TRF); **D-C = [-0.248, +0.237]** (data effect =
ZERO: x3.5 data moved TRF not at all, while the same data lifted LGBM
+0.296 -> +0.411).  Causal decomposition: the bottleneck is the model's
inductive bias on tabular geometry features, not data volume.  Verdict:
transformers rejected for THIS task/features/n; revival paths are new
feature classes (order flow, microstructure) or task-specific
architectures (attention between events, not bars) - both research, not
scale-up.  Scale-up stays dead even at 30k+ with the same features
(D-C=0 already showed this at 10k).  Pre-registration formally stands,
expectations lowered accordingly.

Practical yield: **cell B** - multi-asset LGBM beats per-asset on every
asset (BTC +0.254->+0.298, ETH +0.211->+0.406, SOL +0.398->+0.518):
pooling gives trees cross-asset statistics on stop GEOMETRY (universal),
not direction (asset-specific) - consistent with "trading geometry, not
direction".  Caveat: B-A measured on one split; trade-level bootstrap
understates regime variance -> B is a baseline CANDIDATE until
walk-forward confirmation (D.8b).

### Stage D.8b — walk-forward A vs B :white_check_mark: (upgrade confirmed, 6/8)

Pre-registered decision rule: B>A pooled in 6+/8 folds -> accept, 4-5
ambiguous, <=3 -> artifact.  Design (scripts/d8b_wf_ab.py,
runs/d8b/wf_folds.json): 8 folds x 56 days over Mar 2025 - Sep 2026,
expanding train, 7-day embargo, gate refit per fold on fold-train,
state machine slots reset at fold boundaries (path-dependence
approximation).

| fold | start | A | B | winner |
|------|-------|---|---|--------|
| f0 | 2025-07-07 | +0.602 (n171) | +0.521 (n158) | A |
| f1 | 2025-09-01 | +0.480 | +0.543 | B |
| f2 | 2025-10-27 | +0.176 | +0.376 | B |
| f3 | 2025-12-22 | +0.428 | +0.494 | B |
| f4 | 2026-02-16 | +0.329 | +0.447 | B |
| f5 | 2026-04-13 | +0.385 | +0.336 | A |
| f6 | 2026-06-08 | +0.310 | +0.369 | B |
| f7 | 2026-08-03 | +0.314 | +0.399 | B |

**B wins 6/8 pooled** (threshold met).  WF totals: B +0.450R (n=1040,
dd 3.2R) vs A +0.401R (n=980, dd 3.9R).  Per-asset fold wins:
BTC 7/8, ETH 6/8, SOL 5/8 - the edge is broad, not one-regime (the two
A-folds are early-train f0 and chop f5, and even there B never
collapsed).  A-B diff is regime-dependent: fold-level diffs range
-0.08..+0.20, so quote B conservatively as +0.40-0.45R, not +0.411.
DECISION: multi-asset LGBM (B) accepted as the ranking head of the
champion stack; portfolio math (D.2) should use WF-B numbers
(+0.450R pooled pess, dd 3.2R), never the optimistic single-split ones.

### Stage D.2b — portfolio layer (BTC+ETH+SOL) :white_check_mark: (p95 DD 2.6% << 30% flag ok)

Inputs: WF-B per-trade series (runs/d8b/wf_trades.parquet, 1040 trades,
Jul 2025 - Sep 2026; scripts/d9_portfolio.py).

Correlations, two lenses (scripts/d9_portfolio.py):
- PRICE daily-log-return corr: BTC-ETH +0.86, BTC-SOL +0.83, ETH-SOL
  +0.87 -> ONE cluster (>0.8 threshold).  Cluster limit = max 2
  concurrent positions in the whole crypto book.
- STRATEGY daily-P&L corr: +0.08..+0.23 -> low.  Third independent
  confirmation of "trading geometry, not direction": co-held positions
  lose money at different times because stop geometry, not direction,
  dominates outcomes.

Concurrency caps on real history (total 4 / cluster 2, entry-time sim):
capped accepts 826/1040 (214 rejected by cluster-2 limit), EV +467.6R
-> +364.1R, maxDD 2.9R -> 1.9R.  The cluster cap binds (one crypto
cluster), so effective concurrent-position limit is 2; EV cost of the
safer profile is ~22%.

Bootstrap (stationary block, 1000 sims, 10-day blocks, 1R = 1% equity):
maxDD p50=1.7R p95=2.6R p99=3.2R -> **p95 = 2.6% << 30% flag: OK** with
wide margin.  Kill-switch (DD-triggered pause): at K=4R/14d NEVER fires
(p99=3.2R below trigger) - armed but idle, correct as a safety net; at
K=2R it fires but tail DD does not improve (p99 3.3R) while costing
5.5% EV -> kill-switch NOT recommended as a return-enhancing overlay,
keep K=4R as disaster-only backstop.

Caveats (pre-registered follow-ups):
(1) WF A vs B context: D.8b fold table - B wins 6/8 pooled (BTC 7/8,
ETH 6/8, SOL 5/8), but the gap SHRANK from +0.115R (single split) to
+0.049R under walk-forward.  B upgrade stands on breadth (6/8), not on
margin; treat B-A as +0.05R honest, not +0.115R.
(2)-(4) resolved by runs/d9b_robustness.json (scripts/d9b_robustness.py):
- Block sensitivity 10/20/30/60d: p95 DD FALLS with block length
  (2.60 -> 2.23 -> 1.99 -> 1.79R) - short blocks are the CONSERVATIVE
  end here (more independent resamples, choppier paths), tail not
  understated.  10d numbers stand.
- Daily vs trade-event equity DD: daily 1.72R vs event 2.44R -> daily
  aggregation IS ~30% optimistic (exceeded the 20% threshold).  Quote
  portfolio DD from the event curve: real maxDD ~2.4R capped (~3R
  uncapped); bootstrap p95 quoted on daily basis should be read as
  ~3-3.5R event-equivalent - still << 30% flag.
- Capped-out trades (214): mean r_pess +0.484 vs accepted +0.441 ->
  rejected are NOT worse: capping is pure capacity loss, not a quality
  filter.  Reject rate drifts 16% -> 24% over time (candidate density
  grows); if live capacity becomes binding, consider EV-ranking-based
  admission instead of first-come.
DECISION: portfolio = BTC+ETH+SOL one cluster, max 2 concurrent
positions, 1R = 1% equity, kill-switch armed at 4R drawdown.  Planning
numbers: EV +364R/14.4mo capped (or +468R uncapped), p95 DD 2.6%.

### Stage D.10 — nested CV on the B head :white_check_mark: (discount -2.2%)

Closes the hyperparameter selection bias (scripts/d10_nested_cv.py,
runs/d10_nested.json).  Outer = the 8 WF folds; inner = last 25% of
fold-train by time (3d gap), grid of 6 LGBM configs
(n_est {150,400} x leaves {7,15,31}) selected by inner-val NDCG;
final fit on full fold-train, replay protocol identical to D.8b.
Result: NESTED +0.436R (n=1016) vs FIXED +0.427R (n=1026) ->
selection-bias discount **-2.2%** (expected -20-30% did NOT
materialize: the fixed params ne300/lv15 were chosen conservatively
back in D.4 on BTC only and never re-tuned on this data, so there was
nothing to overfit).  Config choice is stable-ish (ne150 x7, plus
capacity picks in high-volume folds).  EXTERNAL QUOTE: +0.44R pess per
trade, ~57 trades/mo capped, p95 portfolio DD ~3% equity (event-basis).
Planning numbers are now bias-corrected on both axes (protocol:
walk-forward; selection: nested CV).

### Stage D.11 — rank-based portfolio admission :white_check_mark: (+28% EV, DD flat)

Fixes the FCFS slot-mechanics alpha loss found in D.2b
(scripts/d11_admission.py, runs/d11_admission.json; trade stream now
exports model scores - d8b patch, WF numbers reproduced exactly).
Same 1040-trade stream, cap = 2 concurrent:

| policy | n | EV | mean | maxDD(event) |
|--------|---|----|----|--------------|
| FCFS (old) | 826 | +364.1R | +0.441 | 2.44R |
| REPLACE-low (replaced contribute 0) | 1010 | +466.0R | +0.461 | 2.44R |
| REPLACE-high (replaced keep full r_pess) | 1010 | +461.6R | +0.457 | 3.44R |

EV gain vs FCFS: **+102R (+28%)**, far above the +0.02-0.04R estimate.
Why so large: displaced worst-score trades realize NEGATIVE mean
r_pess - REPLACE-low (count them 0) actually beats REPLACE-high (give
them back their losses).  DD unchanged at 2.44R in the planning (low)
variant.  Live rule: when all slots busy and a new signal's score
exceeds the worst OPEN position's score, close the worst and take the
new one; planning numbers use REPLACE-low (mid-flight close assumed to
give back everything).  DAILY PLANNING: +466R / 14.4mo (~32R/mo),
maxDD 2.44R event-basis (~2.4% eq @1R=1%), p95 bootstrap << 30%.

Cluster limit re-check at 4h outcome resolution: corr +0.02..+0.07 -
strategy outcomes decorrelated at fine granularity too, cluster cap 2
stands (not too tight, not too loose).

### Stage D.12 — maker-entry revisit :x: (REJECTED - total adverse selection)

Pre-registered potential +0.05-0.10R; measured instead: STRONGLY
NEGATIVE (scripts/d12_maker.py, runs/d12_maker.json).  Setup: limit at
fill-delta*ATR into the zone, wait W bars, outcome recomputed from the
ACTUAL fill price via a maker variant of the unified sim (entry fee
reduced to 30% of taker, same slip/gap penalties).  Grid delta {0,
0.1, 0.25, 0.5} x wait {1, 4, 12}h on all 2,891 gated WF-B signals.
Baseline market-always: +0.380R per signal.
Results: fill rate 18-40%; given fill, mean pess R is ~-0.04R at EVERY
delta (even delta=0, where the limit matches the old market price).
EV/signal (maker-or-skip) = -0.03..-0.07R vs +0.38R market -> lift
-0.41R.  MECHANISM: fills happen exactly when price trades through the
level - i.e. when the zone fails; adverse selection eats the fee
saving (worth only ~0.07-0.14R) many times over.  This was the last
cheap-cost hypothesis: the 0.25R market-cost assumption is not a
conservative placeholder, it is already favorable.  Execution edge
must come from elsewhere (REPLACE admission already banked +28%).

### Stage D.13 — OB/AVSL ablation :x: (DETECTORS CARRY NO EDGE - geometry does)

The pre-registered ablation splitting the +0.44R stack edge into
detector vs non-detector parts (scripts/ablation.py, runs/ablation*.json).
Four panel variants, identical builder and WF-B protocol (8x56d folds,
7d embargo, lambdarank, rule-table gate, cap state machine):
  A  real OB zones + AVSL (control; reproduces the published baseline)
  B  placebo OB zones + AVSL  (placebo = same side/height/confirm time,
     level shifted outward by U(0.25,3.0) x ATR(confirm); causal)
  C  real OB zones, AVSL off  (avsl/avsr NaN end-to-end: no
     avsl_bounce family, d_avsl features NaN, anchor:avsl* rules dead)
  D  placebo OB zones, AVSL off (detector-free stack)
Control check: variant A panel reproduces the production panel exactly
(235,950 rows BTC, identical market/2R counts) and scores +0.427R
pooled (n=1026, dd 4.3R) vs published +0.44 - harness calibrated.

Results (test pess R, n, maxDD event):
| variant | s1 | s2 | s3 |
|---------|----|----|----|
| A (real OB+AVSL)   | +0.427 (1026, 4.3R) | - | - |
| B (placebo+AVSL)   | +0.452 (1031, 3.2R) | +0.448 (997, 2.6R) | +0.477 (1089, 3.7R) |
| C (real OB, no AVSL)| +0.476 (1281, 4.8R) | - | - |
| D (placebo, no AVSL)| +0.539 (1490, 2.6R) | +0.541 (1430, 3.4R) | +0.531 (1459, 2.1R) |

Verdict (REVISED after D.13b diagnostics - see below): the first-pass
reading "detectors carry no edge" was TOO WIDE.  Decomposition:

1. COST GEOMETRY IS THE DOMINANT MECHANISM.  Within EVERY variant,
   EV is strongly monotone in stop width: quintile of risk_unit/ATR
   q0 (narrowest, cost_R 0.29) has ev -0.14 (A) / -0.09 (D), q2
   (cost_R 0.05) has +0.09 (A) / +0.05 (D).  Narrow stops die of
   round-trip cost drag (the D.3 mechanism), mechanically.  Placebo's
   outward shift widens risk_unit (17.4 -> 19.1 ATR) and cuts mean
   cost_R (0.099 -> 0.084) purely geometrically.
2. AT MATCHED GEOMETRY REAL OB WINS.  Among affordable rows
   (cost_R <= 0.05, ~54-60% of panel): A +0.0640 > B +0.0579 >
   C +0.0571 > D +0.0493.  The real-OB candidate stream is BETTER
   than placebo where costs are survivable.  The OB entry-timing/
   level signal exists; it is positive, not the +0.10..0.15R hoped
   for, but not zero and not negative.
3. THE D>A GAP IS A MIX EFFECT, NOT SELECTION: placebo shrinks the
   toxic tail (cost_R > 0.15: 21.6% of A rows contributing -0.036R/
   trade vs 17.2% contributing -0.024R for D).  "Random zones beat
   OB" is false; "random zones have fewer unaffordable entries" is
   true and mechanical.
4. AVSL IS ROBUSTLY HARMFUL (the one clean architectural finding):
   D - B = +0.08..0.09R in every seed; C > A at panel level; the
   avsl anchor stop rules were already the worst in stage 0.5b.
5. Fold robustness: D - A > 0 in 7/8, 6/8, 7/8, 7/8, 6/8 folds
   (seeds 1-5) but one regime fold contributes +0.28..0.37 of the
   pooled +0.09..0.11R; without it the gap is ~+0.05..0.07R.
   B - A is 5/8, 5/8, 5/8, 6/8, 3/8 folds - the "placebo OB better
   than real OB" first impression was NOT fold-robust; it was the
   AVSL/mix effect.

Pre-registration results table (test pess R, n, maxDD event; 5
placebo seeds for B/D - D > A in 5/5, B > A in 5/5, D > B in 5/5):
| variant | s1 | s2 | s3 | s4 | s5 |
|---------|----|----|----|----|----|
| A (real OB+AVSL)    | +0.427 (1026, 4.3R) | - | - | - | - |
| B (placebo+AVSL)    | +0.452 (1031, 3.2R) | +0.448 (997, 2.6R) | +0.477 (1089, 3.7R) | +0.453 (1019, 3.2R) | +0.432 (967, 2.1R) |
| C (real OB, no AVSL)| +0.476 (1281, 4.8R) | - | - | - | - |
| D (placebo, no AVSL)| +0.539 (1490, 2.6R) | +0.541 (1430, 3.4R) | +0.531 (1459, 2.1R) | +0.521 (1391, 1.9R) | +0.531 (1497, 2.5R) |

Caveats: 3 majors, 1h, 1.5y, one regime sample; placebo inherits real
zone timing/height/side (ablates LEVEL selection, not candidate
timing); diagnostics at panel level (no gate) + WF folds (gated).

Actions: (1) DO NOT go detector-free - real OB beats placebo at
matched cost geometry; (2) kill the toxic tail with an explicit
cost-aware rule (cap cost_R ~0.15 or min risk_unit in ATRs - the
mechanical -0.14R ev of q0 is pure cost drag); (3) drop avsl_bounce
and the anchor:avsl*/avsr* stop rules (robust +0.05..0.09R, the only
clean architectural finding); (4) re-run the ablation after data
expansion (15m, more assets) before freezing conclusions; (5) keep
detector tuning frozen - the affordable-segment OB edge (+0.064 vs
+0.049 placebo) is real but small; capacity/robustness work first.

### Stage D.13c — cost-cap grid + AVSL-off on the WF protocol :white_check_mark: (AVSL-off confirmed; cap is a dd lever, not free EV)

Measured the two D.13 actions on the gated WF-B protocol
(scripts/d13c_cost_cap.py, runs/d13c_cost_cap.json), no rebuild -
the cap filters (candidate, rule) rows with cost_R = 0.0025*fill /
risk_unit above the cap, which is deployable live (risk_unit is
known at signal time):

| config | test pess | n | maxDD |
|--------|-----------|-----|-------|
| A (control) | +0.427 | 1026 | 4.3R |
| A + cap 0.15 | +0.378 | 780 | 4.4R |
| A + cap 0.10 | +0.393 | 656 | **2.8R** |
| C = no AVSL | +0.476 | 1281 | 4.8R |
| C + cap 0.15 | **+0.502** | 970 | 3.6R |
| C + cap 0.10 | +0.454 | 718 | 3.0R |

Findings: (1) AVSL-off CONFIRMED on the gated protocol: +0.049R and
+25% trades - ship it (drop avsl_bounce + anchor:avsl*/avsr* rules).
(2) The cap is NOT free EV on the full stack: on A every cap LOWERS
mean (the gate loses rule options that were net-positive picks on
train) while cap 0.10 cuts dd 4.3 -> 2.8R; on C, cap 0.15 adds
+0.026R and cuts dd 4.8 -> 3.6R.  Best cell: C + cap 0.15 = +0.502,
dd 3.6R = +0.075R over control with -16% dd.  (3) The D.13 regime
fold is identified: fold 2025-10-27..12-22 (A +0.282 vs D +0.639)
and 2026-04-13..06-08 (A +0.239 vs D +0.502) - A's weak regimes; in
strong folds A >= D.  Wide-stop geometry matters most exactly where
the real stack degrades - a regime-aware stop-floor is the natural
next lever, not a global architecture change.

### Stage D.13d — regime trigger search: production vector does NOT separate the weak folds :x: (negative result, recorded to stop a wrong stop-floor)

Question before building a regime-aware stop-floor: is there a causal
signal that distinguishes f2 (2025-10-27..12-22) / f5 (2026-04-13)
from f1 (2025-09-01), with useful lead time?
scripts/d13d_regime_diag.py, runs/d13d_regime_diag.json.

Answer: NO at fold granularity.  The production regime vector
(z50/slope50 from SMA50, vol_pct = ATR% percentile, bbw_pct = BB-width
percentile, trailing 500 bars - all causal) has near-identical fold
means everywhere: |z50| 2.02-2.14 in ALL folds, vol_pct 0.41-0.55,
range% 13-20.  Candidate triggers have ZERO specificity - coverage of
vol_pct>=0.7: f1 33% vs f2 28% (flagging the GOOD fold more than the
bad one); |z50|<=0.5: 13-20% uniform; bbw_pct>=0.7: 24-36% uniform.

Latency is NOT the problem: f2 opens with a visible vol episode
(day 3-7 vol_pct 0.63-0.83 vs fold mean ~0.5) and f5 with a |z50|
collapse (day 3-7 |z| 0.5-1.1 vs fold mean ~2.0) - the detector sees
both within days.  The problem is that these episodes are not unique
to weak folds: f1 day 7 also shows ETH |z|=0.67, and vol spikes occur
in every fold.

Conclusions: (1) the weak-fold damage is NOT a slow regime the vector
can catch at fold/feature-mean level - it is episodic, trade-level
interaction (which candidates fire during intrabar-vol spikes against
narrow stops); (2) a stop-floor gated on z50/vol_pct/bbw_pct triggers
would burn EV in f1 without protecting f2/f5 - DO NOT build it on
these triggers; (3) next diagnostic must be trade-episode level: dump
per-trade (entry ts, r_pess, cost_R) for A and D, bucket by week, and
correlate weekly pess R with intra-week vol episodes - find what the
surviving trades in f2/f5 looked like vs the casualties.

New production baseline (accepted, from D.13c): C + cost_R cap 0.15 =
+0.502R, n=970, dd 3.0R (chronological).  Order matters: AVSL-off
FIRST, cap second - the cap loses EV on the full stack.

### Stage D.13e — metrics audit: "Sharpe 14" was the t-stat; dd was computed on a non-chronological curve :white_check_mark: (formulas now tested; performance LEVEL still suspicious)

Full pass over the metric plumbing (user flagged Sharpe = 14):

1. There is NO Sharpe anywhere in the codebase.  The 14 was
   ``trade_curve_stats["t_stat"]`` = mean/std*sqrt(n) - a SIGNIFICANCE
   statistic (mean in units of standard errors), not a Sharpe.  For
   C|cap=0.15: mean 0.502, per-trade std 0.46R, n=970 -> t = 14.2.
   Worse, the t-stat itself is inflated by dependence: pooling 3
   correlated assets multiplies it ~sqrt(3) with zero new information
   (now proven by test).  Naive t on the C cells reads up to 38.
2. Honest Sharpe, now computed and tested
   (``per_trade_sharpe`` = mean/std per trade;
   ``bucketed_sharpe`` = weekly R-sum Sharpe * sqrt(52), which absorbs
   intra-week overlap and cross-asset pooling): per-trade 0.72-1.08,
   annualized 5.7-16.5 across the grid; baseline C|cap=0.15:
   per-trade 1.08, annualized 12.3.
3. REAL BUG fixed in d13c: max_dd_r was computed on a PSEUDO-curve
   (trades concatenated per asset then per fold - not chronological),
   which overstated dd.  Corrected chronological dd, all cells:
   A|None 2.4R (was 4.3), C|None 3.7R (was 4.8), C|cap0.15 3.0R (was
   3.6), C|cap0.1 2.1R (was 3.0).  Consequence: earlier dd-based
   statements were partly artifacts - A's control dd is actually the
   LOWEST of the A cells; the cap no longer "cuts dd on A".  Mean
   ranking is unchanged: C|cap=0.15 remains the best cell (+0.502).
4. Formulas are now pinned by tests (118 passing): t-stat exact form,
   dd order-dependence, t inflation under pooling, per-trade Sharpe
   known values, bucketed Sharpe vs hand-computed weekly sums,
   unsorted-timestamp invariance, degenerate inputs.

OPEN CONCERN (the number, not the plumbing): even the honest
annualized Sharpe of ~10-16 is economically implausible for an hourly
strategy and per-trade Sharpe >1 is a classic look-ahead smell.  The
metric FORMULAS are verified; the suspicious part is upstream - the
r_net stored in the ablation panels (mean -0.027, std 0.858 over 24k
raw rows is sane, so the inflation appears at SELECTION time: the
gate picks rows whose outcomes cluster tightly).  Before any
production decision on the baseline level: audit the ablation panel
r_net computation for look-ahead (fill price vs decision bar, exit
indexing) and check the win/timeout/SL mix of the SELECTED trades.






### Stage D.13f — look-ahead audit of the gate + permutation-anomaly root cause :white_check_mark:

**Part 1 — REAL LEAK found and fixed.**  The rule table in all three
protocols (`ablation.py`, `wf_ab.py`, `d13c_cost_cap.py`) was fitted on
`~is_test` rows, i.e. on folds that are in the FUTURE relative to the
test fold.  Fixed: train mask is now strictly past-only
(`ts < fold_start - 7d embargo`).  With the honest table the grid
collapses: A|None +0.096R, C|cap=0.15 **+0.118R** (n=954, dd 6.1R;
was +0.427/+0.502R).  ALL prior stage-D numbers are RETIRED.

**Part 2 — permutation anomaly ROOT-CAUSED: the control was
mis-specified, there is NO residual leakage.**

Symptom: with `PERMUTE=42` (table fitted on shuffled `r_net`) test EV
stayed at +0.27..+0.36R, far above the honest +0.118.

Diagnosis (`scripts/_diag_perm_trace.py`, since removed, numbers below):
1. `fit_rule_table` really consumes the permuted `r_net` - the table is
   blind.  But the LGBMRanker was NOT permuted: it kept training on
   TRUE past `r_pess` labels.  The control therefore ablated only the
   table, not the ranker.
2. On the picks (max-`s` rule row per candidate, rule==table-rule,
   test folds) the per-rule EV is dramatically above the panel
   baseline: e.g. `zone:0.5` is -0.088R pess over ALL test panel rows
   but +0.68R (n=48) among ranker-top picks; `anchor:st:0.5` +0.58..+0.95
   on picks.  The ranker has genuine out-of-sample candidate-selection
   skill (entry-time features only - audited).
3. Pre-state-machine EV of permuted-table picks: +0.146R (n=808);
   post-SM +0.242R.  That is the ranker's skill flowing through a blind
   table - not leakage.
4. Full-pipeline permutation (ranker labels AND table labels shuffled):
   EV collapses to +0.064 pre-SM / **+0.069R** post-SM (n=441), which is
   statistically indistinguishable from the panel base rate over the
   same fold windows (**+0.010R**, n=46k; diff ~2 sigma, and post-SM
   trades are correlated so effective n is smaller).
5. Metric consistency check on identical picks: fresh `sim()` pess
   outcome vs panel `r_pess` differ by only +0.01R - the replay is not
   measuring a friendlier outcome than the panel.

Side finding RETRACTED in D.13g (see below) - it was based on the
phantom +0.118R number.

Bottom line SUPERSEDED by D.13g: the "+0.118R" honest number could not
be reproduced by any artifact (no commit, no json) and was WRONG; see
D.13g.


### Stage D.13g - gap-through-stop sim bug: the stage-D edge was 100% artifact :warning: RETIRE

**Correction to D.13f first.**  Two claims in the D.13f write-up were
wrong and are retracted:
1. "Honest grid collapses to A|None +0.096 / C|cap=0.15 +0.118" - no
   artifact backs this.  The saved d13c json (past-only mask) gives
   +0.437/+0.524, identical to the pre-fix run reproduced by d13g: the
   table leak was IMMATERIAL because the fitted table is fold-stable.
   There never was a "collapse".
2. "The informed table is worse than a noise table" - false; measured
   properly (D.13g, pre-sim-fix) the table gate +0.524 beats free
   +0.260.

**The real bug (found via the D.13e composition check).**  `sim()`
fills entries at `open[i+1]` and recomputes risk from that fill.  When
the entry bar OPENS beyond the stop (gap through stop), the trade was
booked as ~+1R (exit at `sl_price` on the far side of the gapped
fill) - but live the stop order fires immediately at market: a SCRATCH
(~0 net of costs).  Prevalence: 8-12% of ALL panel rows, ~+1R phantom
each.

Evidence (runs/d13g2.log, pre-fix): even in C|cap=0.15, hold<=1 trades
were 42% of trades, mean +0.72R, EV share ~1.1 - i.e. essentially ALL
of the cell's EV.  Win 82% with 69% "sl" exits, median hold 0 bars.
This also explains why the full-pipeline permutation only fell to
+0.07 instead of the +0.01 base rate: the artifact is STRUCTURAL, not
informational, so label permutation cannot remove it.

**Fix.**  `sim()` now detects the gap-through-stop entry and books an
immediate market scratch in units of `risk_ref` (intended
`risk_unit`; new optional parameter, all protocol callers updated).
Pinned by 3 new tests in tests/test_sim_engine.py (275 pass).

**Corrected grid (runs/d13g_ranker_only.json, fixed sim): EVERY cell
is negative.**  table/free: A|None -0.161/-0.135, A|0.15 -0.086/-0.095,
C|None -0.172/-0.134, C|0.15 -0.105/-0.066, C|0.1 -0.063/-0.064,
C|0.075 -0.048/-0.054.  Table-vs-free differences are now noise-level.

**VERDICT: stage-D approach is RETIRED.**  There is no edge - the
strategy loses ~0.05..0.17R per trade after honest costs in every
configuration.  The whole D-stage chain (+0.35..+0.52R, Sharpe ~12)
was the gap artifact; the ranker's genuine within-candidate rule skill
was real but ranked entries whose honest net EV is negative.  No
tuning, live testing, or downstream work on the stage-D gate as-is;
any restart needs a new entry hypothesis with positive net-of-cost
panel EV as a precondition.

### D.13g addendum - wrong-side stops: the poison was ALSO in the panel labels

The review pushed on the scratch booking; the data went deeper.
Empirical checks on the C panel (BTC):
- `fill_price = open(e+1)*(1+slip)` (confirmed; the earlier 0% match
  was a too-tight rtol against the slippage factor).
- **8.7% of rows have the stop on the WRONG side of the fill**
  (long with sl ABOVE fill): zone:0.5 (614), zone:1.0 (585),
  anchor:st:0.5 (325).  These are rows where the entry gapped through
  the stop level before the fill.  The builder's `_simulate_outcome`
  saw "stop level touched" and booked them as INSTANT WINS:
  r_net mean +0.935, 100% exit_reason=sl.  The ranker then trained on
  +0.94R labels and hunted these rows (42% of picks in some cells).
- Execution semantics: entry and the instant stop fire at the SAME
  gapped open, so the honest live outcome is a scratch (~-costs), not
  a win - and also not a "-1.5R": there is no position held through
  the gap, the fill and the stop execution coincide (the proposed
  "gap 0.25 ATR => r=-1.25R" criterion assumes a pre-gap entry price
  that market-at-next-open execution does not provide).

Fixes:
1. `sim()` gap-through-stop -> immediate scratch in `risk_ref` units
   (previous commit).
2. Both dataset builders (`build_mtf_dataset.py`,
   `build_stop_dataset.py`) now mark wrong-side-stop rows invalid
   (r_net=nan) - panel rebuild still TODO; interim load-time filter
   added to d13g/d13c (identical effect for this bug: all other rows'
   labels are computed with valid geometry).

Final honest numbers, fixed sim + wrong-side filter
(runs/d13g_ranker_only.json):

    cell          table    free
    A|cap=None   -0.028   -0.057
    A|cap=0.15   -0.028   -0.049
    A|cap=0.1    -0.108   -0.056
    A|cap=0.075  -0.053   -0.074
    C|cap=None   -0.062   -0.075
    C|cap=0.15   -0.043   -0.039
    C|cap=0.1    -0.084   -0.050
    C|cap=0.075  -0.077   -0.032

Permutation control on the fixed pipeline (d13c PERMUTE=42):
A|None -0.032, C|None -0.041, C|0.15 -0.049 - now indistinguishable
from the honest cells and from zero.  The control finally behaves:
no structural artifact left.  Composition is sane (hold med 47,
time-dominated, win 0.4-0.5).

VERDICT UNCHANGED but now airtight: stage-D EV = -0.03..-0.11R ~=
-costs in every configuration; no edge; RETIRED.  TODO: full panel
rebuild with the builder guard, then re-run D.8+ experiments before
trusting any historical number.

## D.14: funding carry feasibility check (post-D new hypothesis)

Delta-neutral carry screen (`scripts/d14_funding_carry.py`,
`runs/d14_funding_carry.json`): short perps with positive funding /
long with negative (spot leg hedges price risk; PnL = collected
funding).  29 OKX USDT perps, daily funding = sum of 3 settlements,
signal = trailing 3-day mean, daily top-3/bottom-3 equal weight,
0.3% round-trip cost per new position (perp taker 2x + spot leg).

New infra: `fetch_funding_history()` in `engine/marketdata/okx_fetch.py`
(OKX /public/funding-rate-history; NOTE: needs SWAP instIds, returns
dict rows, and only serves ~3 months of history).

Result (Jun 15 - Sep 15 2026, 96 days):

    gross_daily_mean_bp        1.61   (+5.9%/yr)
    gross_daily_sharpe         27.5   (hit rate 0.97 - carry persists)
    avg_daily_cost_bp         10.48   (2.1 new positions/day x 0.3% / 6)
    net_annualized            -0.324
    net_daily_sharpe          -30.3

Reading: the funding edge is real and highly persistent, but tiny
(1.6 bp/day) while a daily-rebalanced top-3 book pays 10.5 bp/day in
turnover costs.  Breakeven needs ~1 week average holding at taker
costs (0.3% / 7d = 4.3 bp/day still > gross) - the steady-carry
version does NOT pass the net-of-cost pre-condition on this window.

Caveats: 96 days only (OKX history limit), a calm low-funding regime,
29 assets, taker costs.  An event-driven variant (enter only on
funding spikes > hurdle, hold until normalization) is untested and
is a different strategy.  Steady funding carry: NO-GO for now.


## Panel rebuild closed; interim filters removed; mfe/mae collector

Full panel rebuild with the builder wrong-side guard is DONE.
Re-run on clean panels, no load-time filtering:

  - ablation: A -0.038, B -0.081, C -0.112, D -0.063 (all negative;
    placebo stack B/D worse than real A/C - poison was in the labels,
    not the detectors).  runs/ablation.json
  - d13g grid identical to the interim-filtered run to the digit,
    same per-cell n (640/634/627/615/627/620/618/601); hold<=1 n=0.
  - d13c re-run OK.

=> interim wrong-side filters removed from d13g/d13c (dead code;
   single source of truth = builder guard).  Stage-D verdict
   UNCHANGED and now grounded entirely in rebuilt panels.

New infra: engine/mfe_mae.py - universal DSL-configured MFE/MAE
collector (signal = any dsl expression evaluated bar-by-bar on a
prefix-bound context; causal by construction; prefix-invariance
tested).  Outputs abs/atr/R excursions per event.  R unit here is
sl_atr_mult * ATR(signal bar), NOT the main stack's rule risk_unit.
modes: entry=next_open|signal_close, exit=horizon|sl_hit (window
ends at stop-touch, hit bar included, sl_hit flag always recorded).
19 tests in tests/test_mfe_mae.py.

## Protocol extracted to engine (scripts slimmed down)

New engine/protocol.py owns the WF-B mechanics that lived
(copy-pasted) in wf_ab / ablation / d13c / d13g: protocol-panel
loading (reference filter + cost_R + cap + r_pess), fold calendar
(8x56d, 7d embargo), lambdarank train_ranker (past-only groups,
seed 7), multi-asset assemble_ranker_data, gated replay (top-s per
candidate, optional rule-table gate, sim + state machine),
pooled_stats.  Scripts keep only grids + reporting (d13g 272->135
lines, d13c 273->155).

CRITICAL lesson from the regression runs (all four scripts re-run
and compared byte-for-byte against pre-refactor JSONs):

  - LightGBM binning is encoding-sensitive.  The D.13 family feeds
    float32 zero-filled NaNs; wf_ab (D.8b) fed a pandas DataFrame -
    which silently upcasts to float64 and keeps NaN natively.
    Training wf_ab on the D.13 encoding flipped exactly 2 of 24
    ranker fits (fold-5-A BTC, fold-6-B) with visibly different
    trade counts (nB 20 vs 46).  assemble_ranker_data therefore has
    explicit fill_nonfinite / x_dtype params, and each experiment
    family's encoding is pinned in its script.
  - Original-code determinism verified: wf_ab run twice from git
    HEAD reproduced its JSON byte-for-byte, so any diff = real.

Final state: d13g/d13c/ablation/wf_ab outputs identical to
pre-refactor (ablation run with --reuse: only elapsed_s and
build=None differ, evaluation identical).  13 tests in
tests/test_protocol.py (folds, embargo boundaries, ranker
determinism + row-permutation invariance, replay gate/state
machine, loader filter/cost/pess, encoding variants).

## Encoding pinned; rel/seed diagnostics

Encoding presets ENCODING_D13 / ENCODING_D8B are now module
constants in protocol.py (single source of truth; wf_ab passes
ENCODING_D8B by reference, D.13 scripts take the default).  Never
inline fill_nonfinite/x_dtype literals.

Diagnostics on real panels (runs/probe_rel_seeds.log):

  - rel = clip(round((r_pess+2)*2), 0, 12): 73.7% of 282k rows in
    [2,6] (|y| <= 1R); ZERO rows at rel >= 10 - the cap never
    binds, no LambdaRank tail instability.  Formula kept as-is.
  - random_state is INERT here: seeds 1/2/3/42 vs 7 give
    max|d score| = 0.0 exactly (feature_fraction=bagging=1.0 -> no
    sampled randomness).  Therefore every run-to-run flip can only
    come from the feed encoding - confirmed again (D13 vs D8B:
    max|d| = 2.075 same fold, same seed).
  - Known limitation, deliberately kept: D.13 encoding maps
    warm-up/MTF NaN features to 0.0 ("missing" == "zero"), which is
    semantically lossy but is the encoding every D.13 verdict was
    produced with - changing it would invalidate all comparisons.
    NaN-native is available via ENCODING_D8B for future families.

## FeatureSpec DSL + MTF as-of adapter

- engine/dsl_feed.py: shared bar-DSL plumbing (SeriesCache,
  make_bar_context, BAR_DSL_MANIFEST) extracted verbatim from
  mfe_mae.py; mfe_mae re-exports - one indicator implementation and
  one causality contract for all bar-level DSL consumers.
- engine/feature_spec.py: FeatureDef/FeatureSpec (JSON-serializable)
  + collect_features(df, spec, event_idx) -> per-event Float64
  matrix.  Numeric feature-style evaluation via the new
  Interpreter.visit_numeric (arithmetic/historical keep numeric
  value, warm-up NaN propagates; comparison/logical -> 1.0/0.0).
  Causal by construction: prefix invariance and future-mutation
  invariance are pinned by tests.  Fail fast: names/exprs validated
  at spec construction, event_idx must be sorted/unique/in-range.
- engine/mtf.py asof_join_features(): HTF columns into a base frame
  under strict known_ts <= ts (closed bars only), optional age_col
  (staleness is a legitimate known-at-decision-time input).
  NOTE: resample_ohlcv buckets align to the epoch - MTF tests must
  use a grid-aligned base ts (T0Q in tests).

## Audit: visit() semantics, backward compat, warm-up

- visit() audit: exactly two production consumers of the BOOLEAN
  signal interpreter - engine/mfe_mae.py (signal) and
  dsl/evaluate.py evaluate_dsl.  Both are bool-by-contract; no
  consumer expects numbers from visit().  Numeric path is
  Interpreter.visit_numeric (feature_spec only).
- backward compat: no production module imports engine.mfe_mae
  (only its own tests); d13c/d13g/wf_ab unaffected by the
  dsl_feed extraction.
- dsl_feed: make_bar_context split into make_bar_provider (provider)
  + make_bar_context (Context wrapper) so hybrid contexts can
  combine bar DSL with extra column providers.
- warm-up pinned: close[3]/close[5] at idx 0 -> NaN, NaN comparison
  -> 0.0 flag; boolean feature cols are Float64 (schema asserted).
- asof_join_features staleness policy documented: adapter never
  filters stale HTF bars; freshness caps belong to FeatureSpec /
  event filtering, explicit and testable.

## FeatureProvider (engine/feature_provider.py)

ColumnProvider + HybridContextFactory: expose bar-aligned feature
columns (e.g. asof_join_features output) to DSL expressions via the
context_factory hook of collect_features / collect_mfe_mae.
Causal guards: col[k] -> row bar_idx-k; pre-row-0 reads are NaN;
negative offsets and out-of-range reads raise; row alignment
(height + ts equality) enforced once on first call; collisions with
bar-DSL indicator names rejected at construction.  Causality of
column VALUES is the producer's contract (known_ts <= ts for MTF).
End-to-end smoke: 1m bars -> 1h resample -> asof join -> DSL features
(htf_gap numeric, in_hrange/stale flags) verified live.
NOTE: DSL numeric literals do not support underscores (3600000, not
3_600_000).

## D.14: feature-family A/B (scripts/d14_feature_family.py)

Same panel rows / fold calendar / pess labels as the D.13 protocol;
only the ranker feature matrix changes.  Four arms, ranker-only free
gate, 8x56d folds, 3 assets, main panel:

  d13|enc=d13  pess=-0.057 (dd 41.0R)  decile spread +0.708  [baseline]
  d13|enc=d8b  pess=-0.062 (dd 43.6R)  spread +0.682
  d14|enc=d8b  pess=-0.293 (dd 285.1R) spread -0.051  [no signal alone]
  combo|enc=d8b pess=-0.038 (dd 26.0R) spread +0.697  [best]

Findings:
- encoding effect isolated and small (d13: -0.057 vs -0.062 under
  d8b) - families stay on their pinned encodings.
- D.14 family alone (13 scale-free bar-DSL + 4h-asof features, no
  side/zone/structure context) does NOT rank: flat decile ladder.
  Side-neutral market-state features are necessary but not
  sufficient; D.13's power comes from zone/side/structure features.
- combo: D.14 columns add ~+0.024R pess over d13|d8b and cut max DD
  43.6 -> 26.0R; top decile -0.04 vs -0.05 (conditional EV edge).
  Direction worth pursuing, not yet decision-grade.

Notes: D14 spec renames atr_pct -> atr_pct24 (D.13 build_features
already emits atr_pct; duplicate column labels crash pandas concat).
NaN share of D14 matrix is 0.000 - event bars sit past warm-up.
Saved: runs/d14_feature_family.json, runs/d14_feature_family.log.
Env: repo ruff currently fails on pre-existing pyproject RUF067
selector (unrelated); pytest 327 passed.

## D.15: honest order-block rework (ta pipeline) + raw EV

Semantic bug fixes in ta/src/custom/market_structure (engine okx.py
untouched - engine panel uses its own detect_order_blocks):

- Zone = source pivot bar range [low, high] + zone_atr_multiplier*ATR
  extension (zone_source: range|body|close_band, default range;
  close_band = legacy close +/- m*ATR).  Old default was a
  close +/- 1 ATR band, not an order block.
- Wick entry symmetry: supply tested by high[j], demand by low[j]
  (was inverted for supply).  Penetration guard now meaningful.
- check_orderflow_shift made causal: past window (idx, j] only,
  confirm-guarded pivots, ValueError when online ZigZag is off
  (offline pivots + shift filter = look-ahead leak).
- min_extreme_gap filter now confirm-guarded: rejects only when the
  next extreme was confirmed before the breakout bar.
- reversal_atr_multiple (k * median ATR, default preset k=2.5)
  replaces per-TF online_reversal_pct constants (reversal/ATR ratio
  decayed 4.05 -> 0.67 ATR across TFs in the old presets).
- Presets recalibrated: ADX filter off, RSI confirmation off,
  cluster_blocks off (1m-1h), confirmation_window 36 on 5m/15m
  (retest-delay p90 ~ 35), zone_atr_multiplier 0.2,
  use_online_extremes default True (honest by default).
- multiple_breakouts=True on 5m/15m, lookback_max=30: semantic bug -
  with multiple_breakouts=False the "break" was tested at exactly one
  bar (lookback after pivot), i.e. all candidates had a constant
  break delay (5 on 5m, 20 on 15m) and lookback_max was a no-op clamp,
  not a search window.  Natural first-break delay: med 8, p90 28.

Raw EV (in-sample, BTC-USDT only, 35070/9360 bars 15m/5m, taker 5bp
both legs, entry at retest close, stop beyond zone edge + 0.25 ATR,
TP in R, horizon 48 bars, conservative within-bar ambiguity):

  15m: blocks 567, gross EV +0.019/+0.044/+0.031 R at TP 1/3/6R
       (net -0.16/-0.13/-0.15R); win 47/16/3.5%
  5m:  blocks 1559, gross EV -0.045/+0.026/+0.034 R (net ~-0.25R)

Preliminary positive gross, pending walk-forward.  Do NOT read as
"OB works": single asset, in-sample, gross only.  Note: pre-fix runs
on the fixed-delay semantics showed 15m/6R +0.140R gross - mostly an
artifact of the constant break delay, not an OB edge.

Known anomaly (diagnostic for WF train folds, not an in-sample loop):
validated blocks skew to late breaks (pivot age med 32 vs natural
first-break med 8).  Hypothesis: early breaks are impulses (zone
consumed), OB retest works on post-consolidation reversals.  To be
checked via EV vs (break_idx - idx) on train folds.

WF (runs/ob_wf_ev.log, engine/experiments/ob_wf_ev.py): 7x56d folds
(history
holds 6.5 such windows; embargo 7d; causal prefix detection, ATR
median on prefix; fixed params - nothing fitted, folds measure
stability only).  Gross EV per fold (blocks per fold 39-100):

  fold     0      1      2      3      4      5      6   pos  mean
  1R   +0.001 +0.001 +0.013 +0.011 +0.026 -0.111 +0.103  6/7 +0.006
  3R   -0.053 +0.007 +0.091 +0.026 +0.082 +0.134 -0.024  5/7 +0.038
  6R   +0.141 -0.020 +0.187 -0.069 +0.062 -0.002 -0.101  3/7 +0.028

Verdict vs the pre-registered criteria (6/8+ -> maker; 4-5/8 ->
boundary, dig delay/age; <4/8 -> close): BOUNDARY.  1R is stable but
EV ~ 0; 3R positive in 5/7 with the best pooled gross; 6R pooled
positive but only 3/7 folds.  Gross is far below the ~0.16-0.18R
taker round trip everywhere - any continuation requires maker entry.

Age anomaly RESOLVED, no selection effect: validated ages span
[30, 60) with min=p10=30 - exactly the dynamic lookback (30 on 15m).
In candidates.py the break search starts at bar i = idx + lookback:
lookback is the pivot CONFIRMATION lag (causality - an online zigzag
pivot is not knowable earlier), so every tradable break is >= lookback
by construction.  The "natural med 8" distribution is offline and
untradeable.  Hypothesis 3 ("OB works on reversals, not impulses") is
not testable as posed; the real knob is the confirmation depth
(lookback) - a train-fold tuning question, after WF, not a bug.

Retest delay did not shift: break->retest med 5, p90 23 - cw=36 now
covers p90 with margin (in-sample p90 was censored at the window).

Train-fold diagnostics, step 1 - delay curve (runs/ob_delay_curve.log,
engine/experiments/ob_delay_curve.py; pre-registered buckets, TPs
{3,4}R; train = folds 0-3 + 7d embargo, test = folds 4-6 held out;
gross R, taker NOT included):

  delay      TRAIN n  EV3R/win      EV4R/win | TEST n  EV3R/win     EV4R/win
  [0,5)          157  -0.012/31.8%  -0.016/29.9% |  93  -0.115/32.3%  -0.101/32.3%
  [5,10)          60  +0.229/40.0%  +0.425/40.0% |  31  +0.242/35.5%  +0.198/32.3%
  [10,20)         73  +0.028/38.4%  -0.066/35.6% |  31  +0.123/32.3%  +0.252/32.3%
  [20,36)         64  -0.104/31.2%  -0.178/29.7% |  24  +0.211/50.0%  +0.058/50.0%
  pooled         354  +0.020/34.5%  +0.019/32.8% | 179  +0.032/35.2%  +0.033/34.6%

The [5,10) bucket passes the +0.03R criterion on BOTH TPs on train
AND confirms on held-out test at both TPs (+0.24/+0.20).  Fast-retest
zones (5-10 bars after break) carry the whole edge; immediate retests
(<5, the same impulse returning) and stale ones (20+) are a drag.
Caveats: test n=31 -> per-trade std gives SE ~0.27R (t ~ 1.5 pooled
n=91); 8 cells were scanned on train - the [5,10)x4R +0.425 cell is
inflated by selection, trust the cross-segment consistency instead.
Gross target (+0.10R) reached by the cut alone: delay in [5,10) -
proceed to lookback calibration and TP grid, then maker model.

Steps 2-3 - lookback grid + TP grid (runs/ob_lookback_grid.log,
engine/experiments/ob_lookback_grid.py; delay-cut [5,10) fixed;
static lookback via use_dynamic_lookback=False; train decides):

  L   TRAIN n  EV3R   EV4R   EV5R | TEST n  EV3R   EV4R   EV5R
  15      75  +0.102 +0.124 +0.126 |  37  +0.330 +0.438 +0.476
  20      70  +0.049 -0.023 -0.021 |  33  +0.493 +0.281 +0.341
  25      69  +0.058 +0.080 +0.071 |  36  +0.218 +0.064 +0.091
  30      60  +0.229 +0.425 +0.451 |  31  +0.242 +0.198 +0.230
  35      65  -0.070 -0.009 -0.097 |  20  +0.206 +0.283 +0.332
  40      68  +0.043 -0.007 -0.001 |  27  +0.329 +0.255 +0.254

Verdict: L=30 (the current dynamic preset clamps to exactly this) is
the train argmax - preset unchanged.  Train L-surface is jagged
(L=35 negative), i.e. weak identifiability; test column is noisy
(n=20-37) and NOT used for the decision.

TP surface at L=30, delay [5,10) saturates (extended run, gross):

  TP      3R     4R     5R     6R     8R
  TRAIN +0.229 +0.425 +0.451 +0.478 +0.495   win 40/40/38/38/38%
  TEST  +0.242 +0.198 +0.230 +0.262 +0.327   win 35/32/32/32/32%

Pooled train+test (n=91) at 4R: +0.35R, at 6R: +0.40R gross ->
~+0.19..+0.25R net after taker round trip.  SE ~0.17R (t ~ 2-2.5).
Working point: delay in [5,10), lookback 30, TP 4-6R, horizon 48.

Warning: selections are stacking (4 delay buckets x 6 lookbacks x
6+5 TPs scanned on train) - the working-point EV is upward biased;
folds 4-6 are burned for this config family.  Next: maker entry
model on the working point, then fresh-data validation on another
asset (15m AVAX/BNB) as the real holdout.

Holdout verdict - the pocket does NOT replicate (runs/
ob_holdout_assets.log, engine/experiments/ob_holdout_assets.py;
fixed point delay [5,10), L=30 static, TP {4,6}R, gross, zero
tuning on holdout):

  PRIMARY   n     EV4R/win    EV6R/win   delay med
  AVAX      197  +0.024/29%  -0.038/28%     6
  BNB       109  -0.177/27%  -0.191/26%     7
  SOL       237  -0.069/28%  -0.120/27%     6
  ETH       275  +0.178/36%  +0.139/34%     7
  SECONDARY (bonus, same fixed point)
  DOGE      217  +0.270/39%  +0.265/38%     7
  LINK      100  +0.044/32%  -0.008/31%     6
  LTC       229  -0.155/31%  -0.135/30%     6
  NEAR      191  -0.119/28%  -0.096/27%     7
  XRP        85  +0.105/34%  +0.186/34%     7

Pre-registered criterion: >=3/4 primary gross>0 -> maker; <=1 ->
close.  Result: 1-2/4 (clearly positive only ETH; AVAX ~0; BNB/SOL
negative).  All 9 assets pooled per-trade: 4R ~ +0.02R, 6R ~ +0.00R
- zero, below taker.  Delay med 6-7 replicates the BTC mechanism
timing but carries no edge outside BTC.  The BTC +0.35R working
point was selection-inflated + asset-specific.

DECISION: close the OB directional track per the pre-registered
rule.  No maker study (would model net on inflated gross).  Pivot:
funding carry.  Negative result is clean: pipeline semantics now
causal, the fast-retest mechanism timing is real and replicates,
the profitability does not.

Reopened (scoped): "OB geometry is BTC-specific" hypothesis.
Phase 0 structural diagnostics (runs/ob_struct_diag.log,
engine/experiments/ob_struct_diagnostics.py), 10 assets x 15m:

  asset  bars/ATR hl_ar1 hl_acf pv_lag p50/90 ret_p90 rng/ATR vol_ir gap  EV4R
  BTC      2.51  0.479   1    2 / 9    27     0.87  13.2  ~0  +0.348
  ETH      2.64  0.442   1    2 / 9    26     0.86  13.3  ~0  +0.178
  SOL      2.50  0.402   1    2 / 8    24     0.89  10.2  ~0  -0.069
  BNB      2.45  0.413   1    1 / 8    24     0.87  17.0  ~0  -0.177
  AVAX     2.40  0.400   1    1 / 6    24     0.88  17.4  ~0  +0.024
  DOGE     2.53  0.431   1    1 / 6    22     0.88  14.4  ~0  +0.270
  XRP      2.54  0.414   1    1 / 7    23.4   0.88  11.4  ~0  +0.105
  LINK     2.46  0.418   1    1 / 7    21     0.86  17.6  ~0  +0.044
  LTC      2.43  0.405   1    1 / 6    23     0.88  21.4  ~0  -0.155
  NEAR     2.32  0.375   1    1 / 6    22     0.89  12.1  ~0  -0.119

Spearman vs EV4R/EV6R: half_life_ar1 +0.77/+0.71, bars_per_ATR
+0.72/+0.65, gap_freq -0.66/-0.54 (degenerate metric, all ~0);
retest_p90, pivot_lag, volume_irreg, spread < 0.4.

Phase-0 criterion met (corr > 0.7) -> Phase 1 allowed.  Caveats:
metric spread is only 1.1-1.3x (not the hypothesised 2-3x); literal
half_life_acf spec is degenerate (return ACF < 0.5 at lag 1 always);
n=10 with noisy EV ranks.  Key structural fact: actual zigzag pivot
confirmation lag is p50=1-2, p90=6-9 bars - lookback=30 is ~4x the
real confirmation lag, so the Phase-1 formula (lookback = 1.5 x
pivot_p90 ~ 9-14, cw = 2 x retest_p90 ~ 42-54) would produce a
genuinely different configuration, not a cosmetic one.

PHASE 1 (reduced, PRE-REGISTERED before the run): the original
formula is broken - vol half-life ~1 bar cannot set a delay range
(conceptually wrong measure), and min_extreme_gap = 0.5 x pivot_p50
would disable the filter (p50 = 1-2).  What survives is a BTC-only
lookback recalibration:

  BTC only, 15m:
    lookback = int(1.5 x pivot_p90 = 9) = 13   (was 30, static)
    cw       = round(2.0 x retest_p90 = 27) = 54   (was 36)
    delay    = [5, 10)   (NOT adapted, kept from step 1)
    min_extreme_gap = 6 (default, NOT adapted)
    revATR = 2.5, zone_atr_multiplier = 0.2, TP = {4R, 6R}
  Secondary ablation arm (pre-registered, diagnostic only):
    lookback=13 with cw=36 (isolates the lookback effect).
  Decision on TRAIN (folds 0-3 + 7d embargo); test folds 4-6 are the
  readout vs the L=30/cw=36 baseline (train n=60 EV4 +0.425, test
  n=31 EV4 +0.198).  Criterion on EV_test: > +0.05R better -> the
  9-asset test with per-asset lookback/cw is allowed; within noise
  or worse -> phase 1 closed, OB track closed, funding carry.

PHASE 1 RESULT (runs/ob_lookback13.log, engine/experiments/
ob_lookback13.py): RECALIBRATION FAILS, criterion is a clean FAIL.

  arm                TRAIN n  EV4R/EV6R        TEST n  EV4R/EV6R
  A: L=30, cw=36        60  +0.425 / +0.478     31  +0.198 / +0.262
  B: L=13, cw=36 (abl)  73  +0.177 / +0.397     23  -0.171 / -0.241
  C: L=13, cw=54 (prim) 73  +0.177 / +0.397     23  -0.171 / -0.241

- EV_test drops -0.37R vs baseline (criterion was > +0.05R better);
  EV_train also lower.  Shorter lookback admits younger pivots whose
  fast retests are junk, not signal.
- B == C exactly: cw is irrelevant once the delay cut [5,10) is
  applied (all retests are < 10 bars after break anyway); cw only
  gates which blocks find a retest at all.
- Pivot-lag insight stands as a fact (real confirmation p90 = 6-9),
  but the "excess" lookback=30 was acting as a beneficial quality
  filter on pivot maturity, not as ballast.

FINAL: OB-retest on 15m is CLOSED per the pre-registered rule.
Hypothesis "lookback was masking edge" rejected.  Next: funding
carry recon (top-20 assets, funding history, annualized carry /
pct_positive / std), then baseline carry strategy.

Pre-closure diagnostics (runs/ob_ldgrid.log,
engine/experiments/ob_ldgrid.py) - all four confirm closure:

1. L x delay grid (5 L x 3 delay buckets, EV4R/EV6R, train vs test):
   NO coherent surface.  Cells flip sign between segments (L=13
   [5,10): train +0.51 -> test -0.10; L=35 [5,10): train -0.28 ->
   test +0.39; L=25 [8,15): train +0.22 -> test +0.84).  Train-best
   cells do not replicate; test-best cells were train-flat.  The
   "+0.35R working point" was a train-max artifact on a noise
   surface, as suspected.
2. Per-fold EV4R, delay [5,10): L=30 positive in 5/7 folds, L=13 in
   3/7; L=13 worse in 5 of 7 folds.  Consistent with the arm test,
   direction stable, magnitudes tiny-n noisy.
3. Age anomaly resolved: total validated blocks barely move with L
   (train 354 vs 355, test 179 vs 169; age med 40-41 vs 22-24, min
   age = L as expected).  The test survivor drop 31 -> 23 is delay-
   cut pool composition, not a missing population.
4. Null bootstrap of the holdout asset pattern: with true EV = 0 and
   per-asset SE from trade counts, P(>=5 of 9 positive) = 0.50,
   P(>=3 of 9) = 0.91.  Observed 5/9 positive at 4R (3/9 at 6R) is
   a coin flip - the "works on BTC/ETH/DOGE/XRP" pattern is
   statistically indistinguishable from noise.  Asset-segregation
   hypotheses (basis, beta, retail, depth) are moot.

OB-retest 15m: CLOSED, now with a defensible basis (grid incoherent,
bootstrap null-consistent).  Funding carry next.

## AVSL cross (new signal track) - PRE-REGISTERED before the run

Mapping (user-confirmed): fast line = avsl_ind(low, close, volume,
fast=70, slow=345) - the full AVSL indicator; slow line =
sma_ind(close, 345).  Data: BTC-USDT 15m okx21 (916d), warm-up 400
bars skipped.

Baseline arm (no filters): long when close crosses above fast
(close[t-1] < fast[t-1] and close[t] > fast[t]); short mirrored.
Signals with slow on the wrong side (risk = |close - slow| <= 0 or
stop beyond entry) are skipped - the stop is undefined there.
Stop = slow line at entry (structural); TP {3R, 5R, 8R}; horizon
192 bars (2d) with mark-to-market exit; conservative within-bar
ambiguity (stop wins).  Fees reported separately (gross / net with
taker 5bp x 2).  No cooldown, no alignment/ADX/volume filters -
those are step-3 arms, each pre-registered with criterion +0.05R
over baseline on train.

Segments: protocol folds 8x56d; train = folds 0-3, test = folds 4-7
(4 test folds; 916d history supports 16 windows).  Criterion on
train: EV > +0.05R signal, > +0.10R strong, <= 0 filters needed /
dead.  Readout: n, EV per TP, win rate, long vs short split.

BASELINE RESULT (runs/avsl_baseline.log): EV <= 0 gross, as the
pre-registered expectation for an unfiltered arm; filters are the
next step.  BTC 15m, 916d:

  TRAIN (folds 0-3): 1924 raw crosses (~2.1/day - the AVSL(70,345)
  line hugs price far closer than a swing MA; NOT 1-3/week), 757
  skipped (slow on wrong side - stop undefined).
    TP=3R n=1167 gross -0.003 (long -0.16/23%, short +0.08/31%)
    TP=5R n=1167 gross -0.007
    TP=8R n=1167 gross +0.098 (long -0.02/15%, short +0.16/22%)
  TEST (folds 4-7): 469 crosses, 181 skipped; gross +0.00/+0.06/+0.02.

Two structural findings:
1. Taker round trip in R = 2*fee*price/risk.  With no alignment
   filter the structural stop (slow SMA345) sits arbitrarily close
   to price on many crosses -> mean cost ~1.0R, net ~-1.0R.  The
   structural stop is economically undefined until slow-side
   alignment and a minimum-risk distance are enforced.
2. Long/short asymmetry flips between train and test (train short
   +, long -; test reversed) - no stable side edge at baseline.

Donor audit (user provided Pine source): the repo port is faithful
- lenV, VPCc clamp, PriceV/100, and the AVSL formula all match.
Two deltas: (a) Pine divides by PER-BAR VPCc[i] in the window loop,
the repo by the CURRENT bar's vpc_c (minor - VPCc moves slowly);
(b) donor default mult=2.0 vs stand_div=1.0 used in the first run.

Donor-calibration arm, stand_div=2.0 (runs/avsl_baseline_sd2.log):
  TRAIN n=1001 gross +0.03/-0.02/+0.05 (3/5/8R)
  TEST  n= 256 gross -0.03/-0.00/-0.07
Same conclusion: gross ~ 0, net ~ -0.85R (cost/risk collapse on
unfiltered crosses), long/short flip persists.  Cross frequency
~2/day is intrinsic to the indicator: AVSL is by construction a
trailing-stop line that lives near price (DeV offset), not a swing
level - the "swing cross" framing has no support in the formula.
Verdict unchanged: EV <= 0 -> filter step next, slow-alignment
first.  Honest alternative: treat AVSL crosses as what they are
(stop-flip events) or drop the track.

Bug fixes in ta/src/custom/avs_base.py (pre-validation, no Pine
cross-check by decision):
1. CRITICAL _price_v_rolling: window denominator now uses PER-BAR
   vpc_c[start+j] (Pine parity: src[i]/VPCc[i]/VPR[i] with i the
   loop index), previously current-bar vpc_c[i] was broadcast over
   the whole window.
2. _compute_len_v: banker's round() replaced with half-up
   floor(x+0.5), matching Pine's round().
Unit tests added (ta/tests/tests_custom/test_avs.py, 9 tests):
rolling mean on constant denominators, per-bar-VPCc regression
(fails on pre-fix code), zero-denominator skip, L=0 passthrough,
half-up rounding, len_v branches, vpcc clamp.  Full engine suite
green (236 passed / 2 skipped); ruff clean.
Fixed-code rerun (stand_div=2.0, runs/avsl_baseline_fixed.log):
  TRAIN n=990 gross +0.05/-0.01/+0.05; TEST n=260 gross
  -0.05/-0.02/-0.08 (3/5/8R).  Statistically identical to pre-fix:
  the VPCc-shift error was small (VPCc moves slowly).  Verdict
  unchanged: gross ~ 0 -> filters or close.

Long/short split + beta check + Path A (runs/avsl_baseline_fixed.log,
runs/avsl_align.log; stand_div=2.0, config 70/345):
1. Long/short EV tracks SEGMENT BTC DIRECTION, not signal quality:
   train (BTC -0.5% flat): short positive (+0.13/+0.10/+0.10),
   long negative (-0.09/-0.19/-0.02); test (BTC +8.4%): long
   positive (+0.14/+0.31/+0.08), short negative (-0.22/-0.26/-0.08).
   The "flip" between segments is beta BTC, confirmed by segment
   moves printed per segment.  Not a signal edge.
2. Path A slow-alignment arm (long: slow 1h-slope > 0 AND close >
   slow; short mirrored; pre-registered criterion +0.05R on train,
   all TPs): n 990 -> 648 train / 260 -> 175 test.  Train gross
   +0.039/+0.046/+0.135; test -0.071/-0.044/-0.066.  FAILS: two of
   three TPs below +0.05R on train, and the 8R TP that "passes" is
   negative on test.  Improvement does not transfer - consistent
   with the beta reading: the filter shaves trades but the residual
   EV is still segment drift.
Path A verdict: DEAD per pre-registration.  Path B (stop-flip exit
rule, separate experiment) or close the track.

Swap arm (for fun / diagnostic; runs/avsl_swap.log): entry line
= SMA(345), stop line = AVSL(70,345) - inverted config, same
protocol, stand_div=2.0.  Also fixed a NaN hazard: AVSL has
leading NaNs (~bar 400-710 in train), `risk <= 0` does not catch
NaN comparisons; entry loop now guards np.isfinite(risk).
  TRAIN (flat -0.5%): n=1089 gross +0.03/-0.00/+0.01
    [long -0.06..-0.11; short +0.19..+0.23]
  TEST (+8.4%):       n=248  gross -0.12/-0.23/-0.12
    [long -0.11/-0.21/+0.07; short -0.15/-0.27/-0.40]
Reading: swap is WORSE, and the beta pattern breaks - long is
negative even in a +8.4% segment.  Mechanism: SMA345 cross entry
is late (3.6d into the move), AVSL stop hugs price (tight risk)
-> stopped before continuation; net ~ -1.0R again.  Both configs
of AVSL/SMA cross-as-entry are dead; strengthens the B-or-C fork
(stop-flip exit rule vs closing the track).

Price-cross arm (no SMA; runs/avsl_price_cross.log): entry =
close crossing avsl(70,345) itself, stop = line at entry, both
orientations, 10 assets (BTC + 9 holdout), per-asset, train/test
as protocol.  Result: STRUCTURALLY DEGENERATE, not a fair test.
- Reverse arm: 0 trades on every asset/segment (100% skipped) BY
  CONSTRUCTION - at a down-cross close is below the line, so a
  reverse long has stop above entry: risk < 0 always.
- Normal arm: at the cross the line IS the price, so risk ~ 0 ->
  taker round trip = 2*fee*price/risk explodes (net -2.5R BNB-adj
  to -70R BNB-test); economically undefined, same cost collapse as
  the unfiltered baseline but worse.
- Only non-trivial signal: 8R TP gross is positive on 7/10 assets
  in BOTH train and test (e.g. AVAX +0.22/+0.03, LINK +0.23/+0.23,
  NEAR +0.08/+0.23) while 3R/5R are ~0/negative - tiny-risk, wide-
  target lottery asymmetry.  Untestable as taker: cost >> EV.
Conclusion: any stop tied to the AVSL line AT the cross is
economically void (risk -> 0).  Sane no-SMA designs are: (a) stop
= line + min-risk distance filter (bps of price, pre-registered),
or (b) Path B cross-to-cross flip, MTM, no fixed stop.

Price-cross v2, stop=1xATR(14)@entry (runs/avsl_price_cross_atr.log):
same 10 assets, normal + reverse, sane risk -> sane costs (net
-0.1..-0.6R).  Readout, 3R gross normal vs reverse:
  TRAIN: BTC +0.00/-0.02, AVAX +0.06/+0.01, BNB 0.00/-0.02,
  DOGE +0.04/-0.01, ETH +0.04/+0.02, LINK +0.12/-0.00,
  LTC +0.00/-0.03, NEAR -0.04/+0.02, SOL +0.10/+0.02,
  XRP -0.02/-0.01.
  TEST: BTC +0.02/-0.00, AVAX +0.01/-0.07, BNB +0.11/-0.02,
  DOGE +0.06/+0.00, ETH +0.00/+0.07, LINK +0.15/-0.00,
  LTC -0.02/-0.03, NEAR -0.07/-0.00, SOL -0.00/+0.03,
  XRP +0.12/+0.12.
Findings:
1. Normal beats reverse on ~7/10 assets in BOTH segments: the
   cross DOES carry directional info, but it is tiny, ~+0.03..+0.05R
   gross at 3R.
2. Absolute level ~ 0: 3R break-even win rate is 25%, observed
   24-29% -> EV ~ 0.  8R break-even is 11.1%; observed 12-15% ->
   small positive EV that is a property of the TP/ATR geometry
   (lottery payoff), present in BOTH orientations - not signal.
3. Taker costs on 1xATR(14) 15m risk (~0.3-0.5% price) are
   ~0.2-0.3R per trade -> every arm net-negative everywhere.
FINAL VERDICT, AVSL cross as entry (all configs tried: vs SMA345
stop, alignment, swap, price-cross ATR stop, both orientations,
10 assets): directional edge <= +0.05R gross, costs >= 0.2R ->
net-negative on every asset.  TRACK DEAD as entry signal.  The
only untested mechanism left is AVSL as exit (Path B stop-flip);
funding carry remains the standing pivot.

Path B stop-flip trailing (pre-registered, runs/avsl_trailing.log):
entry=cross, initSL=2xATR14, trail=AVSL-0.3ATR monotonic causal;
v1 time N=10 / v2 profit 1R / v3 AVSL>entry; bench=always-in;
10 assets, train folds 0-3.  Success criterion: trailing EV >
bench EV + 0.05R on train, replicated on test.
RESULT: 0/10 assets pass on train.  Best trailing vs bench EV
(train): BTC +0.148 vs +0.167, AVAX +0.202 vs +0.258, BNB +0.124
vs +0.082 (+0.042, <0.05), DOGE +0.150 vs +0.156, ETH +0.164 vs
+0.153 (+0.011), LINK +0.000 vs -0.022, LTC +0.006 vs +0.018,
NEAR +0.110 vs +0.084 (+0.026), SOL +0.119 vs +0.120, XRP +0.231
vs +0.183 (+0.048, <0.05).  Bench >= trailing on 6/10 outright;
no variant clears +0.05R-over-bench anywhere.
DD: trailing does cut maxDD (BTC 129-144R vs 178R; DOGE 45-53 vs
71; NEAR 57-61 vs 89) but only by cutting exposure - EV drops
proportionally.  No DD-free lunch.
Test replication: moot (nothing to replicate); test nets are
mostly negative, bench still generally >= trailing.
VERDICT: FAIL per pre-registration - trailing is beta with extra
steps.  AVSL track CLOSED in full: cross-as-entry dead (edge
~0.05R gross < costs ~0.2-0.3R), cross-as-exit no better than
always-in.  The always-in benchmark being the best arm is itself
the summary: the AVSL(70,345) line carries mild trend exposure
(beta), no tradable alpha at 15m taker costs.  Pivot: funding
carry recon.

Combined arm (user-requested, runs/avsl_trail_norm.log /
avsl_trail_rev.log): cross-entry + initSL=2xATR14 + IMMEDIATE
AVSL trailing (no activation gate; buffer 0.3ATR, monotonic),
normal AND reversed orientations, bench=always-in same orientation.
NORMAL trail vs bench, train EV: better on 6/10 but only XRP
clears +0.05R (+0.235 vs +0.183); NEAR +0.038; on test XRP
+0.183 vs +0.050 and NEAR +0.096 vs +0.005 do replicate, but 2/10
marginal passes are null-consistent (cf. OB bootstrap: asset
pattern coin flip at these sizes).  REVERSED trail: gross positive
9/10 train (fade + tight trail, win 40-46%, hold ~20 bars) but
below costs; net negative essentially everywhere, test 6/10.
DD: trail < bench nearly everywhere by construction (tighter
stops, smaller exposure), EV drops with it.
VERDICT: unchanged - no orientation/exit combo produces EV > bench
+ 0.05R robustly across assets.  XRP/NEAR flagged only as the
least-uninteresting cases; not actionable.  Track stays CLOSED.

HTF arms (runs/avsl_trail_htf.log): same combined design on 1H
(10 assets) and 4H (7 assets; no data for BNB/LINK/XRP).
1H NORMAL: bench (always-in) BEATS trailing on 8/10 train and
most of test (BTC test bench +0.29 net +0.20 vs trail -0.08;
SOL test +0.30 net vs -0.05).  Trailing still strictly dominated.
The only cross-TF pattern that is net-positive on multiple assets
in BOTH segments is the 1H ALWAYS-IN BENCH itself (train net:
BNB +0.48, DOGE +0.15, NEAR +0.14, SOL +0.12, XRP +0.07; test
net: XRP +0.74, SOL +0.30, LINK +0.27, BTC +0.20) - i.e. the
AVSL(70,345) line on 1H works as a plain trend-regime position
(long above / short below), which is beta-style directional
exposure, not per-trade alpha.  1H REVERSED: gross +7/10 test but
train only 4/10, different assets - noise.  4H: n too small
(test n=1..26 per arm; single trades dominate, e.g. ETH test
n=1 +7.6R) - no inference possible.
SUMMARY: AVSL(70,345) has one defensible use: 1H always-in regime
direction (beta overlay).  As entry signal, exit rule, or fade at
15m/1h/4h taker costs: closed.

yfinance data pipeline (engine/experiments/load_yf.py, data/yf/):
yfinance installed; 40 parquet files loaded (10 assets x 15m/1H/4H/
1D) in the okx21 schema (ts epoch-ms Int64 + OHLCV Float64), so
engine experiments run unchanged.  1H = 730d (17326 bars), 4H
resampled from 1H (4335), 15m = 60d (5742), 1D = full history
(2192-4387 bars, up to 12y).  Hour-aligned, gaps <= 7 on 1H.
DATA QUALITY WARNING: yfinance intraday crypto VOLUME is ~half
zeros (1H: ~8800/17326 zero-volume bars; 15m ~30%; 1D fine).
Anything volume-dependent (AVSL uses VWMA/VM) run on okx21 data
or 1D yf only; use yf intraday for price-only statistics or with
a volume-quality filter.

Universe expanded 10 -> 36 assets (3.6x).  144/144 files present
(36 x 15m/1H/4H/1D).  Yahoo rate-limits intermittently (different
symbols come back EMPTY per sweep; 2s pause + targeted re-runs
filled all holes).  Swaps after persistent Yahoo empties: UNI ->
CRV-USD, APT -> EOS-USD, SUI -> KSM-USD, GRT -> SAND-USD, PEPE ->
FLOKI-USD.  Final universe: BTC ETH SOL XRP DOGE AVAX LINK LTC
NEAR BNB ADA DOT UNI(CRV) ATOM APT(EOS) ARB OP FIL INJ SUI(KSM)
TIA SEI FET AAVE GRT(SAND) ALGO VET ICP HBAR ETC BCH TRX SHIB
PEPE(FLOKI) WIF TON.  Loader supports symbol filter args
(load_yf UNI APT 1H) + 2s throttle for targeted re-runs.

TRAILING ON YF UNIVERSE (runs/avsl_yf_{15m,1h,4h}.log; avsl_trailing
now accepts "yf" flag -> data/yf + 35-asset list): yf-specific
read path added: zero-volume ffill (see warning above) + bad-tick
excision (|1-bar logret|>50% bars -> OHLC := prev close, iterated).
TON EXCLUDED from yf stats: corrupt Yahoo series (636 bars stuck
at $0.017 after a fake -99.5% 1H print, Aug 2025); isolated spikes
in APT/ARB/TIA (1-5 bars) are excised.  15m yf not runnable: 60d
history < 448d walk-forward span (15m scale remains covered by
okx21).  Results (35 assets, net EV, pre-reg pass = train & test
both >= +0.05R, vs always-in bench same orientation):
1H NORMAL: 13/35 pass, trail>bench test 20/35, med diff +0.02R.
4H NORMAL: 11/35 pass, trail>bench test 25/35, med diff +0.16R.
1H/4H REVERSED: 6/35 and 3/35 pass, test med diff negative.
Reading: 4H NORMAL beats bench out-of-sample in 25/35 - nominally
binomial p~0.017, but (a) 6 configs tried, (b) 35 crypto assets
over one overlapping window are NOT independent trials, (c) trail
cuts exposure so bench DD (up to 200R on TRX) dominates gross
comparisons, (d) aggregate net-R is unusable (single 100x-trend
trades in SHIB/FLOKI give hundreds of R).  Before believing 4H:
block bootstrap over asset-level diffs + fresh window.  Verdict
unchanged pending that test: AVSL = beta overlay, not alpha; the
only new candidate is "AVSL trail on 4H" as DD-reducer.

OKX DATA EXPANSION (engine/experiments/load_okx.py, IN PROGRESS -> see
runs/load_okx_expand.log): breadth 10 -> 36 assets (BASE + NEW lists;
all 26 new exist as OKX spot {SYM}-USDT -- no Yahoo-style aliases),
depth caps raised to 15m 100k bars (~2.9y), 1H 40k (~4.6y), 4H 20k
(~9y), 1D 5000 (~13.7y, listing-capped).  Uses the existing resumable
okx_fetch page-cache: re-runs walk backwards from the oldest cached
bar, so depth grows run over run; interrupted runs lose <= 5000 bars.
First proof: BTC 1D 916d -> 8.94y (3265 bars) on the first invocation.
BUG FIXED en route (engine/infra/marketdata/okx_fetch.py): a cache
resume used to start at /market/candles, whose ~1440-bar recent window
cannot serve an old cursor -> both endpoints empty -> "no candles"
crash once a file reached listing depth (hit on ADA-USDT 1D, cache
since 2018).  Resume now starts at /market/history-candles, and an
empty fetch with a non-empty cache returns the cache as complete.
Also: run the whole expansion as ONE python process (bash "; " chains
survive python kills and respawn the next phase -> concurrent writers
on the same parquets).

LONG-ONLY ON OKX (runs/avsl_okx_long.log; avsl_trailing grew a "long"
flag + 1D support + min-bars guard, universe = load_okx.ALL 34): same
pre-registered config (cross entry 70/345, initSL 2xATR14, immediate
AVSL-0.3ATR trail), short entries skipped, long exits at SL|reverse
cross; bench = always-in long-only.  Net EV, train/test 224d+224d:
1D  x32: 1/32 pass, trail>bench test 5/32, med diff -0.011R -> null.
15m x10: 0/10 pass, 8/10 trail>bench but med diff -0.032R -> null.
1H  x10: 2/10 pass, 6/10 trail>bench, med diff +0.168R, but raw EVs
         are beta: trail/bench both strongly + in the 2026 BTC bull
         (BTC +0.94/+0.81R, XRP +1.18/+1.03R per trade), trail WORSE
         on choppy recoveries (ETH -0.21 vs +0.25, SOL -0.18 vs +0.60
         -- trailing cuts winners), better only in downtrends (AVAX
         -0.29 vs -0.41, DD cut ~30%).
4H  x8:  thin (n_test=74), 4/8, med +0.105R -- no inference.
Read: long-only changes nothing material -- the 1H long trail is the
same "always-in regime beta" as before with a DD-reduction side
effect; no alpha.  RE-RUN 4H/1H/15m over the full 34-asset universe
once the okx expansion finishes.

5M LONG-ONLY ON OKX (runs/avsl_okx_5m_long.log; "5m" added to
avsl_trailing TFs): 10 base assets, 2.5-3y depth (BNB/LINK/XRP 1y ->
wf_folds gives 7 folds, test 168d).  n_test=6801 trades.  Result:
fee wall, exactly as pre-diagnosed on 15m.  Test medians: trail
evG +0.051R/trade vs evN -0.289R (cost drag 0.34R = 0.1% round trip
over 2xATR14(5m) risk unit); bench evG -0.004 / evN -0.308.  Trail
"beats" bench 8/10 and cuts DD ~15%, but both are deeply net
negative on every asset (test evN -0.04..-0.35R).  Even at maker
0.02%/side the drag (~0.14R) still exceeds the +0.05R gross edge.
5m closed at taker AND maker costs; no further 5m work planned.

5M x5 CONFIG (runs/avsl_okx_5m_x5.log; cfg=350/1725 added to
avsl_trailing via _fast_line_fs, regression-checked bit-identical to
baseline 70/345; warm-up scales with slow).  Two variants, 10 assets:
LONG-ONLY: pass 0/10, trail>bench 6/10 (med diff +0.056R) but both
sides net-negative (trail med evN -0.24R, bench -0.17R); NORMAL
(two-sided): pass 0/10, trail>bench 3/10, med diff -0.060R.
Diagnosis: x5 halved trade count (n_test 6801 -> 3118) and doubled
hold (30 -> 57 bars) but gross edge per trade did NOT rise
(+0.051 -> +0.043R) because the R unit stayed 2xATR14 -- the edge is
scale-invariant ~+0.02..0.05R/trade while the 0.3R taker cost is
fixed per trade.  Slow-line configs cannot escape the 5m fee wall;
only the risk-unit (wider SL / bigger ATR mult) or maker fills could,
and both were already ruled out.  5m family closed for good.

ENTRY FILTERS ON 1H LONG-ONLY (runs/avsl_okx_1h_filters.log;
avsl_trailing grew filter tokens adx/ob/stoch/rsi = per-bar LONG
gate applied to BOTH arms; gated bench = always-in while gate on.
NOTE: gate is defined long-only; also _read_* now return open.
BUG FOUND: rsi_clouds_ind returns all-NaN macd/sig/hist -- rsi_ind
leaves 13 leading NaNs and the non-talib ema path poisons the whole
MACD with them.  Worked around in _gate_long (manual clouds: seed
warm-up NaNs with first valid RSI, causal).  Gate True fractions:
rsi 50%, stoch 50%, adx 24%, ob 2.5% of bars.)
Test-window results (10 base assets, same data+windows, unfiltered
rerun included):
  none          pass 2/10, tr>bn 6/10, n=610, med test diff +0.051,
                bench (always-in long) itself +0.285R/trade = beta.
  adx(>25,+DI)  3/10, 5/10, n=130, test diff -0.073; gate CUT bench
                to +0.116 (loses bull drift) -> not helpful.
  rsi-clouds    2/10, 7/10, n=352, test diff +0.388; trail own test
                EV med ~+0.37R (7/10 assets positive) vs unfiltered
                trail med ~+0.17R -- filter roughly doubles per-trade
                edge while cutting trades 42%.  CAVEATS: XRP +2.3R
                outlier, best-of-7 selection (nominal p(>=7/10)=0.17
                uncorrected), single bull window, correlated assets.
  stoch         1/10, 6/10, n=439, test diff +0.186 -- weak.
  adx+rsi+stoch 2/10, 4/10, n=69, test diff -0.338 -- stacking kills.
  ob (demand-zone veto) DEAD: 1 test trade.  Structural mismatch:
  AVSL cross bars almost never coincide with price-inside-zone bars
  (ob+stoch same).  OB gates entry-TIMING systems, not cross-veto.
Read: RSI-clouds entry gate is the first filter that improved the
trail (vs gated bench AND vs unfiltered trail) -- candidate worth a
block-bootstrap/holdout on the full 34-asset universe, NOT yet a
verdict.  ADX gate and OB veto rejected; ADX also worsens plain
always-in.  OB stays a standalone entry system, not a filter.

RSI-GATE TEARDOWN (steps 1-2 of the pre-agreed kill chain;
'rsi50' = plain RSI(close,14)>50 and 'rand' = seeded random 50%
gate added as controls; runs/avsl_okx_1h_filters.log tail).
Step 1 no-XRP + distribution (test diffs trail-gated_bench):
  clouds ALL med +0.388 (7/10 pos, q1 -0.118, q3 +0.715);
  clouds noXRP med +0.229 (6/9) -- passes the >+0.15 stop but XRP
  alone is 41% of the effect; breadth real (BTC .77 BNB .79 DOGE
  .55 LINK .55 NEAR .23 LTC .14), lower quartile negative.
Step 2 controls:
  rand 50%: med diff -0.042 (4/10), trail EV negative on 7/10 ->
  capacity-matched noise does NOT reproduce; gate is not a trade-
  count artifact.
  rsi50:   med diff +0.406 ALL, +0.405 NO-XRP (7/10) -- plain
  RSI>50 fully reproduces clouds WITHOUT the XRP crutch (clouds
  noXRP +0.229 vs rsi50 noXRP +0.405).  Trail test EV med ~+0.39R,
  7/10 positive, XRP only 0.86.
VERDICT: RSI-clouds machinery is redundant -- the effect is a coarse
momentum-regime gate (RSI>50), i.e. "beta with a momentum filter"
(hypothesis 2 of 3), not a clouds-specific timing edge.  Per the
kill chain: STOP on RSI-clouds as a signal.  The residual pattern
"gated 1H long trail beats gated always-in ~+0.4R/trade, XRP-robust"
is the same trailing DD-trim/regime story as before; it inherits the
old verdict (beta overlay) unless a bear-window holdout says
otherwise.  Do not spend bootstrap hours on clouds.

DONCHIAN BREAKOUT -- PRE-REGISTRATION (before any run; engine/
experiments/donchian_breakout.py).  Hypothesis: Donchian(20) breakout
+ EMA(200) trend filter + 2xATR(14) stop + Donchian(10) exit gives
positive net result on 4h crypto on >= 4/6 majors, train AND test.
Entry long: close > max(high[t-20:t]) AND close > EMA(200) AND
close > open AND ATR(14) percentile rank within last 500 bars > 0.3.
Entry short: mirrored (close < min(low,20), close < EMA200, red bar).
Exit: close < min(low[t-10:t]) OR close < entry - 2xATR(14)
(long; mirrored for short).  SPEC DEVIATION, declared: the user's
exit clause 3 ("close < max(exit_price, entry-2xATR)") is degenerate
-- max of two entry-time constants never rises; the trailing intent
is already Donchian(10).  Implemented as the two exits above, close-
based (as written), no intrabar wick trigger.  Also pre-registered:
no same-bar re-entry after an exit; each segment starts flat; risk
unit R = 2xATR(14) at entry; costs = actual 2x taker 0.05%/side
normalized by R (user's flat "0.16R" overstates 4h costs; at 4h
2xATR ~ 3-4% of price -> ~0.03R).  Sizing is R-normalized, fixed
fraction 1% is EV-invariant here.  Data: 4H, BTC/ETH/SOL/BNB/XRP/DOGE
(916d each), warm-up 700 bars.  Split = standard walk-forward: train
= folds 0-3 (224d), test = folds 4-7 (224d), segments start flat.
Benchmark: buy-and-hold over the same segment, expressed in R.
PRIMARY system = both sides (shorts mirrored, per spec); long-only
reported as secondary.  KILL: <= 2/6 assets with positive total net R
on test -> close the swing track, go look at funding carry.

DONCHIAN RESULTS (runs/donchian_4h_prereg.log) -- **KILLED**.
TRAIN: 6/6 positive net R (totR +12..+140, evN +0.13..+0.73/trade) --
textbook overfit-free train boom.  TEST: 2/6 (SOL +9.0R, BNB +6.0R;
BTC -6.3R, DOGE -7.3R, XRP -3.6R, ETH -1.9R) -> kill criterion hit
(<=2/6).  Vs buy-and-hold on test (B&H +5.1R BTC, +5.8R ETH, +6.2R
SOL, +6.6R BNB, -0.7R XRP, -2.1R DOGE): system loses to B&H on 4/6
and trails on a 5th.  Long-only secondary: 3/6 positive -- also
fails >=4/6.  Reads: (1) n_test is small (15-19 trades/asset), so
the kill itself is low-powered -- the test window may simply lack
clean ranges-to-trends; (2) the train/test flip with identical rules
is exactly the regime-dependence the AVSL work kept showing: 4h
breakout edge, where it exists, is a bull-trend beta, not portable
alpha; (3) close-based Donchian exit gives back a lot in chop
(BTC test: 47% win, negative EV).  Per pre-registration: swing/
Donchian track closed.  Next on the board was funding carry.

DONCHIAN ALL-TF ROLLOUT (runs/donchian_all_tf.log; same fixed rules,
6 majors, per-TF kill <=2/6 test; 1D now has deep okx data ~13y so
its train = first ~11y of history, test = last 448d; on 1D the fixed
WARM=700 bars eats part of train -- declared beforehand):
  5m : TRAIN 0/6, TEST 0/6 -> dead (fee wall, as everything on 5m).
  15m: TRAIN 0/6, TEST 2/6 -> dead.
  1H : TRAIN 4/6 (mixed: BTC -38.5R, ETH -12.5R vs XRP +61R),
       TEST **5/6** (BTC +7.2, ETH +11.3, SOL +28.1, BNB -0.2,
       XRP +47.1, DOGE +15.5R; evN +0.08..+0.56, win ~50%).
       Long-only 1H test: 6/6 positive (+5.5..+47.4R).
       Vs B&H test: beats it where B&H lost (XRP +47 vs -6.2R,
       DOGE +15.5 vs -9.1R) and on SOL; loses BTC/BNB, ties ETH.
  4H : TRAIN 6/6, TEST 2/6 -> the PRE-REGISTERED TF is killed.
  1D : TRAIN 6/6 (11y of history), TEST 1/6 -> dead.
Read: the pre-registered hypothesis (4H) stays killed; 1H passing is
a POST-HOC best-of-5 discovery in the same bull window that flattered
every long-biased test.  EV per trade on 1H test is small (+0.08
BTC) with heavy train maxDD (27-46R) -- looks like regime survival,
not breakout alpha.  Worth ONE fresh pre-registered confirmation
(full 34-asset 1H universe once the loader finishes, or a later
holdout window), explicitly labelled as such; no tuning of 20/10/200.

DONCHIAN 1H DD AUDIT (per-asset, runs/donchian_all_tf.log; user rule:
"DD > 20R on most assets = unacceptable risk regardless of EV").
TRAIN: DD 27.0..46.1R on **6/6** -> risk-inadmissible by the rule.
Recovery factor (totR/DD): XRP 2.26, DOGE 1.39, BNB 1.16, SOL 0.85,
BTC/ETH negative-total.  TEST: DD > 20R on 3/6 (BTC 30.0, ETH 22.5,
BNB 22.8); winners' path acceptable: XRP DD 7.6R (recov 6.2), SOL
10.8R (2.6), DOGE 16.9R (0.92).  Test totR distribution: med +13.4,
q1 +7.2, q3 +28.1, 5/6 positive; noXRP med +11.3 (4/5); XRP = 43% of
positive sum -- moderate concentration, not a single-asset carrier.
DD/n is small (0.05-0.33R/trade) -- the big DD_R numbers come from
hundreds of trades, i.e. they measure cumulative noise + regime, not
per-trade risk; still, by the pre-agreed 20R rule the TRAIN period
fails.  Therefore the 34-asset confirmation run carries an added
pre-registered risk gate (fixed now, before the run): median test
DD <= 20R AND recovery >= 1.0 on >= 17/34 assets, alongside the
>= 17/34 positive-net-R criterion.  Loader 1H phase still running
(no PHASES_DONE); test fires when data lands.

### Sim-audit: gap-through-stop / allow_reverse / GEN_SLIP layers (2026-09-20)

External review flagged 4 issues in engine/sim; all verified, 2 fixed.

1. gap-check missing in maker_sim AND market_sim (sim() had it).
   FIXED as defense-in-depth: both now scratch (negative, net of
   costs) when the fill is beyond the stop, mirroring sim().
   IMPACT ON PAST RUNS: ZERO.  Audit on the 751 WF-B signals with 1m
   data currently on disk (BTC/ETH/SOL/DOGE subset, scripts/
   audit_sim_gaps.py): 0/751 gap-through-stop at market entry;
   market_sim == sim() pess exactly on the baseline (-0.0543 R);
   maker_entry's 0.05*ATR limit-vs-stop guard blocked every possible
   beyond-stop fill (0 violations).  D.12 verdict (maker REJECTED,
   adverse selection) stands unchanged.  No re-runs needed.
2. allow_reverse fired at d < busy_until (position still open) and
   kept the old trade's ISOLATED r_net/exit_idx -> overlapping
   exposure double-counted.  IMPACT ON PAST RUNS: ZERO - no
   experiment ever set allow_reverse=True (unit test only).  FIXED
   semantics: reverse now force-closes the open trade at bar d
   (flagged force_exit_idx; isolated r_net is stale, caller must
   recompute) before opening the new side; docstring was wrong too
   ("bar >= exit bar"), rewritten.  Pinned by tests.
3. GEN_SLIP appears 4x on an SL exit (entry slip in cost_r, exit slip
   in price, pe=2x, xtr=1x -> 25 bps worst-case price slip; hand
   check on a 1%-stop trade: r_opt -1.2995R, r_pess -1.449R +gap).
   VERDICT: intentional layered pessimism, NOT a composition bug
   (r_opt already carries entry+exit slip honestly; pe/xtr are
   pess-only add-ons).  Left as-is: changing constants would
   invalidate all logged results; effect sizes here are +-0.4R vs
   ~0.15R of pessimism layers - conservative direction anyway.
4. Dead code in state_machine (second same-bar check, unreachable)
   removed; busy_until init -1 -> -2 (never collides with a bar).

Also verified: risk_ref normalization scales costs exactly inversely
(pess ratio 0.5000 for risk_ref 1.0 -> 2.0).  Full engine test suite:
231 passed / 2 skipped.  Cosmetic note: sim()'s `hold` parameter is
ignored (hardcoded i0+47 == HOLD-1 in maker); semantics identical,
no change made.

### OKX EXPANSION LOADER -- DONE (PHASES_DONE, log line 1439)

Final state: data/okx21 1H = 34/34 (complete, all validated; the
34-asset prereg ran with ZERO skips), 15m = 27/34 -- 7 assets failed
at 15m (end-of-run burst of OKX /market/candles + /history-candles
4-attempt failures: VET, ICP, HBAR, ETC, BCH, TRX, SHIB, PEPE, WIF,
TON among the FAILED lines; 54 FAILED lines total across both
phases).  1m legacy files remain 4 (BTC/DOGE/ETH/SOL).  Watcher
(pid 2832) fired correctly: runs/donchian_1h_34_prereg.log was
auto-created and ran to completion once the 34th 1H file landed.

### DONCHIAN 34-GATE 1H CONFIRMATION -- RESULT :x: (FAIL -> DONCHIAN CLOSED)

Pre-registered gates (fixed in 917bf70, any FAIL = Donchian closed
entirely -> funding carry).  TEST segment, full (both sides):
  G1 positive net-R: 27/34 (need >=17) -- PASS
     negatives: TRX -35.0R (worst), BCH -9.5, SHIB -5.9, LTC -6.6,
     AVAX -0.3, APT -0.8, BNB -0.2
  G2 median test maxDD: 14.9R (need <=20) -- PASS
     (unlike the 6-major TRAIN audit's 27-46R: bigger universe
     dilutes the DD tails)
  G3 recovery >= 1.0: 16/34 (need >=17) -- FAIL (BY ONE ASSET)
  OVERALL: FAIL -> per prereg, DONCHIAN TRACK CLOSED ENTIRELY.
Per-asset test totR highlights: XRP +47.1 (dd 4.8), ARB +41.5 (10.5),
INJ +39.4 (9.4), DOT +29.4 (12.4), SOL +28.1 (5.3), ALGO +25.6 (11.0),
FIL +25.4, HBAR +22.4, TIA +23.8; evN med ~+0.17, n=58-106/asset.
Honest reading: 27/34 positive in the SAME bull window that lifted
every long-biased test, train positives only 11/34 -- the wide
universe test inherits the regime-beta problem, and the recovery
factor (tot/DD) gate kills it even before that discussion.  NO
re-litigation of the one-asset miss: the gate was fixed before the
run (that is its entire point).  NEXT TRACK per prereg: funding
carry (OKX /public/funding-rate-history availability + pipeline).

### BARRIER-PROBABILITY MODEL -- PRE-REGISTRATION (2026-09-20, fixed BEFORE run)

New frame (user proposal): not direction, but P(hit TP before SL) --
first passage time.  Baseline no-edge P = sl_r/(tp_r+sl_r) (zero-drift
Brownian); any calibrated deviation from it is the tradeable signal.
User's own success prior: 30%.  ONE shot, gates below fixed now.

Pinned spec:
  Data: 6 majors 1H okx21 (BTC ETH SOL XRP DOGE BNB), entry = next
  bar open after the signal bar (generator rule), R = 1xATR14(signal).
  Barrier grid (tp_r/sl_r): (1,1) (1.5,1) (2,1) (3,1) (4,1.5) --
  taken from the user spec as-is; both sides; horizon 48 bars.
  Label: 1 = TP touched before SL with SL-FIRST pessimism (both in
  one bar -> 0); timeout (neither in 48 bars) -> 0.  Declared: the
  label is P(TP-first within horizon), timeouts count as losses.
  Features (entry-time only, causal): atr_pct, atr pct-rank(500),
  bollinger width + pct-rank, returns 1/4/12/48 bars, signed distance
  to Donchian(20) and Donchian(55) edges in ATR, (close-SMA200)/ATR.
  NO funding features in v1 (fetch infra exists; time-alignment is a
  v2 item -- declared, not an omission).
  Models: LightGBM binary per (side x config) = 10 models, pooled
  across the 6 assets.  Walk-forward: wf_folds 8x56d; per fold, train
  = past-only with 7d embargo (fold_masks); isotonic calibration on
  the 56d window immediately before the embargo gap; test = the fold.
  No tuning of LGBM params (n=400, lr=0.05, leaves=15, mcs=40 --
  the adaptive_tp defaults), fixed now.
  Trading rule on test bars: EV = P_cal*RR - (1-P_cal) - cost_R,
  RR = tp_r/sl_r, cost_R = (2*COMM+GEN_SLIP)*fill/(sl_r*ATR); per bar
  take the max-EV side+config; trade iff EV > 0; per-asset position
  slot (state machine); P&L from the PESSIMISTIC sim_trade (SL-first,
  slip, gap 0.25 ATR) -- the binary EV formula never touches P&L.

PRE-REGISTERED gates (all must PASS on pooled TEST, else the
barrier-probability track v1 is closed with no re-tuning):
  K1 calibration: pooled Brier(calibrated model) < Brier(baseline
     b/(a+b)) AND per-config improvement > 0 on >= 7/10 configs.
  K2 EV edge: top-decile (by model EV) pessimistic per-trade EV > 0
     on pooled TEST with n >= 300.
  K3 risk: pooled taken-trade curve maxDD <= 20R on TEST.
Sanity outputs (not gates): measured baseline-P table vs b/(a+b)
  theory; reliability deciles.  Parallel track: funding_carry.py
  (already implemented, never run) executed as-is, results reported
  separately; no interaction with this prereg.

### BARRIER-PROBABILITY v1 -- RESULT :x: (FAIL all gates, track v1 CLOSED)

runs/barrier_prob_prereg.log.  Smoke sanity first: measured raw
P(TP-first) for (2R,1R) on BTC 1H = 0.329 vs Brownian baseline 0.333
-- the b/(a+b) theory is CONFIRMED almost exactly, i.e. the raw
probability carries no drift edge to begin with.

Gates (pooled TEST, 8 folds x 56d, 6 majors, 10 side-x-config models
+ isotonic cal):
  K1 calibration: FAIL -- model Brier 0.21747 vs constant-baseline
     0.21688 (model WORSE); improvement on 1/10 configs only.
  K2 top-decile EV: FAIL -- pess EV = -0.372R (n=1306); all taken
     trades -0.400R, win 32%.
  K3 maxDD: FAIL (5279R across 13,057 trades -- artifact of scale;
     the real story is per-trade EV ~ -0.4R: the EV>0 rule is not
     selective, pessimistic costs ~0.25-0.35R at 1R stops dominate).
Verdict: entry-time vol/momentum/structure features do NOT shift
P(TP-first) enough to beat the constant baseline, let alone clear
taker costs.  The informative null the user predicted: on this
feature set first-passage probability is NOT predictable.  Track v1
CLOSED per prereg; v2 (funding/OI features, higher-RR configs where
the cost fraction is smaller) would need a NEW prereg -- standing
rule: no re-tuning after a kill.

### FUNDING CARRY -- RESULT :x: (REJECTED: costs >> carry; data thin)

runs/funding_carry.log, runs/funding_carry.json.  Pipeline executed
as-is (bug fixed en route: REPO was engine/ not repo root -- commit
this one).  Data: OKX funding history gave only ~97 days x 29 assets
(max_records=1800 insufficient for multi-year persistence analysis --
rerun with paged history if this track reopens).  Results:
gross carry +1.59bp/day (5.8% annualized, hit 96%, persistence high
as expected) but turnover costs 10.5bp/day (2.11 new positions/day x
0.3% round trip) -> net -32.6% annualized, hit 5%.  Even the
top-k-dead-zone filter (2bp/day) cannot bridge a 9x cost-vs-carry
gap; k=1 concentration would need top-asset funding >> 15bp/day
sustained, which the 97d sample does not show.  REJECTED at current
cost assumptions; reopening requires either maker execution on the
perp leg (~5x cost cut) or demonstrated sustained high funding.

### PER-ASSET SLOW CARRY v3 -- PRE-REGISTRATION (fixed BEFORE run)

Follows user directive after v2: cross-sectional rotation is dead
(extremes mean-revert faster than any rebalance frequency); the
surviving signal is per-asset hold-until-sign-flip carry.  v3 tests
it on 3y of funding history.

Data: Binance USDT-M funding, 1096d x 29 assets (cached).  Binance
is the only multi-year source; OKX tradability is an assumption to
be re-validated on the OKX 96d panel BEFORE any live step.  Params
frozen from v2 prereg (no tuning): signal = trailing 3d mean daily
funding, entry |sig| >= 2bp/day, exit on sign flip, maker half
round-trip (0.10%) charged at entry and exit, side = receive funding
(short perp + long spot for positive funding, mirror for negative).

CONTAMINATION CONTROL: the (3d, 2bp) params were chosen while
looking at OKX 2026-06..09, so the trailing year is tainted.
  PRIMARY eval = F1+F2 pooled (2023-09..2025-08, pre-observation).
  F3 (2025-09..2026-09) = reported confirmation, not gated.
No parameters are fit anywhere; WF means evaluation windows, not
fitting.

Metrics: per-asset daily net streams; Sharpe_ann and Sharpe_NW with
Newey-West factor sqrt(1+2*sum(rho_k, k=1..5)), factor clamped to
[1,5].  Asset counts toward the gate only if in-position >= 60 days
over the eval window (activity floor).  Portfolio = equal-weight
fixed 29 slots (flat contributes 0).

PRE-REGISTERED gates (all on PRIMARY F1+F2):
  C-G1: Sharpe_NW >= 1.0 on >= 10 of 29 assets.
  C-G2: portfolio Sharpe_NW >= 1.0.
  C-G3: portfolio max drawdown <= 20%.
Reported, not gated: F3 per-asset/portfolio Sharpe_NW, fold-by-fold
regime table, trade counts, OKX 96d cross-check (from v2 run).
### PER-ASSET SLOW CARRY v3 -- RESULT :white_check_mark: (PASS all gates, first survivor)

runs/funding_carry_v3.log, runs/funding_carry_v3.json.  One bug
fixed pre-result (same mirrored-sign class as v2 portfolio -- now
pinned by engine/tests/test_funding_carry_v3.py, 4 tests).

PRIMARY F1+F2 (2023-09..2025-08, uncontaminated, Binance 3y):
  C-G1: 28/29 assets Sharpe_NW >= 1 (top: ETH 6.88, BTC 6.45,
        LTC 6.45, XRP 5.82, LINK 5.22; NW factor 2.24).  PASS.
  C-G2: portfolio Sharpe_NW 5.19 (raw 11.60), ann +8.50%.  PASS.
  C-G3: portfolio maxDD 0.55%.  PASS -- BUT SEE CAVEAT 2.
Fold decay (the honest picture):
  F1 (2023-24): 29/29 assets, ann +13.5%
  F2 (2024-25): 22/29 assets, ann +3.75%
  F3 (2025-26, tainted window): 11/29 assets, ann +1.45%,
      portfolio Sharpe_NW still 3.72, maxDD 0.14%.
CAVEATS (declared):
  1. Carry alpha is DECAYING -- +13.5% -> +3.75% -> +1.45% ann by
     fold.  Classic crowding: funding premia are arbitraged down.
     F3 run-rate ~1.5%/yr is close to the noise floor of the cost
     model (maker assumption).
  2. maxDD is a FUNDING-STREAM drawdown: the simulation models no
     price risk (delta-neutral by construction), no basis moves,
     no margin/liquidation.  True DD will be larger; C-G3 as
     measured is nearly vacuous and will be re-specified in the
     execution prereg with a real simulator.
  3. Binance data; OKX tradability unvalidated.  F3 (11/29 >= 1)
     still clears the user's >=10/29 bar even in the decayed regime.
VERDICT per prereg efcb6d5: PASS -> track advances to (a) OKX 96d
validation of per-asset levels/persistence and (b) execution design
prereg (real sim: basis, margin, partial fills on maker legs).
 standing rule holds: params (3d, 2bp, sign-flip exit) stay FROZEN.

### ORDER FLOW -- DESIGN SPEC (no code, pending user go)

Goal: test whether microstructure information predicts short-horizon
direction beyond what OHLCV already showed it cannot.  Data is the
hypothesis: everything before used OHLCV derivatives only.
Sources (OKX, public): REST /market/trades + /market/agg-trades
(history depth to be probed), WS channels trades + books5 for live
collection; tick-by-tick L2 needs auth tier -- probe first.
Features (first prereg candidate set, keep SMALL): aggressor-signed
trade delta (1m/5m/15m), order-flow imbalance (top-5 book),
trade-size distribution skew, VWAP deviation vs mid, spread state.
Infra: WS collector -> daily parquet (trade ticks ~50GB/yr/major ->
start with 6 majors, 3 months); backfill via REST agg-trades.
Experiment prereg (before any run): WF 6 folds, same discipline as
barrier v1; gate = out-of-sample direction hit rate > 52% at 15m
horizon with taker-cost EV > 0, else close.  Heavy: 2-4 weeks.
NOT STARTED until user explicitly green-lights infra build.


### FUNDING CARRY v2 -- PRE-REGISTRATION (2026-09-20, fixed BEFORE run)

User challenge accepted: v1 was daily cross-sectional rotation (2.11
new positions/day), not carry.  Gross +1.59bp/day (96% hit) is real
persistence; the kill was execution-frequency + fee class, declared
fixable.  v2 tests the user's fixes.  DATA LIMIT (verified live):
OKX /public/funding-rate-history serves only ~94 days (0 records
beyond cache via after-cursor) -- "fetch 3 years" is IMPOSSIBLE on
OKX public API.  Longer persistence cross-check = Binance funding
API (years of history, different venue, clearly labeled as such,
NOT tradability evidence for OKX).

Pinned variants (all declared now, no tuning between runs):
  V-daily-taker : v1 as-is (baseline for continuity).
  V-weekly-taker: rebalance every 7 days, taker round trip 0.30%
                  (2x (spot 0.10% + perp 0.05%)).
  V-weekly-maker: PRIMARY.  rebalance every 7 days, maker round trip
                  0.20% (2x (spot 0.08% + perp 0.02%)).  NOTE: the
                  user's 5x maker cut is wrong for a delta-neutral
                  book -- the SPOT leg dominates and only drops
                  0.10 -> 0.08; real cut is 1.5x (0.30% -> 0.20%).
  Per-asset dead zone: skip positions with |trailing 3d mean| < 2bp/
  day (replaces v1's global OR-mask, which effectively never filtered).
  Per-asset slow carry (user's Sharpe gate): hold short while trail-
  ing 3d mean > +2bp/day, long while < -2bp/day, exit on sign flip;
  half round-trip charged at entry and exit (maker fees).
  K=3/3, signal decided on d-1 data, gross stream from held book.

PRE-REGISTERED gates (primary = V-weekly-maker, else the track
closes; per-asset gate uses OKX 97d window):
  W-G1: portfolio net annualized >= 3% AND net daily Sharpe >= 1.0.
  W-G2: per-asset slow-carry net Sharpe >= 1.0 on >= 3 assets.
  W-G3: portfolio turnover <= 0.3 new positions/day.
### FUNDING CARRY v2 -- RESULT :x: (primary gate FAIL; track CLOSED per prereg)

runs/funding_carry_v2.log, runs/funding_carry_v2.json.  Two bugs
fixed en route (documented, no tuning: portfolio PnL sign inverted
in first run -- hit 0.12 = mirror of v1's 0.96, caught and fixed
before the recorded run; Binance symbol mapping 'LINK-USDT' ->
'LINKUSDTUSDT' via str.replace).

Portfolio variants (OKX 96d panel, 29 assets):
  daily_taker : ann -76.7%, Sharpe -24.3, gross +0.90bp/d, 4.39
                new pos/day (v1's cost disease, confirmed).
  weekly_taker: ann -13.7%, Sharpe -5.5, gross +0.68bp/d, 0.89/day.
  weekly_maker: ann -8.3%, Sharpe -5.0, gross +0.68bp/d, 0.89/day.
KEY FINDING: weekly rotation does NOT preserve the gross edge -- it
collapses +1.6 -> +0.68bp/d.  Cross-sectional funding extremes
mean-revert within days: by the time you hold the top-3 for a week,
the extreme has decayed.  And turnover stays 0.89/day (the whole
6-name book churns every weekly rebalance) because extreme-tail
membership is not persistent.  User's model partially confirmed
(frequency costs dominate: -77% -> -14% just from weekly), partially
refuted (gross edge does not survive holding; maker is 1.5x not 5x).

Per-asset slow carry (W-G2, maker, hold-until-sign-flip): 15/29
assets net Sharpe >= 1 (AAVE 34, DOGE 20, LINK 17, BTC 17 ...).
Caveats: 96d single-regime window, no WF split possible, annualized
Sharpe inflated ~2.7x by funding autocorr (rho=0.76 -> Newey-West).
This is the user's actual mental model of carry and it is the ONLY
surviving signal -- but per prereg it is a secondary gate.

Binance 3y cross-check (1096d x 29): lag-1 autocorr 0.761, top-
quartile weekly Jaccard 0.363 -- funding persistence is real and
venue-independent, but moderate; extremes churn too fast for
cross-sectional rotation at any frequency tested.

Gates: W-G1 FAIL, W-G2 PASS, W-G3 FAIL (0.89 > 0.3).  OVERALL:
FAIL -> funding carry track CLOSED per prereg 58849ca.  If anything
here ever reopens, it is a NEW prereg for per-asset slow carry with
a WF split and NW-corrected Sharpe, tested on Binance 3y first as
the only source of multi-year funding history.  Order flow remains
the next track (needs explicit user decision).






Variant of the KILLED Donchian 4H (TEST 2/6 -> closed).  External
spec ("Quattro Donchian" / "Bitcoin Comet" family), claimed but
UNVERIFIABLE live stats (WR 46%, PF 6.7, 8/8 positive years).  This
is a POST-HOC filter addition after a failed test = data-mining risk;
declared.  ONE shot, no parameter tuning, per the standing discipline.

Pinned spec (taken from the external claim as-is, NO tuning):
  Universe: 6 majors (BTC ETH SOL BNB XRP DOGE) on okx21 4H
  (the spec's native universe is BTC/ETH only; 6 avoids cherry-pick).
  Indicators: Donchian(20) prior-bars high/low (ending t-1), SMA(200)
  closes (simple, NOT the EMA200 of the killed run -- that is part of
  the claimed spec), ATR(14) Wilder.
  LONG entry at bar t close: cp[t] > hh20[t] AND
    cp[t] > sma200[t] + 1.2 * atr14[t]  ("decisive break" margin).
  SHORT mirror: cp[t] < ll20[t] AND cp[t] < sma200[t] - 1.2 * atr14[t].
  Fill at the signal close (same convention as the killed 4H run,
  for comparability).  Initial stop entry -/+ 2.75 * ATR(entry),
  ATR FROZEN at entry.  Trailing: stop = max(init, runmax -
  2.75*ATR_frozen) from the running extreme since entry.  NO TP, no
  time exit (segment end closes at segment close).  Exits evaluated
  on CLOSE crossing the stop as of the previous bar (conservative,
  no intrabar stop-tightening look-ahead; matches the killed
  harness).  Costs: 2*TAKER_FEE*entry / (2.75*ATR_e); R denominator
  = 2.75*ATR_e (initial risk).  Same TRAIN/TEST split as the killed
  run (wf_folds 8x56d, TEST = fold 4 start .. end, WARM=700).
  Both sides primary; long-only secondary; bench = buy&hold in R.

PRE-REGISTERED verdict gates (all must PASS on TEST, else the whole
Quattro family is closed with no tweaks):
  G1: >= 4/6 assets positive net R on TEST
      (stricter than the old kill <= 2/6: family already failed once)
  G2: median TEST maxDD <= 20R  (user's standing risk rule)
  G3: recovery >= 1.0 on >= 4/6 TEST assets
  G4: pooled TEST profit factor (net) >= 1.3
Expectation checks (NOT gates): claimed WR ~46% and PF ~6.7 on TEST;
NOTE a 2.75-ATR trailing stop cannot plausibly produce avgWin/avgLoss
= 6.7 (the trail caps winners on a 2.75-ATR retrace); if measured WR
/PF wildly exceed the claim's internal consistency, treat the claim
as fabricated and say so.  Regime-beta suspicion is explicit: this is
an always-in-after-entry trend rider -- the recurring "beta, not
alpha" pattern of this project applies.

### QUATTRO DONCHIAN 4H -- RESULT :x: (FAIL per prereg, family CLOSED)

One shot, no tuning (runs/quattro_4h_prereg.log, long-only secondary
runs/quattro_4h_prereg_longonly.log).  TEST segment:
  full:   G1 4/6 positive (BARE pass), G2 med DD 5.7R (pass),
          G3 recov>=1 2/6 (FAIL), G4 pooled PF 1.05 (FAIL) -> FAIL.
  longonly: G1 2/6, G3 0/6, G4 PF 0.99 -> FAIL worse.
Per-asset test totR (full): BTC -5.2, ETH -5.8, SOL +5.8, BNB +3.4,
XRP +5.4, DOGE +0.1; BTC/ETH -- the spec's OWN native universe --
lose on test in both configs.  TRAIN 5/6 positive with tiny evN
(+0.05..+0.16R, PF 0.88-1.35) in the bull window = regime beta
again; it does NOT survive walk-forward (train winners BTC/ETH flip
negative on test).

Claim check (vs "confirmed live" WR 46% / PF 6.7 / 8 positive years):
measured pooled TEST PF 1.05, per-asset PF 0.62-1.68, WR 30-59%,
mean hold ~20x4H ~= 3.3 days.  Nothing remotely like the claim; as
pre-registered, the claim's internal consistency was already
implausible (a 2.75-ATR trail cannot produce 6.7 avg win/loss) and
the data falsifies it outright.  The 1.2-ATR "decisive break" margin
did NOT fix the fakeout problem of the killed Donchian 4H -- same
verdict, same reason.  QUATTRO FAMILY CLOSED: no parameter tweaks,
no TF sweep, no further variants.


#### AVSL LIVE-SCALE PREREG (2026-09-22, FROZEN BEFORE ANY LIVE CODE)

Scope: SIZING / VENUE / MONITORING only.  The signal, geometry and
S1 sizing config move NOT AT ALL: engine/passed/avsl_cross_s1.py
is read-only for this track.  This prereg operationalizes the
read-outs recorded at the E5/E4 verdicts and the S-decomposition
("LIVE RISKS" block): monitoring, not filters; brake, not
discretion.

STRUCTURE (two phases, each gated):
  Phase A  PAPER-FORWARD shadow pilot, >= 90 days AND >= 50 closed
           trades (whichever is later).  Live 4H grid, live data,
           frozen module recomputed on each closed 4H bar; orders
           simulated at taker.
  Phase B  small real capital, ONLY after Phase A PASS, same
           monitoring; any size-up beyond Phase B is a new prereg.

VENUE / COST ASSUMPTIONS (frozen):
  universe   the frozen 10 (BTC AVAX BNB DOGE ETH LINK LTC NEAR SOL
             XRP), USDT-M perp, taker-only entries and exits
  fee        <= 10 bp round trip (matches the backtest assumption)
  slippage   budget 5 bp / side
  ABORT gate all-in realized cost > 15 bp RT over any 20
             consecutive fills -> STOP, re-prereg with real costs

PARITY (hard gate, Phase A):
  every closed 4H bar: live signal must equal the module's
  recomputation on the same bars (engine self-check path).
  ANY mismatch -> immediate STOP + post-mortem before resume.

MONITORING READ-OUTS (weekly snapshot to STATUS, monitoring NOT
filters -- none of these may gate the signal config):
  r1  rolling Sharpe (90d, daily returns of the account stream)
  r2  ATR percentile (500-bar) + current-regime tag (low/high)
  r3  corr(realized vol, S1 size)
  r4  trade-count parity vs the backtest F3 rate
  EXPECTED DECAY (prereg'd, from E5): if r2 flips to high-ATR,
  EV is expected to decay toward the 2023-24-like ~0; that is the
  prereg'd behavior of a regime-bound edge, NOT a malfunction and
  NOT grounds to touch the config.

DISASTER BRAKE (mechanical, prereg item -- never discretionary):
  pause NEW entries while rolling Sharpe (90d) < 0; existing
  positions run to their frozen exits.  Resumption requires
  rolling Sharpe > 0 AND a dated STATUS note.  Bypassing the brake
  for any reason = pilot FAIL.
  K=4R/14d equity backstop stays armed but idle (bootstrap: never
  fires, p99 = 3.2R) -- disaster-only, not a return overlay.

PILOT GATES (evaluated at Phase A end):
  g1  parity: zero mismatches over the full window
  g2  cost: all-in RT <= 15 bp over all fills
  g3  brake: zero bypasses, weekly snapshots without gaps
  g4  DD <= 25% (the frozen E-d level)
  g5  declared in advance: the pilot does NOT judge EV
      significance -- n=50 is underpowered by design; the EV
      read-out is descriptive.  Pseudo-confirmatory reading of a
      50-trade EV is forbidden.
  Phase A PASS = g1..g4 all hold.  Any fail -> STOP + post-mortem;
  resumption is a NEW dated prereg.

FORBIDDEN (carried from the closed tracks): concurrency caps
(toxic, S3/S4), any entry/exit filter (incl. skip-high-vol --
E5 finding requires its own prereg), parameter changes, dead-pool
entries.  Code to be written AFTER this freeze:
experiments/live/parity_check.py, experiments/live/pilot_tracker.py.


DETECTOR AUDIT + FIX (2026-09-22, post-E8, library quality)
An external review claimed ~19 defects in the OB detector
(market_structure).  All claims were verified against the code
before any edit; full verdict table in
experiments/ob/detector_audit.md.  CONFIRMED and FIXED:
  A1 "dynamic lookback" units bug: price-valued median ATR used as
     a BAR count -> disguised constant lookback_max=50; with
     multiple_breakouts=False the breakout was checked at EXACTLY
     pivot+50.  FIX: honest scan window [lookback_min, lookback_max),
     first valid breakout wins; dynamic-lookback fields deprecated.
  A2 multiple_breakouts never re-signaled (both branches took the
     first breakout; R2's docstring was wrong).  FIX: folded into
     A1; R2 == R1 now.
  A3 LOOK-AHEAD: reversal threshold = k * median(ATR over the FULL
     series).  FIX: causal warmup median
     (reversal_warmup_bars=500).
  A4 LOOK-AHEAD: structure filter used unconfirmed pivots (bar-index
     filter, no confirm guard).  FIX: confirm-guarded in online mode.
     Did NOT affect E8 (research presets run with the filter OFF).
  A5 liquidity_tolerance absolute (no-op above ~$25).  FIX:
     relative fraction of price.
  A6 no zone-pierce guard between breakout and retest.  FIX: new
     require_zone_intact=True (far-edge + penetration allowance).
REFUTED (documented, not changed): volume-gate "weakening" claim
(inclusion makes it STRICTER by w/(w-1)); "confirmation_window=36
on 4h" (default 10); "zone_atr_multiplier not ATR-scaled" (it is);
breaker list mutation (none); empty-frame dtype mismatch (none).
POLICY flags left as-is (documented in the audit): wick-touch entry,
close-confirmation off, breakout-by-wick, None-trend pass-through,
min_extreme_gap causality (by design).

CONSEQUENCES: all previously recorded OB numbers (acceptance
R1-R3, ablation, port-check, E8) were measured on the OLD detector
("fixed 50-bar delay + wick-touch retest").  E8's KILL stands as a
verdict about the detector AS TESTED; OB track remains CLOSED; no
closed prereg is re-run.  Any OB revival on the fixed detector =
NEW dated prereg + fresh acceptance.  Live-preset regression
baselines ("1h"=131, "4h"=10) are STALE; post-fix smoke ("4h"
preset, 4H grid): BTC 64, AVAX 83, BNB 32, DOGE 30, ETH 44.
AVSL live-scale prereg (previous section) is UNAFFECTED: the frozen
AVSL-cross 4H S1 module does not import market_structure; engine/
is clean.

TESTS: ta suite +5 batch-1 regression tests (causal reversal, window
scan, zone-intact guard, structure confirm guard, price-scale
invariance) and +1 batch-2 guard test (strictly increasing pivot
indices).  Full monorepo run is `pytest ta/tests engine/tests dsl/tests`
(root `pytest -q` covers only engine+dsl per testpaths):
2543 passed / 6 skipped; ruff and mypy clean.

AUDIT BATCH 2 (2026-09-22, later same day): a second review batch
(17+5 items) was verified against the code -- verdicts appended to
experiments/ob/detector_audit.md.  NO new code defects: the headline
items are batch-1 fixes re-stated (fixed-offset breakout = A1+A2;
zone re-pierce = A6); refuted: min_reaction_size IS relative (0.2%
of price -- R6), pivot-idx dict collisions are impossible by
construction (R7, now locked by a test), cluster_blocks is off
everywhere including R1-R3 (R8), shallow-copy mutation leak has no
live path (R9), ATR period is bar-scaled by definition (R10).
New policy items documented: P8 zone anchored to pivot-bar ATR, P9
one-sided volume gate (no cap), P10 RSI gate = momentum-continuation
semantics (dead code, off), P11 mature-trend structure extremes,
P12 tail-window truncation, P13 range-vs-body zone source.

AUDIT BATCH 3 (2026-09-22, same day): headline claim "zone_source is
dead, E8 tested a close_band, OB was never tested" -- REFUTED for
the current code (indicators.py dispatches range/body/close_band,
3 pinning tests; E8 and R1-R3 acceptance ran post-rework with
zone_source="range").  TRUE historical core: before d4565c0
(09-20 19:10, "OB honest rework") the pipeline built close +/- m*ATR
unconditionally -- so the EARLY OB kills (15m/1h retest, D-era
closure) are verdicts about the close_band variant, not structural
OB.  Corroborated by the acceptance zone-width 1.56-2.09 ATR =
(high-low) + 0.4*ATR (impossible for close_band).  Other batch-3
items: FVG brk+1 is the FVG definition, not look-ahead (signal is
dated at retest j >= brk+1); min_extreme_gap asymmetry = P5 by
design; the rest are repeats (volume gate, A5 already fixed, R6,
R7, R-5 -- empty branch IS covered by test_empty_output_schema).
Verdicts R13-R20 in detector_audit.md.  OB track stays CLOSED for
all eras; early close_band-era kills are citable as prior evidence
for a close-band-variant revival only.

AUDIT BATCH 4 (2026-09-22, post-fix follow-up): reviewer "tails"
adjudicated -- items T1-T6 in detector_audit.md are repeats of
existing policy/refuted verdicts (wick-entry=P1, reaction
semantics=R6, volume algebra=P9, is_aligned(None)=P4, cluster
mutation=R9, empty-frame schema=R-5/R11, exercised by
test_empty_output_schema); NO new code defects.  Perf (T7): the
new numba window scan costs 1.1 s per 500k bars (zigzag 2.2 s;
end-to-end 79 s is dominated by the PRE-EXISTING python validation
pass, not the window loop) -- non-issue at production scale
(~1.5 s/asset on the 4H grid).  Funnel diagnostics added
(experiments/ob/detector_funnel.py; matches the pipeline count
exactly): on the live "4h" preset the dominant cutter is
min_extreme_gap=8 (83% of BTC candidates), NOT the zone-intact
guard (1.7%) -- hypothesis refuted by measurement.  POST-FIX
ACCEPTANCE RE-RUN (runs/ob_research_check_postfix.log): R1/R2/R3
pass A1-A5 on all 10 assets (n=889-1110 within [200,2000], width
median 1.69-1.82 ATR, delay 2 / p90 6-7, S 47-53%, determinism
OK); only A6 fails, as expected -- its frozen references (131/10)
are stale pre-fix baselines.  The research acceptance criterion
SURVIVES the audit fixes; the earlier "smoke 30-83 blocks =
acceptance FAIL" verdict was a category error (live "4h" preset
compared against the R1-R3 research floor).  E8 KILL and CLOSED
status stand; revival still requires a new dated prereg on the
current code.

#### E8b REVIVAL PREREG -- OB-RETEST 4H, CORRECTED DETECTOR
(frozen 2026-09-22, BEFORE any run code/executes; the freeze commit
hash IS the prereg reference)

MOTIVATION AND SCOPE.  The E8 KILL (prereg 7105724) adjudicated the
BUGGY detector: fixed breakout check at exactly pivot+50 (A1/A2),
look-ahead reversal median (A3), unconfirmed-pivot structure filter
(A4, inert on R2), absolute liquidity_tolerance (A5), no zone-intact
guard (A6).  "OB as tested has no edge" does not automatically
transfer to the corrected generator.  Post-fix, the research
acceptance re-PASSes (R1-R3, A1-A5, all 10 assets; log
runs/ob_research_check_postfix.log), so a candidate exists.  This
prereg is OB REVIVAL #1.  It is NOT a re-adjudication of E8 and NOT
a tuning iteration: the detector code is FROZEN at commit 759d74c
(audit fixes + batches 1-4); no detector, preset or runner parameter
may change between this freeze and the run.

ONE-SHOT RULE.  Whatever the outcome, the revival question closes
with this run.  FAIL -> the OB track is PERMANENTLY dead; no further
revivals absent a genuinely different mechanism (different ENTRY
LOGIC, not preset/parameter changes -- the min_extreme_gap=8 and
wick-entry policy items die with it).  PASS -> the E6-family
follow-up pattern applies (risk-overlay prereg first; no direct
live).  Family ledger gains a NEW line "OB-revival"; family
false-positive budget remains 0 until a PASS.  Declared a priori:
the prior for PASS is LOW (E8 lost to random geometry at n=5872);
the revival is justified by the identified detector defects, not by
hope.

ENTRY (frozen, identical to E8): OB-retest events on the 4H grid
from RESEARCH preset R2 (experiments/ob/research_presets.py at the
freeze commit); demand retest -> long, supply retest -> short;
entry bar = the detector's retest bar; WARMUP 400; same-bar
opposite-side duplicates kept.  R1/R3 are sensitivity references,
descriptive only, never gated, never switched post-hoc.  DECLARED
DEGENERACY: post-fix R1 == R2 == R3 output-identically on this
universe (the A2 fix folded multiple_breakouts into the window
scan), so the R-axis sensitivity is vacuous; the only live
sensitivity contrast is R2 vs R4_diagnostic (structure filter ON).

FRAME (frozen, identical to E8/E6/E7 -- deliberately unchanged so
E8 vs E8b is apples-to-apples): stop 3xATR14, TP 5R, horizon 500,
fee 10bp RT, S1-sized account stream, SPLIT_FRAC 2/3 -> PRIMARY
(pre-2025) and F3 (post-2025) segments.

NULL (frozen, identical protocol): matched random-geometry,
per-geometry, 100 draws, seeds 0..99, drawn at the SAME entry count
as the revival run.

GATES (frozen, identical thresholds): E-a pooled NW EV > null mean
+ 0.05R on BOTH segments; E-b EV >= 95th null percentile on BOTH
segments; kill on E-a/E-b failure.  Then E-c Sharpe >= 1.0,
E-d DD <= 25%, E-f bootstrap CI > 0 (seed 11, block 500).

DECLARED DIFFERENCES vs E8 (all detector-side, this is the TESTED
CHANGE SET): causal reversal warmup (reversal_warmup_bars=500);
breakout window [lookback_min, lookback_max), first valid wins
(replaces fixed pivot+50); confirm-guarded structure filter;
relative liquidity_tolerance; require_zone_intact=True.  Nothing
else differs from the E8 run configuration.

FORBIDDEN: preset/parameter edits, null re-drawing or re-seeding,
segment redefinition, added filters, any detector commit between
freeze and run, reading any EV/return output before this freeze is
committed.  Descriptive (non-gating) read-outs allowed after the
run: funnel decomposition (experiments/ob/detector_funnel.py),
retest-delay distribution, EV vs pivot age, per-asset spread.

RUNNER: experiments/avsl/retest_entry.py kind "ob" (unchanged;
imports R2 from the frozen presets module).  Log:
runs/retest_e8b.log.  Pre-run invariant: research_preset_check
A1-A5 must PASS on the run day (it does as of this freeze).

#### E8b RESULT (2026-09-22, runs/retest_e8b.log; prereg 1ce933e):
#### PASS -- WEAK per family multiplicity

Runner unchanged; detector frozen at 759d74c (no commits between
freeze and run).  9571 entries (R2 preset, corrected detector; E8
had 8538 on the buggy one).  Gates, both segments:

  PRIMARY: EV +0.165R (n=6613, NW z +3.40) vs null +0.051+-0.022
           -> E-a PASS (+0.114R > 0.05R margin), E-b 100th pct;
           Sh +2.10 (E-c PASS), DD 6% (E-d PASS),
           CI [+0.0319, +0.0629] (E-f PASS).
  F3:      EV +0.251R (n=2958, NW z +5.72) vs null +0.073+-0.039
           -> E-a PASS (+0.178R), E-b 100th pct;
           Sh +2.62 (E-c PASS), DD 17% (E-d PASS),
           CI [+0.0410, +0.0997] (E-f PASS).

All six gates pass on BOTH segments -- the first PASS in the
family ledger.  The WEAK label is the runner's frozen multiplicity
downgrade (addendum 68953e0; any PASS through this runner is
WEAK), and the prereg independently prescribes the E6-family
consequence: risk-overlay prereg BEFORE any live use; no direct
live entries from this verdict.

Reading (descriptive, non-gating): the swing E8 -> E8b
(-0.034R -> +0.165R PRIMARY, both at n~6k) is consistent with the
audited defects having been signal-relevant, not cosmetic -- most
plausibly the fixed pivot+50 breakout check (entries were taken
~50 bars after the actual breakout) and the look-ahead reversal
median.  Caveat kept on record: this is the corrected detector's
FIRST and ONLY confirmatory test; the family false-positive
accounting now has one issued PASS (WEAK) at risk.

Family ledger amendment: re-tests 3/3 (E8 KILL) + OB-revival 1/1
EXECUTED -> 1 PASS (WEAK) issued.  Per the frozen one-shot rule
the revival question is CLOSED: no further OB revivals absent a
genuinely different entry mechanism.  Queue consequence: OB
risk-overlay prereg is BACKLOG (after the user-directed AVSL
productization); min_extreme_gap / wick-entry policy items are
moot for live until that overlay prereg exists.

### AVSL PRODUCTIZATION IMPLEMENTED (2026-09-23)

The two files named by the frozen live-scale prereg are written:
experiments/live/parity_check.py (PARITY hard gate g1: frozen-sha
pinning of engine/passed/avsl_cross_s1.py + full-series
recomputation vs the tracker's incremental record; repaint,
missed-entry, nondeterminism -> exit 1 / update abort) and
experiments/live/pilot_tracker.py (seed / update / snapshot:
incremental paper entries from the refreshed kline cache,
PROVISIONAL trades re-priced until the exit bar closes, S1 sizing
at entry, accrual mirroring the frozen evaluate(), read-outs
r1 rolling-90d daily Sharpe + mechanical disaster brake (arms
after 90 daily obs; brake_on < 0; brake_off >= 0 with a
"dated STATUS note required" event), r2 500-bar ATR percentile +
regime tag, r3 corr(|daily ret|, active mean S1 size), r4
closed-trade rate vs the F3 reference computed at seed, g4 pilot
DD).  Runbook: experiments/live/README.md.  Smoke on the local
cache (offline): seed (pilot start bucket 124306, F3 ref 0.970
trades/day) -> update --no-fetch (parity OK, 0 new bars) ->
snapshot (r2 = 91, high-vol) -> standalone parity OK; ruff and
mypy clean.  STATE IS LOCAL (runs/ is gitignored) -- seed must be
re-issued on the machine that runs the pilot.  The Phase A clock
starts at the FIRST update that ingests fresh bars (i.e. after
the first online `load_binance` refresh); seed date recorded in
state.  Next: schedule the cron per the runbook; first weekly
snapshot into STATUS.

#### OB CONFIRMATION + SIZING PREREG (frozen 2026-09-23, BEFORE
#### any run code; the freeze commit hash IS the prereg reference)

Reframe: E8b PASSED with DD 6%/17% already inside the G2' cap, so
this is NOT an DD-fix overlay -- it is the E8b-prereg's promised
confirmation step: missing checks (long/short, per-asset, regime,
AVSL correlation) + sizing ablation + portfolio fit.  The E8b
one-shot rule is unaffected: the revival question stays closed;
this prereg adds NO new multiplicity to the entry verdict (same
signal, same data path, no E8c on any preset).

SIGNAL (frozen, identical to E8b): OB-retest events on the 4H grid
from RESEARCH preset R2 (post-fix, experiments/ob/research_presets.py
as of the freeze commit); demand -> long, supply -> short; entry =
retest bar close; stop 3xATR14; TP grid {3, 5, 8}R with PRIMARY =
5R; horizon 500, stop-first within-bar; fee 10bp RT; universe BTC
AVAX BNB DOGE ETH LINK LTC NEAR SOL XRP (Binance 1H -> 4H);
WARMUP 400; split 2/3 PRIMARY / 1/3 F3.

ARMS (frozen before code; sizing only, signal untouched):
  A   raw 1x per trade (the E8b baseline config)
  S1  vol-target: size = clip(0.20 / rv100, 0.25, 2.0)
  S3  concurrency cap: skip entry if >= 5 open trades or open
      exposure >= 3x base (size 1); processed on PRIMARY (5R) exits
  S5  S1 x regime: ATR14 pct (500-bar) > 80% -> size x 0.5
S-parameter values are frozen; exits for all arms computed at
PRIMARY 5R; TP {3, 8}R are per-trade descriptive read-outs only.

GATES (per arm, BOTH segments, thresholds identical to the AVSL
overlay): G1' Sharpe_NW >= 1.0; G2' event DD <= 25%; G3' net EV
>= 0.10R; G4' >= 7/10 assets positive; G5' block bootstrap CI
(B=1000, block 500) excludes 0.

KILL RULE (frozen interpretation): arm A is the PRIMARY gate
target -- ANY A gate FAIL in either segment -> OB CLOSED FINAL,
no sizing rescue.  Among arms passing ALL gates on both segments:
risk-first pick, order S3 > S5 > S1 > A (most conservative
exposure first).  An S-arm failing while A passes is an ablation
finding, not a kill.

NULL (descriptive, NOT gated): matched random-geometry, per-asset
entry counts + p_long matched, 100 draws, seeds 0..99, arm A at
TP 5R; reported as EV percentiles per segment.

READ-OUTS (non-gating): long/short EV + win rate per segment;
per-asset EV distribution; ATR-pct quintiles x EV; correlation of
the OB arm stream vs the AVSL 4H S1 backtest stream (same global
grid, per segment).

RULES: one pass, all arms x 2 segments; no signal or threshold
edits; no S-variants added after the run; no tuning on F3; no
E8c on any preset.  Runner: experiments/ob/ob_risk_overlay.py;
log runs/ob_risk_overlay.log.

#### OB CONFIRMATION + SIZING RESULT (2026-09-23; prereg 83c2b3f)

VERDICT: KILL -> OB CLOSED FINAL.  Arm A (raw, the frozen gate
target) FAILED G2' in BOTH segments: event DD 86% PRIMARY / 62%
F3 vs the 25% cap.  All other A gates passed (G1' Sh +1.00/+1.31;
G3' EV +0.15R/+0.26R; G4' 8/10 and 10/10 positive assets; G5'
CI excludes 0 both; descriptive matched-null: EV 100th pct both
segments) -- the PER-TRADE edge is real, the ACCOUNT-LEVEL drawdown
is not survivable at 1x sizing.  No sizing rescue: S1 DD 29%/23%
and S5 29%/22% also breach G2' PRIMARY; S3 collapses (90/9571
trades kept, EV -0.07R/-0.22R, G1'/G3'/G4'/G5' all F) -- the
concurrency cap is toxic for OB exactly as it was for AVSL
(clusters carry the edge; law of method confirmed twice).

GRID-ALIGNMENT DISCOVERY (evidence-trail finding, recorded here
because it touches E8b too): the 10 Binance 4H series start at
buckets 109056..111302 (~374d spread), but retest_entry.py (E6/E7/
E8/E8b) and the frozen module's evaluate() place trades in the
portfolio stream by ASSET-LOCAL indices.  Per-trade EV, the
matched-null percentile comparison, and segment EVs are
unaffected; stream-based metrics (Sharpe/DD/CI) are not: this
runner's TRUE-alignment arm A shows Sh +1.00/+1.31 DD 86%/62%,
while the legacy convention sensitivity gives Sh +1.62/+1.90 DD
29%/51%.  The kill is convention-robust (A fails G2' under both).
E8b's frozen E-d margin (S1-sized DD 6%/17%, legacy convention)
should be treated as convention-dependent; its EV/null/E-z verdict
inputs are convention-free.  No gate re-adjudication was done
here (one-shot rule); flagged for the ledger.

READ-OUTS (non-gating, arm A, true alignment):
- Long/short: PRIMARY long +0.473R (n=2924, WR 27%) vs short
  -0.169R (n=2938, WR 18%); F3 long +0.268R / short +0.243R
  (both sides positive late).  PRIMARY shorts are the DD engine.
- Per-asset: 9/10 positive pooled (XRP -0.008R); ETH +0.353 best,
  LTC +0.045 weakest of the positive.
- Regime: monotone low-vol edge -- Q1 (ATR pct 0-20] +0.333R,
  Q5 (80-100] +0.102R.  Same direction as the AVSL regime slice.
- Corr with AVSL 4H S1 stream: +0.13 PRIMARY / +0.10 F3 -- would
  have diversified strongly (portfolio-fit was NOT the problem;
  moot under CLOSED FINAL).
- TP grid (descriptive): EV rises with TP -- 3R +0.142/+0.188,
  5R +0.151/+0.255, 8R +0.235/+0.327 (PRIMARY/F3).  If any OB
  geometry is ever revisited from scratch, 8R dominates; frozen
  PRIMARY stays 5R, noted only as ledger fact.

Process notes: run 1 crashed in the corr read-out (segment/full-
stream length mismatch, pure reporting bug); fixed and rerun --
gate numbers reproduced identically; corr, null and the TP-grid
snippet completed on the rerun.  No signal, gate or sizing edit
was made at any point after the freeze.

#### E8b ADJUDICATION (2026-09-23, principal decision)

E8b PASS (WEAK, 95c06e2) -> **FAIL**, adjudicated under true grid
alignment: the recompute of the identical frozen frame (same 9571
trades, same S1 sizing, prereg 83c2b3f run) passes E-a/E-b/E-c/E-f
but FAILS E-d on the PRIMARY segment (DD 29% vs 25% cap; legacy
convention had shown 6%).  Convention-free inputs (per-trade EV,
matched-null percentile) PASS comfortably -- the revival question
E8b answered stays answered YES; the track dies on account-level
risk, which is structural (PRIMARY short EV -0.169R, WR 18%;
overlapping clusters; S5 shows the DD is not a vol-regime event;
no sizing rescue: S1/S5 breach G2' PRIMARY, S3 toxic 90/9571).
OB CLOSED FINAL, one-shot preserved.  Full record incl. E-gate
table, root cause and the R-OB-1/2/3 BACKLOG revival candidates
(explicitly NOT pre-registered; R-OB-2 flagged as pass-by-
construction): experiments/ob/e8b_adjudication.md.
Focus: AVSL Phase A.

#### AVSL PREREG CONVENTION CHECK (2026-09-23; diagnostic, no
#### gate/signal/sizing edit; script
#### experiments/avsl/grid_alignment_check.py)

Question: is the only issued PASS (AVSL-cross S1, overlay verdict
e6b4b4d) robust to the grid-alignment convention that killed E8b?
Method: identical trades (n=2939), sizes and thresholds as
evaluate(); stream rebuilt with e0/e1 shifted to the true global
4H grid.  Legacy numbers reproduce the frozen verdict bit-for-bit
(Sh 1.50/2.84, DD 22%/12%, EV +0.17/+0.33) -- baseline OK.

RESULT: the AVSL PASS is NOT convention-robust.  True-aligned:
PRIMARY NW-Sharpe +1.23 (PASS), DD 26.0% (FAIL, cap 25%), EV
+0.16R PASS, 9/10 assets, CI +0.0008 (PASS, marginal); F3 DD
28.9% (FAIL; trough 2024-09-15 -- the first epoch where all 10
assets trade concurrently, which the legacy convention silently
time-diversified away), EV +0.32R, 7/10, CI +0.0157.  So G2'
fails BOTH segments under honest alignment, by 1-4pp (vs OB's
86%/62%) -- the DD margin of the issued PASS was largely a
convention artifact; EV/CI/breadth margins are convention-free
and stand.

ENGINE OBSERVATION (recorded, module untouched): nw_sharpe can
blow up on sparse streams -- true-aligned F3 sum_rho = -1.7
sends the NW factor to its 1e-6 floor (printed Sh +9076);
plain Sharpe +9.08 / DD 28.9% are the meaningful F3 figures.
Any successor metric work should floor the factor sanely (new
prereg territory; frozen module is read-only).

OPERATIONAL CONSEQUENCE (principal to adjudicate; Phase A NOT
stopped): the live pilot (paper-only) remains a valid ops/parity
instrument -- its g4 pilot DD is measured live, not inherited
from the backtest -- but **Phase B (real capital) is BLOCKED**
until this finding is adjudicated: either a new dated prereg
re-issues the verdict under true alignment (fresh multiplicity
budget), or the principal accepts the verdict with the DD
convention caveat on the ledger.  Convention-free evidence
(NW-z +3.31/+3.85 per-trade, EV, breadth) is unaffected.

#### PHASE A CLOCK STARTED (2026-09-23)

Machine turned out to be online -> clock started same day.
pilot_tracker seed: pilot_start_bucket 124317 (2026-09-23), F3
reference rate 0.964 trades/day; first ONLINE update: cache
refreshed incrementally (all 10 assets, gaps=0), PARITY OK
(tracker == full recomputation, pilot window), +0 entries; first
snapshot taken (snapshots=1): parity OK, r2 ATR pct 91 (high-vol),
brake idle, g4 pilot DD 0.0%.

OPS POST-MORTEM (two bugs found and fixed at first live use; both
in pilot infra, neither touches signal/gates/frozen module):

1. parity_check.refresh_cache called the loader as
   experiments.load_binance -- wrong path (real module:
   experiments.loaders.load_binance) AND with bare asset tags
   (BTC...), which fall through the loader's symbol filter and
   silently trigger a fetch of its ENTIRE default universe.
   Fixed: correct module path + full Binance symbols (BTCUSDT...).
   First failed update (no fetch, stale cache) was aborted by the
   runbook's own failure rules -- machinery worked as designed.

2. pilot_tracker.cmd_seed set pilot_start_bucket = max(b[-1]) --
   the newest CACHED bucket, whose close was already determinable
   at seed time.  Its entries can never be recorded by the seed,
   so the first update flagged XRP entry (124306, long) as a
   missed closed-bar entry -> PARITY FAIL -> STOP per g1 (the g1
   gate fired exactly as designed on a real defect).  Post-mortem:
   off-by-one in the seed boundary convention.  Fix: start =
   b[-1] + 1 -- the pilot trades only buckets whose close happens
   AFTER the seed (conservative; independent of intra-bar cache
   state).  State wiped and reseeded; the aborted seed never
   entered the ledger clock.  Resume-after-STOP formally satisfied
   by this dated note (root cause + fix recorded before the new
   seed's first update).

Cadence next: cron per experiments/live/README.md (update 4x/day
>= 15 min after 4H close; snapshot weekly -> STATUS).  Reminder
on the ledger: Phase B stays BLOCKED pending the AVSL DD
convention adjudication (see above); Phase A (paper ops) proceeds.

#### PHASE A OPS: CRON LIVE + POST-MORTEM #3 (2026-09-24)

Cron installed on the ops machine (Windows scheduled tasks, TZ
UTC+3 fixed): TINV_AVSL_pilot_update every 4h at 03:20/07:20/
11:20/15:20/19:20/23:20 local (= 20 min after each 4H close),
TINV_AVSL_pilot_snapshot weekly Sun 12:00; both append to
runs/live_pilot/cron_*.log.  Setup script kept at
runs/live_pilot/setup_cron.ps1 (gitignored).  Same-day fix:
the registered actions passed `>>`/`2>&1` straight to
python.exe, but redirects are shell features -- the scheduler
executes the exe directly, so every run died with 0x800700E0
and no log.  Actions re-registered via cmd /c wrapper +
StartWhenAvailable (catch-up after sleep, within the +-30 min
tolerance); verified end-to-end by a manual task start
(PARITY OK, LastTaskResult=0, log written).  Same-day follow-up:
a >2h sleep caused 2 missed repetitions; StartWhenAvailable
fired the catch-up correctly on wake (PARITY OK, result=0).
Battery defaults were also fixed (DisallowStartIfOnBatteries /
StopIfGoingOnBatteries -> False in setup_cron.ps1) -- a laptop
on battery would otherwise silently skip runs.  LIVE OPS PAUSED
by principal decision (2026-09-24 evening): both scheduled tasks
DISABLED (not deleted -- setup intact, re-enable =
Enable-ScheduledTask or re-run setup_cron.ps1 in a dedicated
session).  Last state on pause: parity OK, 1 provisional entry
(XRP 124317 short), no gate fired.  Resume requires a fresh
session-level go.

POST-MORTEM #3 -- parity gate vs recording order (found at the
first update that closed an in-scope entry; XRP short @124317):
the gate demanded every closed in-scope entry to be ALREADY in
state BEFORE _update recorded it -- structurally, the pilot's
first entry could never pass (observed: PARITY FAIL on a healthy
state, two aborts).  Two defects fixed in pilot_tracker._update:
(1) gate moved AFTER the recording pass, per the parity
docstring's own semantics (#3: the check that the tracker missed
no closed-bar entry is meaningful only against recorded state);
(2) state persisted BEFORE the independent check -- parity_ok
reads state.json from disk, and previously compared against the
stale pre-update file.  Post-fix first live entry recorded and
PARITY OK (tracker == full recomputation, 1 entry, provisional).
All three pilot defects were caught by the pilot's own gates
(g1 fired twice, fetch failure surfaced as +0/abort) -- no
silent divergence at any point.  Frozen module untouched.

#### SVD DIAGNOSTIC (LEVEL 1): UNIVERSE IS STRUCTURALLY ONE-FACTOR
(2026-09-24, diagnostic only -- no frame/gate/sizing change)

experiments/diagnostics/svd_factors.py: eigenspectrum of the 4H
log-return correlation matrix over the AVSL 10-asset universe,
13,018 aligned closed 4H buckets (~6y).  Results:
lambda = [6.70, 0.61, 0.51, 0.45, 0.41, 0.34, 0.32, 0.27, 0.25,
0.15]; PC1 = 67% of variance; mean pairwise corr +0.63; PC1
loadings uniform +0.26..+0.35 (classic market factor); corr(PC1
score, BTC return) = 0.85 -- PC1 IS crypto-beta.  Per-asset corr
to BTC 0.56 (DOGE) .. 0.83 (ETH).

Naive plan metric n_eff(90%) = 6 would read "multi-factor, do
portfolio optimization" -- MISLEADING: the tail eigenvalues just
pool noise (they sum to 33%).  Marchenko-Pastur with q = 1302:
lambda_plus = 1.056; exactly ONE eigenvalue (6.70) exceeds it --
under RMT the correlation structure is RANK-ONE.

Consequences (recorded, NOT acted on):
- Cluster DD (AVSL 29%/23% both S-gates fail; R-OB-1 long-only
  50%/53%) is structural: 10 positions = 1 bet.  Universe
  problem, not sizing.  Consistent with shorts having been a
  partial hedge of the same factor (removing them doubled DD)
  and with S3's cap cutting signal rather than factor exposure.
- Sizing/portfolio-layer SVD (levels 2-4: RMT cleaning, SSA,
  principal portfolios) is DEFERRED: cleaning a rank-one matrix
  cannot create the diversification that is not there.
- If a universe decision is ever taken (assets with independent
  BTC beta), re-run this diagnostic as the entry gate, then
  re-evaluate levels 2-4 on the new structure.
- Frozen AVSL/OB frames and the live pilot are untouched; the
  pilot continues on the current universe per its prereg.

#### SVD FOLLOW-UP LEDGER: R-SVD-1..6 REGISTERED (2026-09-24)
Backlog registration ONLY -- none prereg'd, no code, no gates
frozen.  All six are NEW families (decomposition-driven, not
E8/AVSL/OB multiplicity); each needs its own prereg before code.
Rank-one context (see diagnostic above) applies to all: SVD
cannot create diversification; these are separation/monitoring
tools, not signal sources.

- R-SVD-1 PC1 net-exposure cap (candidate S3 replacement).
  Priority HIGH.  Feasibility numbers from the frozen S1 backtest
  (2941 trades / 14411 buckets): gross concurrency mean 12.1,
  p90=23, max 42 (>=5 concurrent 78% of time) -- BUT net signed
  factor exposure p50=4, p90=12, p99=20, range [-24,+23]:
  longs/shorts offset ~2/3 of gross.  This is the material
  difference from S3: S3 capped GROSS (and cut the offsetting
  hedges -- edge died); a PC1 cap limits NET and leaves natural
  long/short offset alone.  Hypothesis alive, not dead-on-
  arrival.  Pre-reg (when written) must freeze ONE cap rule a
  priori (e.g. cap = historical p90 of net exposure) + gates:
  DD must drop materially, per-trade EV must survive.
  DD-CONCENTRATION CHECK (2026-09-24, decision gate before
  prereg): FAILED -- scenario B.  Buckets grouped by |net PC1|
  quintiles (edges 2/4/6/10); global max-DD episode losses:
  Q1 19.9% / Q2 12.9% / Q3 18.8% / Q4 14.4% / Q5 34.1% -- Q5 is
  far below the 50% concentration bar, and LOW-exposure Q1+Q2
  carry 32.8%.  Restricted (group-only) max DDs are flat across
  quintiles (1167-1738% of 1%-risk units, LOWEST in Q4/Q5) --
  factor-exposure level is not the DD engine.  Moreover Q5
  buckets hold the bulk of PROFIT (+20.7k of ~+31.5k total
  PnL): a total cap at p90 would clip the strategy's best
  buckets along with a third of episode losses -- the S3
  failure mode returns through the back door.  VERDICT: the
  drafted total-cap prereg is expected to fail its own G1/G2;
  NOT WRITTEN.  R-SVD-1 moved to PARKED.  A different mechanism
  (e.g. incremental-exposure cap per new signal) would be a new
  feasibility question, not a fix of this one; no such prereg
  is scheduled.
- R-SVD-2 residual cross-sectional market-neutral (PC1-orthogonal
  spreads, C(10,2) pairs).  Priority MED.  Residual variance is
  33% of total on this universe -- thin but nonzero material.
- R-SVD-3 lambda1(t) rolling regime indicator (factor
  concentration, NOT vol-target; E5 showed vol regime does not
  explain DD).  Priority MED; diagnostic-first like L1.
  REDEFINED 2026-09-24 as crash detector for halt (after the
  DD-quintile check showed DD is timing-structural).  Feasibility
  gate (experiments/diagnostics/lam1_crash_check.py, rolling 30d
  PC1 share vs top-5 DD episodes): FAILED -- (a) baseline share
  is ALREADY 0.73 mean (p10-p90 = 0.62..0.83): on a rank-one
  universe correlations->1 is the permanent state, the signal has
  no dynamic range; (b) episodes caught only weakly and
  inconsistently: in-episode mean share at 84th/73rd/58th
  percentile for the 34R/30R/24.5R episodes -- the 24.5R one at
  baseline; (c) decile PnL flat (+0.00..+0.05 R/bucket, no
  monotone structure, D9-D10 hold ~0 PnL) -- a halt keyed at any
  percentile either misses the episodes or halts a third of the
  time for no PnL saving.  PARKED, same verdict class as
  R-SVD-1: the rank-one structure that motivated the SVD family
  also neuters its regime signal.
- R-SVD-4 funding-rate SVD / cross-sectional carry revival
  (carry closed at F3 1.45%; SVD regime filter is the revival
  hypothesis).  Priority MED; funding data on disk.
- R-SVD-5 lead-lag via lagged SVD.  PARKED: needs 1m/tick data
  (cache is 1h minimum).
- R-SVD-6 SSA denoising of signal/EV series.  PARKED:
  monitoring tool, post-processing, lowest priority.
Order of execution: R-SVD-1 pre-reg mechanics -> freeze -> one
historical pass (same discipline as R-OB-1).  The others wait;
running several SVD families at once would be the multiplicity
error the ledger exists to prevent.

#### R-SSA FAMILY REGISTERED; R-SSA-1 FEASIBILITY FAIL (2026-09-24)
Per-asset SSA denoising (the original CT-perfusion-inspired idea)
is a DIFFERENT family from cross-asset R-SVD and was never tested.
Registered R-SSA-1 (SSA on the AVSL line), R-SSA-2 (SSA on price
before the OB pivot detector), R-SSA-3 (SSA on signal streams).
R-SSA-1 feasibility gate (experiments/diagnostics/
ssa_avsl_check.py, causal SSA W=30 k=3 -- last-point Hankel
reconstruction, no lookahead; identical frozen entry/exit
machinery; baseline validated byte-exact: 2941 trades):
  - cross reduction only 1% (2941 -> 2909); EV/trade +0.217 ->
    +0.195; total R 639 -> 568; sum per-asset max-DD 341 -> 384R.
  - GATE FAIL: EV fell, DD rose, crosses did not shrink.
  - MECHANISM: double-smoothing redundancy.  AVSL is already an
    SMA(SLOW=345) of adjusted price -- a low-pass filter ~11x
    wider than the SSA window.  SSA-30 on top of SMA-345 sees an
    almost-linear segment, keeps it (top-3 components ~= identity)
    and only perturbs the line; the latency cost lands as pure
    EV decay.  Denoising an already-denoised signal.
  - VERDICT: R-SSA-1 PARKED (structural, not tunable: any window
    < SLOW inherits the argument a fortiori).  The redundancy
    argument does NOT transfer to R-SSA-2 -- the OB detector
    pivots on RAW price, which is genuinely noisy -- so R-SSA-2
    stays the live candidate of this family (feasibility before
    prereg, same protocol).  R-SSA-3 stays parked (monitoring).

#### R-SSA-2 FEASIBILITY GATE -- PREREG FROZEN (2026-09-24,
#### before this code; runner experiments/ob/rsa2_check.py)

Hypothesis: SSA-denoised close (wick shape preserved) reduces
micro-pivot noise in the OB detector -> fewer false blocks ->
better signal quality.  Non-redundancy rationale: the ZigZag
reversal threshold (2.5 x median ATR) is a MAGNITUDE filter,
not a smoothing filter -- a different operator class from SSA.

Design (ONE config, frozen, no tuning):
- SSA W=30, k=3, causal last-point Hankel reconstruction
  (identical machinery to the R-SSA-1 gate; buckets t<30 use
  raw values -- declared).
- Variant C: close_ssa = SSA(close);
  high_ssa = close_ssa + (high - close);
  low_ssa  = close_ssa - (close - low).
  OHLC invariant preserved; ZigZag sees a smooth center with
  raw wick extents.  SSA on high/low separately is REJECTED
  (can break high >= close >= low).
- ISOLATION: only the DETECTOR input changes.  Retest-bar
  entries, stops 3xATR14, TP {3,5,8}R primary 5R, horizon 500,
  fee 10bp RT, WARMUP 400 are computed on RAW OHLC/ATR exactly
  as in the frozen E8b frame (ob_risk_overlay._trade_tp).
- Arms: A = raw OHLC -> R2 detector; B = SSA-OHLC -> R2
  detector.  R2 preset frozen (research_presets.R2).
- Matched null (seeds 0..99) DEFERRED to a potential post-gate
  prereg -- the gate below is a relative A/B and needs no null.

Read-outs: retest-event and trade counts, EV/trade, win rate,
total R, max DD of the equal-risk cum-R stream, long/short
split (pooled); per-asset table; SIGNAL LAG: median distance
in bars from each SSA retest event to the nearest raw retest
event (critical for interpreting any EV change).

Gate (declared before running): PASS iff B.EV >= A.EV AND
B.maxDD < A.maxDD.  Otherwise R-SSA-2 PARKED with mechanism;
the denoising direction for OB is considered closed.  One-shot:
no W/k search, no post-hoc variants.

VERDICT (2026-09-24, one-shot run of rsa2_check.py): FAIL --
decisively and with the OPPOSITE sign.  B produced MORE events
than A (13,941 vs 9,821, +42%), not fewer: the SSA-shifted
close path crosses the 2.5-ATR reversal threshold at different
points and triggers MORE ZigZag legs.  Quality collapsed:
EV/trade +0.1908 -> +0.0566 (-70%), win 0.226 -> 0.199, total R
1828 -> 770, equal-risk maxDD 105.7 -> 308.6R.  Per-asset: all
10 assets worse on DD, 8/10 worse on EV -- uniform, structural.
Signal lag median 3 bars (12h) -- lag alone does not explain a
70% EV loss; the SSA-shifted pivots are simply worse entry
geometry (retest bars land at different, degraded locations).
Baseline A internally consistent (9,585 trades, L/S 4746/4839).
CONSEQUENCE (per the frozen gate): R-SSA-2 PARKED; the
denoising direction for OB is CLOSED -- neither cross-asset
factor tools (R-SVD-1/3) nor per-asset smoothing (R-SSA-1/2)
improve the frames; the ZigZag magnitude filter is already the
right noise operator for pivot detection, and perturbing its
input strictly degrades it.  Both families remain registered
for the ledger; no further denoising preregs scheduled.

#### R-SVD-2 FEASIBILITY GATE -- PREREG FROZEN (2026-09-24,
#### before this code; runner experiments/diagnostics/rsvd2_check.py)

Hypothesis: residuals after PC1 removal contain cross-sectional
mean-reversion structure tradeable on the 10-asset universe,
with PnL approximately orthogonal to crypto-beta (hence to the
AVSL S1 stream, which trades PC1).

Design (ONE config, frozen, no tuning):
- Returns: 4H log returns, common aligned buckets (as L1).
- W = 180 bars rolling SVD window of the correlation matrix.
- PC1 loadings: top eigenvector, sign convention max-|loading|
  component positive; RECOMPUTED ONLY every 24 bars at rebalance
  points from R[t-W:t] (strictly past -> causal; also stabilizes
  loadings and caps turnover).  Between updates the previous
  loadings apply.
- Residual: E(tau) = R(tau) - b * (b' R(tau)) with b the current
  unit loadings vector (orthogonalization w.r.t. PC1); the N-bar
  signal uses current loadings applied over the trailing N bars.
- Signal: cumulative residual over N = 30 bars; direction MR:
  long bottom-3, short top-3, equal weight within baskets,
  basket notional 1 each.
- Rebalance: every 24 bars (4 days); positions held over
  (t, t+24]; period PnL = mean(long rets) - mean(short rets).
- Fee: 10bp round-trip per side basket -> net period PnL =
  gross spread - 0.002.  First rebalance at t = W + N.
- Periods/year for Sharpe annualization: 365/4 = 91.25.

Read-outs: gross and net Sharpe, EV per rebalance, total net,
max DD of the net stream, long/short basket averages, corr(net
period PnL, AVSL S1 equal-risk stream aggregated to the same
rebalance windows), corr(net period PnL, BTC return summed over
the same windows).

Gate (declared before running):
- PASS   = net Sharpe >= 1.0 AND corr(AVSL) < 0.3
- PARKED = net Sharpe < 0.5 OR  corr(AVSL) > 0.5
- NEUTRAL = in between (post-mortem, no prereg without a new
  mechanism hypothesis).
PASS -> full R-SVD-2 prereg with declared arms N in {10, 30, 90}
(and no other tuning).  PARKED -> structural fail with mechanism
recorded; the SVD family closes.  One-shot: no W/k/N search.

VERDICT (2026-09-24, one-shot run of rsvd2_check.py, 533
rebalances, full history): PARKED.  net Sharpe = -1.03 (gross
-0.74), total net -3.77 on notional-1 baskets, maxDD 4.08 --
far below the 0.5 park line.  Orthogonality worked exactly as
designed: corr(net, AVSL S1) = -0.02, corr(net, BTC) = +0.06 --
residual PnL is genuinely beta-free.  The failure is the MR
direction itself: long-losers/short-winners on 30-bar cumulative
residuals LOSES (gross -0.74), i.e. residuals exhibit residual
MOMENTUM, not reversal.  Note for the ledger only: flipping the
sign is post-hoc tuning under the one-shot rule and would still
miss the PASS bar (|gross| 0.74 < 1.0); no momentum prereg is
scheduled.  Data note: the first run aborted on NaN -- a
double-log bug in the runner (not dirty data); fixed before any
metric existed, no peeking occurred.  CONSEQUENCE: the SVD
family CLOSES.  Final tally: rank-one diagnostic stands (L1),
all four downstream hypotheses (R-SVD-1 PC1 cap, R-SVD-3
lambda1 halt, R-SVD-2 residual MR; R-SSA-1/2 smoothing on the
OB side) parked by their own predeclared gates with mechanisms
recorded.  Denoising/factor-decomposition yields no live track
on this universe.

#### PROTOCOL AMENDMENT P-2: TWO-LAYER VERDICTS (2026-09-24,
#### dated, PROSPECTIVE; non-retroactivity clause binds)

Motivation: the ledger recorded deploy-layer failures with the
same vocabulary as signal-layer deaths ("CLOSED FINAL"), which
conflates "no edge" with "edge alive, not deployable".  The
amendment refines classification; it does NOT re-run, re-score,
or unlock anything by itself.

Rule 1 -- two layers on every future prereg:
  SIGNAL layer: does the per-trade edge exist? (entry/exit
  geometry, frozen after prereg)
  PORTFOLIO layer: is it deployable? (sizing, cap, hedge,
  construction -- separate preregs allowed on signal-alive
  tracks without touching signal verdicts)
Verdict vocabulary: SIGNAL-DEAD / LATENT (signal-alive,
portfolio-blocked) / DEPLOYABLE.

Rule 2 -- family budget: max 3 preregs per family ABSENT a
structural kill.  A mechanism-level refutation (rank-one fact,
beta-window refutation, crowding measurement) closes the
family immediately regardless of budget -- score-based
closure alone does not.

Rule 3 -- non-retroactivity: no gate re-run, no seed/parameter
change, no family reopening.  A relabel below authorizes
nothing; every latent revival still requires its own one-shot
portfolio-layer prereg with pre-declared gates, and prior
mechanism evidence is honest input into whether to prereg at
all.  Adopting an amendment right after a losing streak to
unlock specific tracks is protocol-level p-hacking; hence this
clause.

LEDGER RECLASSIFICATION (documentation only, verdicts
unchanged):
- z-score track: SIGNAL-DEAD (no post-entry edge, cause
  established).  Not latent.
- AVSL-cross-as-entry (1H/4H/high-TF): SIGNAL-DEAD (edge did
  not survive confirmation).  Not latent.
- Donchian-4H: SIGNAL-DEAD (no config passes; entry retained
  only as a component, not a track).
- Funding carry v2/v3: mechanism-dead (crowding, premia eaten
  -- measured, not scored).  Basis trade = new family, not a
  revival.
- AVSL S1 (promoted engine/passed, live paused by principal):
  LATENT -- signal-PASS (per-trade edge), portfolio layer DD
  26% vs cap 25% (marginal).
- E8b OB: LATENT -- signal-PASS (weak, per-trade gates),
  portfolio-FAIL on deploy DD 29% vs 25%.
- R-OB-1 cap, S5 sizing, R-SVD-1/3, R-SSA-1/2, R-SVD-2,
  R-OH-1 hedge: mechanism-dead entries; they change neither
  signal verdicts nor latent status.
- HONEST PRIOR on latent revivals: the strongest
  portfolio-layer mechanism (beta-hedge) was tested first and
  REFUTED (DD windows are not BTC-crash windows).  Remaining
  portfolio-layer candidates on latent tracks (regime gate,
  split-exit) have materially lower priors; breadth into NEW
  signal classes (TTF, P4 low-cap carry, basis, multi-market)
  dominates further portfolio-layer work on latent tracks.

#### R-OH-1 FEASIBILITY GATE -- BETA-HEDGE OVERLAY (2026-09-24,
#### prereg frozen before code; runner experiments/ob/rhedge_check.py)

Hypothesis: OB DD is crypto-beta crash exposure; a short-BTC
overlay proportional to the portfolio's net PC1 exposure keeps
all OB signals (unlike the parked PC1 cap) while removing the
beta component of the stream.

Design (frozen):
- Signal: frozen E8b OB frame, ALL blocks, both sides, S1
  vol-target sizing -- the exact R-OB-1 machinery
  (ob_risk_overlay.base_trades/decorate), unmodified.
- Exposure: E(t) = sum over open trades of s1_i x sign_i
  (PC1 loadings are near-uniform 0.26..0.35, absorbed into the
  hedge calibration; declared simplification).
- Hedge: overlay return per bucket = -alpha x E(t) x r_BTC(t),
  true mark-to-market on BTC 4H simple returns; positions
  accrue per the frame's spread-over-hold convention (declared
  approximation).  No hedge costs (taker on rebalance would be
  ~2-4bp/bucket turnover; noted as read-out at PASS).
- Arms: alpha in {0, 0.25, 0.5, 1.0}; alpha=0 is the baseline.
  The alpha axis is EXPLORATORY by design (the question is
  whether ANY beta-neutrality level helps); a PASS leads to a
  prereg that freezes ONE alpha chosen by the declared rule
  (smallest alpha meeting the gate).

Gate (declared): PASS iff exists alpha > 0 with
maxDD(stream) <= 20% AND total return >= 0.8 x alpha-0 total
return.  Stream: S1-sized accrual + overlay, DD = running max
of the cum stream.  Otherwise R-OH-1 PARKED and the rank-one
DD reading ("structural, unfixable by overlay") is confirmed
by a fifth independent test.

VERDICT (2026-09-24, one-shot run of rhedge_check.py, 9585
entries, full grid n=15269): PARKED -- and the mechanism is
REFUTED, not just short of the bar.  Baseline alpha=0: total
+830 R-units, DD 29.3%, NW Sharpe +1.23 (metric cross-check
against R-OB-1 machinery: matches).  Every alpha makes
everything monotonically WORSE: alpha=.25 -> DD 30.5%, total
-1.4%; alpha=.5 -> DD 31.9%; alpha=1.0 -> DD 34.9%, total
-2.8%, Sharpe 1.20.  Reading: (a) the overlay has NEGATIVE
mean PnL -- E(t) is positively correlated with BTC drift, i.e.
the OB book is implicitly long the market on average, and
shorting that drift subtracts return without touching the DD
windows; (b) DD increases under the hedge, which means the OB
drawdown windows are NOT BTC-crash windows -- the DD is
asset-level idiosyncratic whipsaw, exactly the E5
'spread-over-time, not tail exposure' reading.  Conclusion is
robust to hedge costs (any cost only worsens the overlay).
This is the FIFTH independent confirmation that rank-one DD on
this universe is structural: S5 sizing, PC1 cap (R-SVD-1),
lambda1 halt (R-SVD-3), long-only split, and now beta-hedge
overlay all fail to touch it.  Regime-gated entry (R-OR-1) is
the only remaining OB-adjacent feasibility candidate from the
mechanism list; its premise is untouched by this result, but
the S5 prior stands.

#### R-OB-1 PREREG -- OB LONG-ONLY (frozen 2026-09-23, BEFORE any
#### run code; the freeze commit hash IS the prereg reference)

HONEST LABEL (recorded first): this is a DECOMPOSITION-DRIVEN
hypothesis.  Motivation is the measured long/short asymmetry of
the CLOSED OB track (PRIMARY short -0.169R vs long +0.473R;
shorts were the DD engine).  It is NOT an independent idea and
NOT an OB revival: OB stays CLOSED FINAL; E8/E8b ledgers gain no
multiplicity.  This is a NEW family "R-OB", one-shot, own kill
rule.  Aged since the OB closure: same session -- accepted
explicitly, with the label above, at principal instruction.

HYPOTHESIS: demand-block retest entries alone (long-only) carry a
per-trade edge AND a survivable account-level risk profile under
S1 sizing on the true grid -- i.e. the OB failure was a
short-side/overlap phenomenon, not a long-side one.

SIGNAL (frozen): R2 preset (research_presets.py as of the freeze
commit) DEMAND blocks only -> long entries at the retest bar
close.  Everything else identical to the E8b frame: stop 3xATR14,
TP grid {3, 5, 8}R with PRIMARY = 5R, horizon 500 stop-first,
fee 10bp RT, WARMUP 400, universe BTC AVAX BNB DOGE ETH LINK LTC
NEAR SOL XRP (Binance 1H -> 4H), split 2/3 PRIMARY / 1/3 F3.

ALIGNMENT (declared, lesson of the convention findings): TRUE
global grid -- absolute 4H bucket minus the earliest asset
bucket; every stream, segment split and read-out computed on
true-time placement.  No legacy-index numbers will be produced.

ARMS: single gate config -- S1 vol-target sizing
(clip(0.20/rv100, 0.25, 2.0), frozen-module formula).  Raw 1x is
NOT a gate arm; its account DD is a declared sensitivity
read-out (the OB kill came from raw-level DD; the ledger gets
the number either way).

GATES (both segments, thresholds unchanged from the family
precedent): G1' Sharpe >= 1.0; G2' event DD <= 25%; G3' net EV
>= 0.10R; G4' >= 7/10 assets positive; G5' block bootstrap CI
(B=1000, block 500) excludes 0.  Metric rule (frozen before the
run, symmetric): G1' uses nw_sharpe as implemented in the frozen
module; if the NW autocorrelation sum < -0.5 the factor is
degenerate (floored) and the G1' input becomes the plain
annualized Sharpe (mean/std * sqrt(6*365)) at the same 1.0
threshold.  The rule fires on the metric, never on the outcome.

KILL RULE: any gate FAIL in either segment -> R-OB-1 CLOSED
(does not touch OB CLOSED FINAL status).  One-shot: one pass, no
re-runs, no parameter or threshold edits after this freeze, no
F3 tuning, decisions on PRIMARY.

NULL (descriptive, NOT gated): matched random-geometry for the
long-only set (per-asset long counts matched, long side only,
100 draws, seeds 0..99, TP 5R); reported as EV percentiles per
segment.

READ-OUTS (non-gating): per-asset EV; ATR-pct quintiles x EV;
corr(long-only S1 stream, AVSL 4H S1 true-aligned stream) per
segment; raw-1x DD sensitivity; TP {3, 8}R descriptive EV.
Runner: experiments/ob/rob1_long_only.py; log
runs/rob1_long_only.log.

#### R-OB-1 RESULT (2026-09-23; prereg 44a0c75, one pass)

VERDICT: FAIL -> R-OB-1 CLOSED.  Gates (S1-sized, true grid):
PRIMARY NW-Sharpe +1.03 (PASS by 0.03), DD 50% (FAIL); F3 Sharpe
+0.55 (FAIL), DD 53% (FAIL), CI [-0.017,+0.140] (FAIL).  G3'/G4'
pass everywhere (EV +0.471R / +0.270R; 10/10 and 8/10 assets).

THE INTERESTING PART -- the prereg hypothesis is REFUTED at the
account level and the OB post-mortem story needs a correction:
- Per-trade: the long side is genuinely strong (null 100th pct
  BOTH segments, EV +0.471/+0.270, 9/10 assets positive pooled).
- Account: long-only DD (50%/53%) is MUCH WORSE than the full
  OB signal's S1 DD (29%/23%).  The shorts were not the DD
  engine -- they were a partial HEDGE: supply-block entries fire
  in downtrends that coincide with long-drawdown epochs, so
  removing them doubled the S1 DD.  The raw-1x sensitivity
  confirms (long-only 76%/93% vs full-signal 86%/62%).
- Corrected causal story for the OB ledger: the OB account
  failure is an OVERLAP-CLUSTER phenomenon on the LONG side
  (bull-window clustering), and the short side was carrying
  offsetting exposure.  Neither side is deployable alone; the
  cluster structure, not direction, is the risk driver.

Read-outs kept on the ledger: corr(rob1, AVSL S1) +0.08/+0.10 --
diversification potential was real but is moot under CLOSED;
regime profile of longs is NOT low-vol monotone (Q1 +0.481, Q5
+0.536) -- unlike the full signal; TP 8R descriptive +0.704/
+0.455 (consistently dominates the grid, per-trade view only).

Standing rule respected: no re-runs, no parameter changes, no
rescue attempts.  R-OB family: one member, CLOSED.  Remaining
backlog items R-OB-2 (pass-by-construction, recommended never to
run) and R-OB-3 (8R primary; post-hoc unless re-derived from
scratch on untouched grounds).  Focus returns to AVSL: pilot
cadence + the Phase B adjudication of the DD convention finding.


#### OPT-INTEGRATION (2026-09-25, step 1 of the options track:
#### Deribit API + data load; infrastructure only, NO gates,
#### no backtest claims yet).
####
#### API FACTS (hard-won, keep):
#### - history.deribit.com WITHOUT auth serves expired
####   instruments AND per-instrument trades (get_last_trades_
####   by_instrument works for 2016+ instruments); DVOL lives on
####   www.deribit.com ONLY (get_volatility_index_data, 1D from
####   2021-03-24).  urllib (python) is blocked at the edge on
####   both hosts; subprocess curl works.
#### - get_instruments?expired=true ignores `count` and `offset`
####   -> one ~77MB response per currency (BTC 122,488 insts
####   from 2016-07; ETH 124,373 from 2019-03; puts ~61k each).
####   Response format on history: {"usOut":...,"result":[...]}
####   -- NO jsonrpc key; on www: {"jsonrpc":"2.0","result":...}
####   and www truncates to ~82 recent instruments (useless for
####   history).
#### - www RESPECTS count but NOT offset on get_instruments.
#### - THE 400 "Bad request" MYSTERY RESOLVED: it is a
####   per-URL/IP throttle with a multi-minute cooldown, and it
####   is RE-TRIGGERED by each retry (my 3-24s retry backoff
####   kept it alive forever).  Single spaced attempts succeed;
####   also ~14 zombie retry-loop processes from earlier
####   run_commands chains were hammering concurrently (killed).
####   Rule: heavy calls strictly sequential, >=60s quiet before
####   first attempt, on 400 back off minutes not seconds.
####
#### DATA IN CACHE (data/deribit/):
#### - instruments_BTC.json / instruments_ETH.json: slim lists
####   (name, expiry, strike, type, settlement, creation);
####   BTC 122,488 (first expiry 2016-07-15, 61,242 puts),
####   ETH 124,373 (first 2019-03-29, 62,190 puts).
#### - dvol_BTC_1D.json / dvol_ETH_1D.json: 2011 daily points
####   each, 2021-03-24 .. 2026-09-24 (BTC last 36.12, ETH
####   50.94).  Assembled from per-year www calls
####   (experiments/options/dvol_merge.py).
#### Fetcher: experiments/options/deribit_fetch.py (stages
#### instruments / dvol / trades, checkpoint via cache files).
####
#### FEASIBILITY SIZING for the protective-puts overlay
#### (experiments/options/puts_feasibility.py; rule declared in
#### the file header: put expiry = first expiry >= entry+27d,
#### strike band 0.70-0.92 x spot at 4H entry, BTC only,
#### 2021-04+): 131 AVSL 4H long entries (4 pre-DVOL skipped),
#### ~764 unique put instruments in the band -> ~1.5k requests
#### ~10-20 min sequential fetch for the trades stage.
####
#### NEXT: (a) trades fetch for the sized subset; (b) decide
#### fill model: actual trade prints at entry timestamp are
#### SPARSE for OTM puts -- will measure nearest-print lag and
#### whether mid-proxy from DVOL+settlements is needed; (c) only
#### then pre-reg the overlay on frozen AVSL 4H BTC longs (gate:
#### DD <= 20%, EV >= 80% baseline).
####
#### OPT-DATA-DEPTH (2026-09-25, step 2: trades fetched, fill
#### model measured; diagnostics only, no backtest claims).
####
#### FETCHED: 693/693 puts (band 0.70-0.92 x spot, matched
#### expiries >= entry+27d) in data/deribit/puts_trades/;
#### 417/418 puts (band 0.90-0.98) in puts_trades2/.
#### 9+0 corrupt files (double-write by overlapping retry
#### loops) re-fetched clean; lesson: never let two retry loops
#### run on the same file set.
####
#### PRINT-LAG VERDICT (experiments/options/puts_depth.py):
#### **print-based fills are INFEASIBLE for both bands.**
####   - before-entry print exists: 31/131 entries (deep band);
####   - next print AT/AFTER entry: 119/131 (deep) and 104/131
####     (near band), BUT next-print lag median 644-664 HOURS
####     (~27 days!), p90 2-8 thousand hours.  Median trades per
####     instrument ~86-101, 57-68 of 693/417 instruments have
####     ZERO trades ever.  OTM BTC puts trade far too sparsely
####     for event-driven fills even at 0.90-0.98 moneyness.
####
#### SKEW MAP (experiments/options/skew_probe.py, 353,796
#### prints with iv field; units: BOTH print iv and DVOL are in
#### percent points; skew := print_iv - DVOL_same_day):
####   moneyness 0.60-0.65: +10.6 vol pts; 0.80-0.85: +5.6;
####   0.90-0.95: +2.1; 0.95-1.00: -0.8 (monotone put skew).
####   MODE DEPENDENCE (the prereg trap): 2021 and 2024-2026
####   agree within ~2 pts, but 2022 (bear) runs +10-25 pts
####   higher and stress episodes of 2023 even more (deep OTM
####   2023 median +133 on thin prints).  A flat-average skew
####   proxy UNDERSTATES hedge cost exactly in drawdown epochs.
####
#### CONSEQUENCE FOR THE OVERLAY PRE-REG (options, any of them):
#### fills must be mark-proxy: premium = BS(spot, K, DVOL(t) +
#### skew(m)), with skew frozen per moneyness bucket.  To be
#### decided at prereg time: (i) skew calibration = per-year or
#### conservative-high (use the bear-regime quantile, i.e. pay
#### the stress price always), or (ii) exclude 2022-2023 from
#### the test window (unacceptable: kills the bear evidence).
#### RECOMMENDATION: conservative-high skew + explicit
#### sensitivity read-out at skew-0 (ATM).  No overlay run until
#### this fill model is frozen in the prereg text.
####
#### ============================================================
#### PUTS-OVERLAY PRE-REG (2026-09-25, FROZEN BEFORE THE RUN;
#### runner: experiments/options/puts_overlay.py, one pass, log
#### runs/puts_overlay.log; decision on PRIMARY gates below).
####
#### QUESTION: does a protective-put overlay on the BTC leg of
#### the FROZEN AVSL 4H S1 portfolio cut portfolio DD below the
#### 20% gate while keeping >= 80% of baseline EV?
####
#### HEDGE SCOPE: BTC longs only (the only leg with an options
#### market deep enough); every AVSL 4H BTC long entry with
#### entry_ts >= 2021-04-01 (DVOL inception + margin).  Short
#### entries and all other assets: un-hedged (no instrument).
####
#### CONTRACT SELECTION (frozen): per entry, expiry = first
#### Deribit BTC put expiry >= entry + 27d; strike = grid strike
#### nearest 0.90 x S0 (S0 = Binance 1H close at entry_ts);
#### T = (expiry - entry)/365d.
####
#### FILL MODEL (frozen; the measured print sparsity rules out
#### print fills): premium AND exit marks are Black-Scholes puts
#### (r = 0), sigma_entry = DVOL_day(entry) + skew(K/S0),
#### sigma_exit = DVOL_day(exit) + skew(K/S_exit); DVOL_day =
#### last DVOL print <= ts.  SKEW TABLE (PRIMARY,
#### conservative-high, frozen from the p75 of the measured
#### per-bucket print skew): piecewise-linear nodes
####   m:    0.60   0.675  0.725  0.775  0.825  0.875  0.925  0.975
####   sk:  12.74  19.38  20.64  18.86  14.09  13.23  13.75  7.00
#### clamped to [0.60, 1.00] moneyness (outside: flat).
####
#### SIZING/NOTIONAL (frozen): put notional covers put_frac=1.0
#### of the entry spot exposure implied by the frozen account
#### convention: N/equity = 1% x size / (risk_frac), risk_frac =
#### 2 x 10bp x S0 / fee_r (fee_r from the frozen trade table).
#### Hedge PnL in equity % = (P_exit - P_entry)/S0 x N/equity,
#### accrued EVENLY over [entry..exit] bars, added to the frozen
#### 1%-unit bar stream.  Hedge exit ts = min(AVSL exit, expiry);
#### at expiry: intrinsic with S_exp = Binance 1H close of the
#### 08:00 UTC bar (Deribit settlement).
####
#### GATES (evaluated ONCE on the overlay portfolio stream,
#### 2021-04-01 .. data end, BTC+9 assets, S1 sizing, fees as
#### frozen):
####   G-P1: portfolio max DD <= 20%
####   G-P2: portfolio net EV >= 0.80 x baseline EV (baseline =
####         frozen stream, no hedge)
####   G-P3: portfolio Sharpe_NW >= baseline Sharpe_NW - 0.10
#### PASS iff all three.  FAIL -> options overlay CLOSED (one
#### shot; no re-runs, no skew/strike/frac edits afterwards).
####
#### READ-OUTS (non-gating): total premium paid (% equity);
#### hedge PnL by calendar year; 2022-epoch DD overlay-vs-
#### baseline; sensitivity at put_frac 0.5, skew=median table,
#### skew=0; strikes actually selected; n hedged trades.
####
#### ============================================================
####
#### ============================================================
#### PUTS-OVERLAY RESULT (2026-09-25; prereg frozen above, one
#### pass; log runs/puts_overlay.log; runner
#### experiments/options/puts_overlay.py).
####
#### DISCLOSURE: three implementation bugs were fixed BEFORE the
#### first complete successful run (hedge-grid broadcast,
#### nw_sharpe double-centering returning ~0, risk_frac formula
#### carrying a stray S0 multiplier).  No model/rule/gate edits
#### after the freeze; gates evaluated on the first run that
#### executed end-to-end.
####
#### BASELINE (2021-04..2026-09 window, full 10-asset S1
#### portfolio): DD 21.5%, EV +0.0233 %/bar, Sharpe_NW 1.93.
####
#### OVERLAY (PRIMARY: put_frac 1.0, skew p75): DD 21.6%,
#### EV +0.0232, Sharpe_NW 1.93; n=131 hedged legs, mean
#### moneyness 0.935; total premium 141.0% of equity over 5.5y.
#### Hedge PnL by year (% equity): 2021 -5.8, 2022 -10.8,
#### 2023 -33.9, 2024 -18.6, 2025 -13.7, 2026 -2.3 -- ALL
#### negative; 2023 premium burn -34% on flat/sideways BTC with
#### DVOL high.
####
#### GATES:
####   G-P1 DD <= 20%:  FAIL (21.6%; DD unchanged vs baseline,
####       2022-epoch DD 14.8% in BOTH -- the AVSL stop exits the
####       spot leg within days while the put keeps bleeding time
####       value; the protection never overlaps the actual
####       drawdown epochs enough to matter)
####   G-P2 EV >= 0.8x baseline: PASS (marginal: 0.98x)
####   G-P3 Sharpe >= baseline-0.10: PASS (unchanged 1.93)
####
#### VERDICT: **FAIL -> PUTS-OVERLAY CLOSED** (one shot; no
#### re-runs, no skew/strike/frac/exit edits; the whole
#### protective-puts-on-AVSL family is closed, not just these
#### parameters).
####
#### POST-MORTEM (recorded, does not reopen anything):
#### 1. Structural: AVSL's stop truncates the spot exposure to
####    days; a 27-90d put held only that long pays almost never
####    (the crash must happen INSIDE the trade window) while the
####    premium bleed is continuous.  Portfolio insurance on a
####    stop-based strategy is paying twice for the same tail.
#### 2. Even at skew=0 the overlay does not reduce DD (read-out)
####    -- this is geometry, not pricing.
#### 3. The DD gate failure sits in non-BTC-hedgeable epochs
####    anyway (2022 epoch DD only 14.8%; max DD driven by the
####    rest of the book + BTC legs outside hedge windows).
#### Remaining standing options per the SVD-closure focus: vol
#### carry (short-vol on the option market itself -- requires a
#### NEW prereg and a maker-fill model) / market switch (FX).
####
#### ============================================================
#### VOL-CARRY SHORT-STRANGLE PRE-REG (2026-09-25, FROZEN
#### BEFORE THE RUN; runner experiments/options/strangle_carry.py,
#### one pass, log runs/strangle_carry.log).
####
#### STRATEGY: monthly short strangle on BTC (standalone vol
#### carry, NOT an AVSL overlay).  At every Deribit BTC monthly
#### expiry timestamp (08:00 UTC, settlement_period=month,
#### 2021-04..2026-08, n=65 rolls): sell 1 put + 1 call of the
#### NEXT monthly expiry.  WING STRIKES (frozen): grid strike
#### nearest 0.90x (put) and 1.10x (call) S at roll ts.
#### CONFLICT RESOLUTION: the sketch's "3% OTM" and "delta
#### 0.10-0.20" are incompatible on 30d BTC (3% OTM ~ delta
#### 0.35+); frozen choice = the delta band, i.e. ~10% OTM wings
#### (the SSRN 3%-OTM variant is recorded as un-run).
####
#### SIZING (fixed fraction, frozen): each wing sold on 0.10x
#### equity of BTC notional (0.20x total strangle notional).
#### Scaling read-out 0.05x/0.20x.  Deribit inverse conventions:
#### premiums in BTC, payoff max(K-S_T,0)/S_T.
####
#### FILL MODEL (frozen; the only new component, as flagged):
#### no orderbook history exists on the API, so maker fills are
#### proxied on the same mark model as the puts prereg:
#### mid = BS(r=0, DVOL_day(ts) + skew(m)); entry credit =
#### 0.75 x mid  (25% maker haircut), exit buyback = 1.25 x mid;
#### maker fees = 0 (Deribit rebates; haircut covers).  Skew
#### tables: put side = frozen p75 table from the puts prereg;
#### CALL side = calibrated from the fetched call prints the
#### same way (table printed by the runner and frozen by this
#### prereg text reference).  SENSITIVITIES (non-gating):
#### haircut 0 / 15%.
#### MANAGEMENT: none -- hold to settlement (print-sparsity
#### evidence makes reconstruction of any active management
#### untestable; declared up front).
####
#### GATES (evaluated once, daily stream in % equity,
#### 2021-04..2026-08):
####   G-V1: Sharpe_NW >= 1.0 (annualized sqrt(365))
####   G-V2: max DD <= 20%
####   G-V3: IV premium exists: median(IV30 - RV30) over rolls
####       > +2 vol pts AND positive in >= 60% of rolls (RV30 =
####       30d realized vol of Binance daily closes at roll ts;
####       IV30 = DVOL at roll ts)
####   G-V4 (ADDED by the repo, disclosed: the sketch had no
####       tail control; short-vol without it is unfalsifiable
####       in this book): worst single strangle loss <= 15%
####       equity AND 2022 calendar-year PnL >= -20% equity.
#### PASS iff all four.  FAIL -> short-strangle vol carry
#### CLOSED (one shot).
####
#### KNOWN LIMITATIONS (declared, not gating): mark-proxy fills
#### (no book); settlement uses Binance close of the 08:00 UTC
#### bar; no margin/liquidation model (G-V4 is the substitute
#### control); call-skew table thinner than put-side (fewer
#### prints on the call wing).
#### ============================================================
####
#### ============================================================
#### AVSL TREND-FILTER PROGRAM PRE-REG (2026-09-25, FROZEN
#### BEFORE ANY FILTER RUN).  Ablation, one pass per filter,
#### NO tuning after each freeze.
####
#### BASELINE: engine/passed/avsl_cross_s1 (frozen verdict:
#### PRIMARY Sharpe 1.50 DD 22% EV +0.17R; F3 Sharpe 2.84
#### DD 12% EV +0.33R).  Baseline is recomputed in-process in
#### every runner and MUST match the frozen numbers (sanity
#### gate); any deviation aborts before filter evaluation.
####
#### FAMILY BUDGET: this is the filter-family, max 10 pre-regs
#### (P-2).  Sequential, order frozen below by prior.  A FAIL
#### closes that filter only; the passed AVSL module is
#### untouched (adoption of any PASS requires a new dated
#### prereg per the module docstring).
####
#### PROTOCOL (frozen, common to all): each runner imports the
#### passed engine, rebuilds the identical portfolio stream
#### (same 1%-unit accrual construction), applies the filter
#### (direction filters drop trades; sizing filters multiply
#### the S1 size), recomputes PRIMARY/F3 metrics.  Filter info
#### may use only data available at the entry bar close.
####
#### INDIVIDUAL GATE (frozen, both segments independently):
####   DD(filter) <= 0.8 x DD(baseline)   [>=20% rel. reduction]
####   EV(filter) >= 0.9 x EV(baseline)   [<=10% EV give-up]
####   G4 pos_assets >= 7 in both segments (no asset starvation)
#### READ-OUTS (non-gating): Sharpe_NW, n trades, trailing 12m
#### negative-window count (PF-G4 style), per-year EV.
#### KILL: gate FAIL -> filter closed, next in order.
#### PHASE 2: combinations only of passed filters (AND logic,
#### pre-registered then; Bonferroni x k for k candidates).
#### PROGRAM KILL: 0 individual passes -> program closed,
#### remaining focus vol-carry / FX.
####
#### ORDER + SPECS (frozen now, details per filter):
####   F1 HTF trend (1D SMA50)      prior 35-45%  <- RUNS FIRST
####   F3 Multi-TF (4H SMA200 + F1) prior 30-40%
####   F6 Supertrend direction      prior 25-35%
####   F2 ADX x sizing              prior 25-35%
####   F7 Market structure HH/HL    prior 25-35%
####   F5 Realized-vol regime       prior 20-30%
####   F4 confidence x strength     DEFERRED (see below)
####
#### F1 SPEC (frozen): keep long trade iff close of the last
#### COMPLETED UTC day (d_c = floor((bar_close_time)/day) - 1,
#### bar_close_time = 4H bar open + 4h) > SMA50 of the 50 daily
#### closes ending at d_c; keep short iff <.  Equal -> drop.
#### Daily closes built from the same 1H source (last 1H close
#### per UTC day).  No other parameter exists.
####
#### F3 SPEC: F1 condition AND 4H close(bar) > SMA200(4H closes
#### up to and incl. entry bar) for longs (mirrored shorts).
####
#### F6 SPEC: standard Supertrend(10, 3.0) on 4H H/L/C (ATR via
#### the engine's atr_ind; Wilder smoothing; first non-NaN bar
#### seeds direction long); long kept iff final direction up.
####
#### F2 SPEC: size_mult = clip(ADX14(4H)/25, 0.5, 1.5), ADX
#### Wilder on the entry bar (uses history only).  Distinct
#### from the failed ADX>25 SKIP gate: sizing, not skipping.
####
#### F7 SPEC: 5-bar fractal swings (k=2 neighbors each side)
#### on 4H; structure up iff last two swing highs HH AND last
#### two swing lows HL (mirror down); keep aligned trades.
####
#### F5 SPEC: vol_d = std(last 90 daily log rets); mult 1.2 if
#### vol_d < median(vol_d over prior 365d window), else 0.8.
#### Distinct measurement from S2 (ATR-percentile, FAILED
#### recorded).  History is a prior-failure warning, not a ban.
####
#### F4 DEFERRED: 'stop-head confidence' is an E8b OB-entry
#### quantity with no frozen AVSL-entry mapping; inventing one
#### now would be post-hoc.  F4 needs its own confidence
#### calibration prereg before it can run (parked).
#### ============================================================
####
#### F1 VERDICT (2026-09-25, one pass, runs/filter_f1.log):
#### BASELINE SANITY OK (PRIMARY 1.49/22%/+0.17R, F3 2.82/12%/
#### +0.35R -- reproduces frozen within data-drift tolerance).
#### Trades 2941 -> 1317 (45% kept).  GATE FAIL BOTH SEGMENTS:
####   PRIMARY: DD 22->21% (gate <=17.6% FAIL), EV +0.17->+0.31R
####            (PASS), pos 9/10 PASS; Sharpe 1.37.
####   F3:      DD 12->20% (FAIL), EV +0.35->+0.09R (FAIL),
####            pos 6/10 (FAIL); Sharpe 2.82->0.59.
#### READ-OUT: trailing 12m neg windows 0 -> 3127 (filtered
#### stream is concentrated + flat stretches).
#### INTERPRETATION: daily-trend alignment keeps the trend-side
#### trades but THROWS AWAY the F3 (holdout) edge -- consistent
#### with the E1-E5 map (edge = low-vol 2025+, not trend
#### direction); the kept cluster is more concentrated, DD does
#### not improve.  F1 CLOSED (FAIL).  Next: F3 Multi-TF (its F1
#### component is now measured-dead on F3; expectation lowered,
#### gate unchanged).
#### ============================================================
####
#### F3-FILTER VERDICT (2026-09-25, one pass, runs/filter_f3.log):
#### Trades 2941 -> 1120 (38%).  PRIMARY GATE PASS (DD 22->17%,
#### EV +0.17->+0.48R, Sharpe 1.60, pos 10/10) BUT HOLDOUT F3
#### SEGMENT FAILS ALL THREE (DD 12->19%, EV +0.35->+0.08R,
#### pos 6/10; Sharpe 0.60).  Same failure mode as F1: the 4H
#### SMA200 + daily-trend confirmation removes exactly the
#### trades that carry the F3 holdout edge.  F3-FILTER CLOSED
#### (FAIL).  Direction-alignment family now 0/2; running per
#### frozen order: F6 Supertrend next.
#### ============================================================
####
#### F6 VERDICT (2026-09-25, one pass, runs/filter_f6.log):
#### Trades 2941 -> 1664 (57%).  PRIMARY PASS STRONGLY: DD
#### 22->12%, EV +0.17->+0.31R, Sharpe 1.66, pos 10/10, neg
#### 12m windows 0->0.  F3 SEGMENT FAILS ALL THREE: DD 12->15%,
#### EV +0.35->+0.30R (retention 86% < 90%), pos 6/10; Sharpe
#### 1.52.  BY FROZEN GATE: FAIL -> F6 CLOSED.
#### READ-OUT (non-gating, recorded for honesty): the PRIMARY
#### profile of F6 is the best seen in the filter family and
#### PF-G4-clean.  Any 'PRIMARY-only deployment' branch does
#### NOT exist in the frozen program; opening it after seeing
#### these numbers would be post-hoc.  It can only enter as a
#### NEW dated prereg with its own holdout story -- parked,
#### not decided here.  Direction filters now 0/3; the F3
#### holdout edge concentrates in trades all three remove.
#### Next per frozen order: F2 ADX x sizing.
#### ============================================================
####
#### F2 VERDICT (2026-09-25, one pass, runs/filter_f2.log):
#### ADX14 mult p10 0.61 / med 0.99 / p90 1.50.  ALL TRADES
#### KEPT, size-scaled.  DD unchanged (PRIMARY 22->22%, F3
#### 12->11%) -- nowhere near the -20% gate; EV retention ~100%.
#### ADX strength carries no sizing information for this signal.
#### Consistent with the E-history ADX>25 skip-gate failure:
#### ADX is dead for AVSL-cross in both gate and sizing forms.
#### F2 CLOSED (FAIL).  Next per frozen order: F7 structure.
#### ============================================================
####
#### F7 VERDICT (2026-09-25, one pass, runs/filter_f7.log):
#### Trades 2941 -> 852 (29%).  DD gate PASSES both segments
#### (PRIMARY 22->12%, F3 12->8%) BUT the F3 EV-retention gate
#### FAILS: +0.35R -> +0.15R (43% << 90%); Sharpe F3 0.73; neg
#### 12m windows 0 -> 397.  F7 CLOSED (FAIL).  Direction /
#### structure filters 0/4.  Next per frozen order: F5
#### realized-vol regime (sizing), then F4 is DEFERRED -> if F5
#### fails the program kill rule applies (0 individual passes).
#### ============================================================
####
#### F5 VERDICT (2026-09-25, one pass, runs/filter_f5.log):
#### mult share hi 59% / lo 27% / neutral 14%.  DD WORSENS on
#### PRIMARY (22->25%); F3 12->10%.  EV retention ~100%.
#### Realized-vol regime sizing carries no DD relief -- second
#### vol-scaling failure (with S2 ATR-percentile).  F5 CLOSED
#### (FAIL).
####
#### PROGRAM KILL RULE APPLIED (2026-09-25): individual record
#### F1 FAIL / F3 FAIL / F6 FAIL / F2 FAIL / F7 FAIL / F5 FAIL
#### (F4 deferred -- no frozen confidence mapping).  0/6 PASS
#### -> AVSL TREND-FILTER PROGRAM CLOSED.  Combinations phase
#### not run (no passes to combine).  The passed AVSL-cross S1
#### module is UNCHANGED.  Direction/structure filters
#### consistently remove the F3 holdout edge; sizing filters do
#### not move DD.  Next focus per the book: vol carry (in
#### flight) / FX market switch.
#### ============================================================
####
#### VOL-CARRY SHORT-STRANGLE VERDICT (2026-09-25, one pass,
#### runs/strangle_carry.log): VERDICT FAIL -> SHORT-STRANGLE
#### VOL CARRY CLOSED.
#### CALL SKEW TABLE (measured, frozen read-out): calls trade
#### BELOW DVOL near the money: 0.95-1.05 median -2.9 vol pts,
#### 1.10-1.15 -1.9, 1.20-1.30 ~+0.25, >1.35 +3..+4 (n=828k
#### prints).  The call wing is sold CHEAP vs DVOL; the put wing
#### rich (+13.8 at 0.90).  Net credit exists, tails eat it.
#### PRIMARY RUN (scale 1.0, haircut 25%): Sharpe -0.19, DD
#### 77.8%, total -71.2% equity over 2021-04..2026-08; NEGATIVE
#### EVERY YEAR: 2021 -2.8 / 2022 -10.8 / 2023 -16.7 / 2024
#### -6.2 / 2025 -2.5 / 2026 -12.9.  Worst single leg -8.3%.
#### GATES: G-V1 FAIL, G-V2 FAIL, G-V3 PASS (IV30-RV30 median
#### +8.6 vol pts, positive in 82% of rolls -- the variance
#### risk premium EXISTS and is still not enough), G-V4 PASS
#### (sizing cap did its job; the loss is a slow bleed, not a
#### single blowup).
#### SENSITIVITIES: haircut 15% -> -66.4%; haircut 0% -> -58.5%
#### (fills are NOT the problem); scale 0.5x -> -35.6%; 2.0x ->
#### -98.2%.  No sizing knob rescues a negative-expectancy
#### stream.  2023 is the worst year (grind-up + vol spikes:
#### call wing pays, put wing decays uncollected).
#### CONCLUSION: BTC 30d variance risk premium (+8.6 pts) is
#### real but structurally smaller than the wing payoff drain
#### at any frozen fixed-fraction short-strangle shape.
#### Consistent with the puts-overlay closure: the tails are
#### not payable from premium.  SHORT-STRANGLE VOL CARRY CLOSED
#### (family; not just these parameters -- any fixed monthly
#### short-wings shape shares this arithmetic).
#### Next branch per the book: FX market switch (new pre-reg
#### required before any run).
#### ============================================================
####
#### ============================================================
#### AVSL TP-ABLATION PROGRAM PRE-REG (2026-09-25, FROZEN BEFORE
#### ANY RUN).  Exit-side ablation of the passed module; the
#### module stays PASSED and untouched (adoption of a PASS
#### requires a new dated prereg per its docstring).
####
#### EVIDENCE BASE (honest summary, deviations from the
#### proposal noted): E3 arm D (pre-registered amendment,
#### runs/ablation_rr_d.log) reverse-cross exit EV +0.447/
#### +0.422 vs frozen +0.172/+0.335 -- BUT D's random-geometry
#### null is +0.415+-0.124 PRIMARY: the PRIMARY lift is ~all
#### null (drift capture); the real entry-information lift is
#### F3-side (+0.277).  E3 measured PER-TRADE EV ONLY -- no
#### portfolio Sharpe/DD exists for any exit arm.  Trailing on
#### other TFs failed twice (avsl_trailing.py stop-flip 15m
#### OKX 0/10; avsl_trail_* logs evN<0, fees) -- 4H Binance
#### universe was never trailed under portfolio gates.
#### PRIOR ADJUSTED: 35-45% (proposal said 40-50% before the
#### null decomposition was priced in).
####
#### F-TP1 SPEC (frozen, RUNS FIRST): entry/stop/sizing frozen
#### (identical to the passed module); exit = first OPPOSITE
#### cross bar after entry, taken at that bar's close, capped
#### at HORIZON=500 (semantics identical to E3 arm D,
#### ablation_rr._trade with revcross=True; stop checked
#### intrabar and wins).  Trades chain (reverse cross is the
#### next entry); no same-asset overlap.
#### F-TP1 GATES (frozen): the passed module's full battery on
#### BOTH segments (Sharpe_NW >= 1.0, DD <= 25%, net EV >=
#### +0.10R, pos_assets >= 7, block-bootstrap CI > 0) AND
#### PRIMARY portfolio DD strictly below the baseline's 22%
#### (program purpose is DD relief; a PASS with worse PRIMARY
#### DD is recorded as PASS-no-adopt).  READ-OUTS: vs-baseline
#### table, neg 12m windows, per-year EV, hold distribution.
####
#### F-TP2 (adaptive MFE TP, parked until F-TP1 verdict):
#### TP = clip(0.8 x MFE_pred, 1.5R, 6R), MFE_pred = LGBM on
#### entry-time features (D.5 transfer).  Needs its own
#### calibration pre-reg (features + train/test split) BEFORE
#### any run.
#### F-TP3 hybrid 2R-50% + trailing remainder: parked, spec at
#### freeze time.  F-TP4 structural TP: parked.  F-TP5 no-TP
#### hold-only: parked (differs from F-TP1 only by horizon;
#### note E3 D already caps at 500).
#### PROGRAM: max 3 pre-regs in the family (P-2); F-TP1 FAIL ->
#### F-TP2 decision; both FAIL -> exit-axis closed, FX next.
#### ============================================================
####
#### F-TP1 VERDICT (2026-09-25, one pass, runs/tp1_revcross.log):
#### **PASS -- FIRST NEW PASS SINCE THE ORIGINAL MODULE.**
#### n=2941 (same entries as frozen; only exits differ); hold
#### med 4 bars / p90 128.
####   PRIMARY: Sharpe 1.17, DD 15% (baseline 22%), EV +0.44R,
####            pos 9/10 -- battery 4/4 + DD-relief 5/5.
####   F3:      Sharpe 3.03, DD 5% (baseline 12%), EV +0.45R,
####            pos 10/10 -- 4/4.
####   neg 12m windows 0; per-year net EV positive EVERY year
####   (2020 +1.11, 2021 +0.08, 2022 +0.44, 2023 +0.45, 2024
####   +0.15, 2025 +0.40, 2026 +1.57).
#### INTERPRETATION: confirms the TP-geometry hypothesis at the
#### portfolio level.  2023-24 was not a dead regime -- the 5R
#### TP was unreachable there and hold-exits accumulated the
#### bleed; reverse-cross exit captures the move without the
#### 5R wait.  EV matches E3-D's descriptive numbers (+0.447/
#### +0.422) within tolerance; the null caveat stands (PRIMARY
#### lift over matched null is small) -- the ENTRY information
#### remains a holdout-side effect, now harvested by an exit
#### that does not abandon trades before the drift pays.
#### PER FROZEN PROGRAM: F-TP2 (adaptive MFE TP) is no longer
#### needed as a rescue; it stays available as an independent
#### pre-reg if pursued.  NEXT: promotion decision for an
#### AVSL-cross S1 reverse-exit module (new dated prereg +
#### engine/passed promotion + live-scale consideration), per
#### the module docstring's adoption rule.  The passed frozen
#### module remains untouched until that promotion prereg.
#### ============================================================
####
#### ============================================================
#### F-TP1 PROMOTION DUE-DILIGENCE CHECKS (2026-09-25, declared
#### before any run; descriptive read-outs, NOT gates -- the
#### gates belong to the promotion prereg that follows).
####
#### CHK-1 TRUE-GRID ALIGNMENT: recompute BOTH the baseline
#### (TP=5R) and F-TP1 streams on the TRUE global grid
#### (absolute 4H bucket minus earliest asset bucket, the
#### R-OB-1 lesson convention).  Legacy-index numbers (22%/15%)
#### are expected to move; the relative comparison must survive.
####
#### CHK-2 PORTFOLIO NULL FOR TRAILING: E3-D measured the
#### trailing null on per-trade EV only (+0.415+-0.124 / +0.145
#### +-0.069).  Here: the SAME E1/E3 random-draw procedure
#### (seeds 0..99, per-asset entry counts and long/short ratios
#### matched to the actual trades) with the trailing exit,
#### S1 sizing, TRUE grid -> portfolio Sharpe/DD/EV null
#### distribution per segment.  Answers: is the F-TP1 portfolio
#### profile (Sharpe 1.17 / DD 15%) exit-geometry-universal or
#### AVSL-specific?  Read-out: F-TP1's percentile within the
#### null per metric per segment.
####
#### CHK-3 DISTRIBUTION DECOMPOSITION: net-R distribution of
#### F-TP1 vs baseline trades (percentiles, win%, avg win/loss,
#### hold stats, top-5%-trades PnL share) -- locates the EV gain
#### and the Sharpe give-up (variance) mechanically.
#### ============================================================
####
#### ----------------------------------------------------------
#### READ-OUT (single run, runs/tp1_checks.log, 2026-09-25):
####
#### CHK-1 TRUE GRID: baseline 26% PRIMARY / 29% F3 DD, Sharpe
#### +1.22 / (NW artifact, see below), EV +0.16/+0.31; F-TP1
#### 22% / 20% DD, Sharpe +1.22 / +1.35, EV +0.49 / +0.38,
#### pos 9 / 10.  Legacy 15% DD -> true 22%: still < cap 25%
#### but margin 3pp, not 10pp.  Baseline true 26% reproduces
#### the known true-grid number.  All promotion gates pass on
#### the true grid.
####
#### FINDING 1 (metric artifact, frozen-module known rule):
#### baseline F3 nw_sharpe exploded to +9123 -- its NW lag-sum
#### hit the -0.5 floor (factor ~0.0004), the documented floor
#### behavior of the frozen metric.  Plain annualized Sharpe
#### for reference: baseline +1.99/+3.72, F-TP1 +8.34/+6.76.
#### Caveat recorded: F-TP1's daily stream is MORE persistent
#### (rho2 0.927 vs 0.886) and lower-variance than baseline,
#### so the NW correction penalizes F-TP1 harder; the NW
#### comparison (1.22 vs 1.22) is the conservative one, plain
#### comparison (8.34 vs 1.99) the liberal one.  DD/EV/pos
#### gaps are metric-independent and all favour F-TP1.
####
#### CHK-2 PORTFOLIO TRAILING NULL (100 draws, E1/E3 matched
#### counts/sides, true grid): PRIMARY null Sharpe +0.93+-0.14
#### [+0.56,+1.45], DD 19%+-7% [8%,38%], EV +0.44+-0.13;
#### F-TP1 percentile: Sharpe 96th, DD(favourable) 35th, EV
#### 67th.  F3 null Sharpe +0.79+-0.31, DD 18%+-6%, EV
#### +0.16+-0.08; F-TP1 percentile: Sharpe 94th, DD 29th, EV
#### 100th.
####
#### FINDING 2 (edge vs drift, portfolio level): PRIMARY EV is
#### DRIFT -- random trailing entries average the same +0.44R
#### (F-TP1 67th pct), replicating E3-D at portfolio level.
#### The AVSL entry edge shows up as VARIANCE REDUCTION, not
#### EV: same EV as null but Sharpe 96th pct and DD below null
#### mean.  On F3 the EV is EDGE (100th pct, +0.38 vs
#### +0.16+-0.08) and Sharpe 94th pct.  NB: even RANDOM
#### trailing portfolios sit at 19% mean DD -- most of the DD
#### relief vs 26% baseline is exit geometry, not entry
#### selection.  Honest promotion claim: deployable candidate
#### rests on (a) true-grid gates all pass, (b) entry adds
#### portfolio quality (Sharpe 94-96th pct of null both
#### segments), (c) F3 EV is genuine edge, NOT on PRIMARY EV.
####
#### CHK-3 DISTRIBUTION: baseline win 21%, avg win +4.80R,
#### avg loss -1.02R, median -1.02; F-TP1 win 13%, avg win
#### +6.37R, avg loss -0.45R, median -0.32, max +200.9R (one
#### multi-month ride), top-5% of trades = 168% of total PnL.
#### F-TP1 is a right-tail ride: reverse-exit cuts average
#### loss by half (-1.02 -> -0.45) and lets winners run;
#### the Sharpe give-up under NW is the price of tail
#### persistence.  Per-year net EV (legacy grid): 2020 +1.53,
#### 2021 +0.33, 2022 +0.06, 2023 +0.67, 2024 +0.35, 2025
#### +0.16, 2026 +0.82 -- positive every year.
####
#### CONSEQUENCE FOR PROMOTION PREREG: gates must be declared
#### on the TRUE grid; PRIMARY EV claim must be phrased as
#### drift-captured (per CHK-2), portfolio-quality claim via
#### Sharpe/DD percentiles vs null; F3 EV edge is the
#### signal-specific claim.  F-TP1 stays the PASS candidate;
#### nothing invalidated, claims made more precise.
#### ----------------------------------------------------------
####
#### ----------------------------------------------------------
#### DIAGNOSTIC (descriptive post-mortem, declared 2026-09-25
#### before run; no gates): WHY DID SHARPE FALL under the
#### frozen NW metric (1.49 -> 1.17 legacy PRIMARY)?  Plan:
#### (a) NW factor decomposition (lag-sum, factor, effective
#### sample size) for baseline vs F-TP1 daily streams, true
#### grid; (b) per-trade Sharpe (mean/std of net R) -- the
#### entry economics without stream autocorrelation; (c) hold
#### duration and tail sensitivity (per-trade Sharpe with top
#### wins removed).  Question answered: metric artifact vs
#### economic deterioration.
#### ----------------------------------------------------------
####
#### ----------------------------------------------------------
#### READ-OUT (runs via experiments/avsl/sharpe_postmortem.py,
#### single descriptive run, true grid, 2026-09-25):
####
#### Q: WHY DID SHARPE FALL (1.49 -> 1.17 legacy PRIMARY)?
#### A: METRIC ARTIFACT -- the NW long-memory penalty, not the
#### economics.  Decomposition (PRIMARY): plain_ann Sharpe
#### ROSE 4.87 -> 20.44; the NW lag-sum grew +7.4 -> +139.2
#### (k<=500), factor 4.0 -> 16.7, effective sample size
#### 643 -> 36 of 10179 4H bars.  NW = plain/factor pins both
#### strategies at ~1.22: for this persistence class the
#### frozen metric has a resolution CEILING (~1.2); it cannot
#### express the improvement.  Same entries both sides; the
#### difference is exit-side hold structure (median hold 4 vs
#### 23 bars; winners ride to the 500-bar horizon).
####
#### FINDING 3 (material, changes the claim): EV CONCENTRATION.
#### F-TP1 top-20 trades (of 1847) = 99% of PRIMARY PnL (F3:
#### 117%); ex-top-20 mean EV +0.006R (PRIMARY) / -0.066R
#### (F3).  Baseline ex-top-20 stays +0.111R.  Per-year
#### (legacy grid, global top-20 removed): 2020 +0.42, 2021
#### -0.01, 2022 +0.06 (0 monsters), 2023 +0.04 (6), 2024
#### -0.05 (5), 2025 +0.10, 2026 +0.55.  So "2023-24 alive"
#### must be re-phrased: alive VIA 5-6 monster trends per
#### year; ex-monster EV ~0.  The per-trade t-stat (3.2 vs
#### 3.0 baseline) and avg-loss cut (-1.02 -> -0.45R) are
#### real, distributed, and are the robust part of the edge;
#### the EV level is tail-dependent.
####
#### PROMOTION PREREG CONSEQUENCES (updating the CHK-1/2/3
#### guidance): (i) headline NW Sharpe is unfit for this
#### class -- gate on it anyway (it passes, 1.22/1.36) but
#### read plain_ann and eff_n as declared sensitivities;
#### (ii) add concentration read-outs as REQUIRED disclosures,
#### not gates: EV ex-top-20 per segment, per-year ex-top-20
#### table, eff_n; (iii) DD 22% claim carries the fragility
#### caveat: live path depends on catching rare extreme
#### trends; expect long flat/negative stretches between
#### monsters; (iv) deployable thesis re-stated: "loss-cutting
#### exit (avg loss -0.45R, t~3) + occasional trend capture;
#### NOT a smooth-Sharpe product".
#### ----------------------------------------------------------
####
#### ============================================================
#### PROMOTION PREREG: AVSL-cross S1 + reverse-cross exit ->
#### engine/passed/avsl_trailing_s1.py  (frozen 2026-09-25,
#### BEFORE any module run; parent avsl_cross_s1 stays FROZEN).
####
#### CONFIG (frozen, identical evidence chain as F-TP1): entry
#### close crosses AVSL(70,345) stand_div 2.0, normal arm,
#### WARMUP 400; stop max(|close-line|, 2xATR14) at entry bar;
#### exit FIRST OPPOSITE-cross bar close, stop intrabar wins,
#### MTM at HORIZON 500; TP NONE; taker 10bp RT; sizing S1
#### clip(0.20/rv100, 0.25, 2.0); universe BTC AVAX BNB DOGE
#### ETH LINK LTC NEAR SOL XRP (Binance 1H -> 4H); segments
#### PRIMARY 2/3, F3 1/3; grid = TRUE global grid (declared
#### convention, R-OB-1 lesson).
####
#### PROVENANCE: F-TP1 prereg 032726e, verdict 902400d;
#### due-diligence 8e2654b (CHK-1/2/3); post-mortem 1285c56.
####
#### FROZEN RESULT (runs/tp1_checks.log -- the numbers the
#### module must reproduce): n=2941; PRIMARY Sharpe_NW +1.22,
#### DD 22%, EV +0.49R, pos 9/10; F3 Sharpe_NW +1.35, DD 20%,
#### EV +0.38R, pos 10/10.
####
#### PROMOTION GATES (all must PASS):
#### P1 --verify: reproduce frozen numbers at printed
####     precision (Sharpe +-0.005, DD +-0.005, EV +-0.005,
####     pos exact, n exact).
#### P2 self-contained: no imports from experiments/ (test).
#### P3 exit-rule regression tests pass (stop intrabar wins,
####     reverse-cross at close, horizon clamp, fee, both
####     sides) -- synthetic arrays, no data dependency.
#### P4 battery re-assert on true grid: Sharpe_NW >= 1.0,
####     DD <= 25%, EV >= 0.10R, pos >= 7, both segments.
####
#### REQUIRED DISCLOSURES (always printed, read-outs not
#### gates, per due-diligence FINDINGS 1-3): plain_ann Sharpe
#### and NW eff_n per segment; ex-top-20 EV per segment;
#### per-year EV and per-year ex-top-20 table.
####
#### DEPLOYABLE THESIS (frozen wording): "loss-cutting exit
#### (avg loss -0.45R vs -1.02R, per-trade t~3, distributed)
#### + episodic trend capture (top-20 trades ~99% of PnL,
#### ex-monster EV ~0).  NOT a smooth-Sharpe product: expect
#### long flat/negative stretches between monsters; NW
#### Sharpe is at its resolution ceiling for this class
#### (eff_n 36/34 of 10179/5090)."
#### ============================================================
####
#### ============================================================
#### PROMOTION VERDICT (single verify run, 2026-09-25, commit
#### db06485 frozen BEFORE the run):
####   P1 --verify: PASS (n=2941 exact; PRIMARY +1.22 / 22% /
####       +0.49R / pos 9; F3 +1.35 / 20% / +0.38R / pos 10 --
####       all within tol of the frozen result)
####   P2 self-contained: PASS (test_no_experiments_imports)
####   P3 exit-rule regressions: PASS 8/8 (stop intrabar wins,
####       reverse-cross at close both sides, horizon cap,
####       no-cross -> final-bar MTM, fee, hygiene, constants)
####   P4 battery re-assert true grid: PASS (both segments,
####       bootstrap CI excludes 0)
####   DISCLOSURES printed: plain_ann +20.4/+16.6, eff_n 36/33,
####       ex-top-20 EV +0.006R/-0.066R (top20 share 99%/117%),
####       per-year table with ex-top20 column.
####   VERDICT: engine/passed/avsl_trailing_s1.py DEPLOYABLE
####   (second passed strategy).  Parent avsl_cross_s1 stays
####   FROZEN/retired-exit.  Ledger: PASS->DEPLOYABLE: 2.
####   Post-verdict fix: _per_year year attribution moved to
####   true-grid absolute buckets (disclosure-only; gates and
####   P1-P4 unchanged and re-confirmed after the fix).
#### Live-scale considerations (carried from due-diligence):
####   expect long flat stretches between monster trades; NW
####   Sharpe at ceiling for this class -- monitor plain_ann,
####   eff_n, ex-top-20 EV, per-year ex-top20 as live read-outs.
#### ============================================================
