---
title: Inverse-Volatility (Naive Risk Parity) Portfolio
source: Leote de Carvalho, Lu & Moulin (2012), Financial Analysts Journal 68(3)
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Weighting each asset proportionally to the inverse of its trailing volatility is
the simplest risk-based allocation — no covariance estimation, no optimization,
so no estimation error to overfit. Leote de Carvalho, Lu & Moulin show risk-based
strategies (inverse-vol, ERC, min-variance, max-diversification) share a common
low-beta / low-vol tilt, and the "optimal versus naive diversification"
literature (DeMiguel, Garlappi & Uppal 2009) finds simple schemes often match or
beat optimized ones out-of-sample because they avoid estimation error. Inverse-
vol should deliver a defensive, well-diversified allocation with a Sharpe in line
with the validated risk-parity / minimum-variance family (~0.8–1.2 on the full
universe) and very low turnover. Distinct from RiskParityStrategy, which solves
the full equal-risk-contribution problem using the covariance matrix (inverse-vol
ignores correlations); serves as the robust naive baseline for that family.

## Rule sketch

- Monthly, compute each asset's trailing volatility over a lookback (param ~126
  days); weight proportionally to 1/vol, normalized to sum 1. Long-only.
- Parameters: lookback 63–252 days.

## Universe fit

Full universe (returns only) — long-only, monthly, clean fit, minimal data
footprint. Imperfect: ignores correlations entirely, so it can double-count
risk when several held assets are highly correlated (e.g. multiple equity
regions); it will structurally over-weight the lowest-vol assets (bonds), giving
a bond-heavy, low-return profile unless the universe is balanced.
