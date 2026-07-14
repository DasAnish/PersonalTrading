---
title: Minimum CVaR Portfolio (tail-risk optimization)
source: Rockafellar & Uryasev (2000), Journal of Risk 2(3)
mechanism: diversification
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Conditional Value-at-Risk (CVaR, expected shortfall) measures the average loss in
the worst tail of the return distribution and, unlike variance, is a coherent
risk measure that directly targets tail losses. Minimizing portfolio CVaR
allocates away from assets that contribute to deep joint drawdowns, which should
produce a shallower left tail and smaller max drawdown than minimum-variance,
especially when returns are fat-tailed or crash-correlated. The edge is
tail-risk reduction rather than raw Sharpe: expected Sharpe comparable to the
minimum-variance family (~0.6–1.0 here), but with a materially better
maximum-drawdown and downside-capture profile in stressed regimes. Rockafellar &
Uryasev show CVaR minimization reduces to a tractable linear program. This is a
construction mechanism the repo does not yet have (it has full-variance
min-variance, HRP, risk parity, and — as a separate new idea — semivariance, but
no explicit tail/expected-shortfall objective).

## Rule sketch

- Monthly, over a return-history lookback (param, ~252 days; range 126–500) at
  confidence level `alpha` (param, default 0.95; the worst 5% of scenarios),
  solve the Rockafellar–Uryasev LP for long-only weights that minimize the
  portfolio's `alpha`-CVaR subject to `sum(w)=1`, `w>=0`.
- Use the historical/empirical return scenarios directly (no distributional
  assumption). Optional min/max weight caps (params).
- Rebalance monthly.

## Universe fit

Runs on the full universe (or core_6/core_8) from a returns matrix alone —
long-only, monthly, clean fit, same data footprint as minimum_variance.
Imperfect: at `alpha=0.95` on ~252 daily observations the tail is defined by only
~12 scenarios, so the CVaR estimate is noisy and the optimizer can be unstable
month-to-month (higher turnover); a longer lookback or lower alpha trades tail
sharpness for stability. Empirical CVaR frontiers are known to be fragile
out-of-sample, so validation (DSR/PBO/SPA) is the real test.
