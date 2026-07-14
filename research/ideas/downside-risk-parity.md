---
title: Downside Risk Parity (equal downside-risk contribution)
source: Roncalli (2013), "Introduction to Risk Parity and Budgeting", Chapman & Hall/CRC
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Standard risk parity equalizes each asset's contribution to total portfolio
*volatility* using the full covariance matrix. Risk budgeting generalizes to
alternative risk measures; using the semicovariance matrix (co-movements of
below-target returns) equalizes each asset's contribution to portfolio
*downside* risk. This should tilt the budget away from assets that co-move on
the downside and toward genuine diversifiers of loss, producing a shallower
left tail than full-covariance risk parity while remaining more diversified
(less concentrated) than minimizing downside variance. Expected Sharpe
comparable to the validated risk-parity / minimum-semivariance family
(~0.8–1.2 on the full universe), with the benefit concentrated in drawdown and
downside capture. Distinct from RiskParityStrategy (full-vol ERC) and
MinimumSemivarianceStrategy (minimize, not equalize, downside variance).

## Rule sketch

- Monthly, over a lookback (param ~252 days) compute the semicovariance matrix
  from below-target return deviations (target param, default 0), then solve for
  long-only weights that equalize downside-risk contributions
  (w_i * (S w)_i / w'Sw = 1/N) via SLSQP; weights sum to 1.
- Parameters: lookback 126–504 days; target_return 0 or trailing mean.

## Universe fit

Full universe (returns matrix only) — long-only, monthly, clean fit, same data
footprint as risk parity. Imperfect: the semicovariance matrix uses only the
below-target subset of observations (~half the data), so it is noisier than the
full covariance and the equal-downside-contribution solution can be unstable
month to month; on a small universe the downside co-movements are dominated by
the equity block, so the budget may load heavily on bonds/gold.
