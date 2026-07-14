---
title: Minimum CDaR (Conditional Drawdown-at-Risk) Portfolio
source: Chekhlov, Uryasev & Zabarankin (2005), International Journal of Theoretical and Applied Finance 8(1)
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Conditional Drawdown-at-Risk is the average of the worst (1 - alpha) fraction of
drawdowns along a portfolio's cumulative return path. Unlike variance, CVaR or
semivariance — all point-in-time measures of a single period's loss — CDaR is
path-dependent and penalises sustained peak-to-trough declines directly, which
is closer to what a drawdown-averse investor actually experiences. Minimizing
CDaR should build a portfolio that avoids assets contributing to long, deep
drawdown episodes, producing a shallower and shorter max-drawdown profile than
the validated minimum-variance / minimum-CVaR / minimum-semivariance family.
Expected Sharpe comparable (~0.9–1.4 on the full universe) with the
distinguishing benefit in max-drawdown and drawdown duration rather than raw
Sharpe. This is a construction objective the repo lacks (it has full-variance,
tail-CVaR and downside-semivariance objectives, but none path-dependent).

## Rule sketch

- Monthly, over a lookback (param ~252 days) build the portfolio cumulative
  return path and minimize CDaR at confidence alpha (param default 0.95 = worst
  5% of drawdowns) over the long-only simplex (SLSQP), weights sum to 1.
- Parameters: lookback 126–504 days; alpha 0.90–0.99.

## Universe fit

Full universe (returns matrix only) — long-only, monthly, clean fit, same data
footprint as minimum-CVaR. Imperfect: CDaR is path-dependent, so a single
in-sample path can dominate the estimate and the objective is non-convex in the
weights (SLSQP may find a local optimum); as a risk-minimization objective it
should still diversify rather than concentrate, but the drawdown estimate from
~252 days sees only one or two real drawdown episodes, so validation
(DSR/PBO/SPA) is the real test.
