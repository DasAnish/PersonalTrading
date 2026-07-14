---
title: Maximum Omega-Ratio Portfolio
source: Keating & Shadwick (2002), Journal of Performance Measurement 6(3)
mechanism: diversification
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

The Omega ratio measures the ratio of probability-weighted gains above a
threshold to probability-weighted losses below it, capturing the entire return
distribution (all moments) rather than just mean and variance. Maximizing
portfolio Omega should allocate toward assets whose joint distribution offers a
favourable gain/loss asymmetry — rewarding positive skew and penalizing fat left
tails in a way variance ignores. On a heterogeneous multi-asset universe with
skewed assets (gold, commodities) this should yield a portfolio with a better
upside/downside profile than a variance- or tail-only objective. Expected Sharpe
comparable to the validated minimum-CVaR / minimum-semivariance family (~0.9–1.4
on the full universe), with the distinguishing benefit showing up in
gain-to-pain / Omega itself rather than raw Sharpe. Distinct construction
objective from everything in the repo (min-variance, min-CVaR, min-semivariance,
HRP, risk parity, network risk parity).

## Rule sketch

- Monthly, over a lookback (param, ~252 days) build the daily return scenario
  matrix and maximize portfolio Omega at threshold tau (param, default 0)
  over the long-only simplex (SLSQP), weights sum to 1.
- Parameters: lookback_days 126–504; threshold tau 0 to a small positive daily
  hurdle.

## Universe fit

Full universe (returns matrix only) — long-only, monthly, clean fit, same data
footprint as minimum-CVaR. Imperfect: Omega maximization is non-convex in
general, so SLSQP may find a local optimum and can be sensitive to the
threshold and lookback; the in-sample Omega can overstate out-of-sample
performance (validated by the DSR/PBO/SPA battery). With few assets the
optimizer may concentrate into whichever asset had the best in-sample asymmetry.
