---
title: CVaR Risk Parity (equal component-CVaR contribution)
source: Boudt, Peterson & Croux (2008), Journal of Risk 11(2)
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Boudt, Peterson & Croux decompose portfolio Conditional Value-at-Risk into
per-asset component contributions (component CVaR_i = -w_i times the expected
return of asset i conditional on the portfolio being in its worst-alpha tail).
Equalizing these component CVaRs — CVaR risk parity — budgets tail risk equally
across assets, tilting away from assets that drive the joint tail and toward
tail diversifiers. This should give a shallower, better-balanced tail than
full-volatility risk parity and a more diversified allocation than minimizing
total CVaR (which can concentrate in the single lowest-tail asset). Expected
Sharpe comparable to the validated risk-parity / min-CVaR / downside-risk-parity
family (~0.9–1.4 on the full universe), with the benefit in tail balance and
drawdown. Distinct from MinimumCVaRStrategy (minimizes total CVaR),
RiskParityStrategy (volatility contributions) and DownsideRiskParityStrategy
(semicovariance contributions): this equalizes historical component CVaR.

## Rule sketch

- Monthly, over a lookback (param ~252 days) form the return scenario matrix,
  identify the worst-(1-alpha) tail days of the portfolio, compute each asset's
  component CVaR over those days, and solve for long-only weights that equalize
  the component-CVaR shares (SLSQP); weights sum to 1.
- Parameters: lookback 126–504 days; alpha 0.90–0.99.

## Universe fit

Full universe (returns matrix only) — long-only, monthly, clean fit, same data
footprint as minimum-CVaR. Imperfect: the tail is defined by only ~12 days at
alpha=0.95 over 252 observations, so component CVaR is noisy and the
equal-contribution solution can be unstable month to month (turnover); the
objective is non-convex, so SLSQP may land on a local optimum — validated by the
DSR/PBO/SPA battery.
