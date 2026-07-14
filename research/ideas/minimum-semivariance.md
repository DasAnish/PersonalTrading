---
title: Minimum Semivariance Portfolio (downside-risk optimization)
source: Estrada (2008), Journal of Applied Finance 18(1)
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Standard minimum-variance optimization penalizes upside and downside deviation
equally, but investors only dislike the downside. Minimum-semivariance replaces
the covariance matrix with a semicovariance matrix computed only from returns
below a target (typically the mean or zero), so the optimizer minimizes downside
co-movement while leaving upside volatility unpenalized. The edge is a better
realized risk/return trade-off than min-variance when return distributions are
skewed or fat-tailed — the published finding is that the minimum-semivariance
portfolio matches or beats minimum-variance on most performance measures
(higher Sharpe/Sortino, similar or lower drawdown) at the cost of higher
turnover. Expected Sharpe broadly comparable to the repo's validated
minimum-variance / risk-parity family (~0.6–1.0 on this multi-asset universe),
with a shallower left tail. This is a distinct construction mechanism: the repo
has minimum_variance (full covariance), HRP, and risk_parity, but nothing that
optimizes a downside-only risk measure.

## Rule sketch

- Monthly, over a covariance lookback (param, ~252 days; range 126–500) compute
  the semicovariance matrix: for each pair, average the product of the two
  assets' below-target return deviations (target = 0 or trailing mean, param),
  setting above-target observations to zero.
- Solve for the long-only weights that minimize portfolio semivariance
  `w' S w` subject to `sum(w)=1`, `w>=0` (Estrada's heuristic / convex QP on the
  semicovariance matrix). Optional min/max weight caps (params).
- Rebalance monthly.

## Universe fit

Runs on the full 13-ETF universe (or any broad group — core_6/core_8) exactly
like minimum_variance: only a returns matrix is needed, so the fit is clean,
long-only, monthly. Imperfect: the semicovariance matrix is estimated from only
the below-target subset of observations, so it uses roughly half the data and is
noisier than the full covariance — estimation error (already a known weakness of
min-variance) is amplified, which is why turnover is higher. No instrument-level
issues; purely a construction change.
