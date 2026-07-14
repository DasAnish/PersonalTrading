---
title: Accelerating Dual Momentum
source: "https://engineeredportfolio.com/2018/05/02/accelerating-dual-momentum-investing/ — Ludlow & Hanly (2018), Engineered Portfolio"
mechanism: momentum-cs
status: rejected
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Accelerating Dual Momentum (ADM) modifies classic dual momentum by scoring
each asset on a *multi-lookback* momentum measure — the average of its 1-, 3-
and 6-month total returns — rather than a single 12-month lookback. Averaging
several short lookbacks makes the score "accelerate": it responds faster to
turning points than a 12-month signal, capturing regime shifts earlier while
the multi-window averaging damps the whipsaw a single 1-month signal would
suffer. Combined with an absolute-momentum overlay (rotate to bonds/defensive
when the selected asset's own momentum is negative), the practitioner
backtests report equity-beating returns with reduced drawdowns. The economic
rationale is the same underreaction/slow-diffusion edge as all momentum, but
the acceleration harvests it at a shorter effective horizon where autocorrelation
is strongest. This is distinct from the backlog's existing Dual Momentum idea
(Antonacci — single 12-month lookback, relative + absolute) in its *signal
construction*: multi-lookback averaged score with faster response. It remains a
momentum-cs idea and shares DNA with the built dual-momentum strategy, so it
should be evaluated specifically as a "does the shorter, multi-window,
accelerating signal beat the single 12-month lookback net of the extra
turnover it creates?" question rather than as an entirely new mechanism.
Expected standalone Sharpe: roughly 0.5–0.8 (in line with, and possibly modestly
above, classic dual momentum), with the caveat that shorter lookbacks raise
turnover and are more exposed to short-term reversal noise.

## Rule sketch

- **Signal**: for each asset compute the average of its trailing 1-, 3- and
  6-month total returns (the ADM "acceleration" score). Rank assets by this
  score for relative momentum; apply absolute momentum by requiring the
  selected asset(s) score (or their own excess-over-cash) to be positive,
  else rotate to the defensive asset.
- **Rebalance rule**: monthly, matching this repo's cadence.
- **Portfolio construction**: long-only — hold the top-scoring asset or
  top-N equal-weighted; when absolute momentum fails, allocate the freed
  weight to the defensive asset (VUTY here, in place of the original's bond
  fund) rather than cash.
- **Parameters** (plausible ranges, not fitted): lookback set {1,3,6} months
  (variants {1,3,6,12}); number of assets held N = 1–3; absolute-momentum
  threshold at zero excess return; defensive asset VUTY.

## Universe fit

Maps to the full 13-ETF universe as candidate risk assets (VUSA, EQQQ, IWRD,
IMEU, IIND, AIGC, SGLN, SSLN, BRNT, CRUD, COMM/WCOA) with VUTY as the
defensive/absolute-momentum fallback. Long-only and monthly-rebalance
compatible. Imperfections: (1) the original blog strategy is a concentrated
top-1 rotation between a few broad assets; with only 13 ETFs and a top-1 or
top-2 rule the portfolio is very concentrated and turnover-heavy, which the
repo's transaction-cost model must penalise; (2) it lacks a true cash
instrument, so the absolute-momentum "risk-off" leg must route to VUTY, whose
own drawdowns (e.g. 2022 rate shock) differ from cash and will change the
crash-protection profile the source relied on; (3) the source is a
practitioner blog backtest, not a peer-reviewed study, so the pre-registered
Sharpe range carries more uncertainty and the idea should be treated as a
signal-variant test of the already-built dual-momentum strategy rather than an
independently validated anomaly.
