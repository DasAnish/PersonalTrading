---
title: Risk-Adjusted (Sharpe-Ratio) Momentum
source: Rachev, Jasic, Stoyanov & Fabozzi (2007), Journal of Banking & Finance 31(8)
mechanism: momentum-cs
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Rachev, Jasic, Stoyanov & Fabozzi show that ranking assets by a reward-to-risk
criterion (Sharpe or a tail-adjusted STARR ratio) rather than by raw past return
produces momentum portfolios with more consistent, better risk-adjusted profits.
Scaling trailing return by its own volatility down-weights assets whose gains
came with high volatility (often mean-reverting or luck-driven) and favours
assets with steady, high-quality trends — the same underreaction edge as raw
momentum but with a cleaner signal. Expected standalone Sharpe ~0.5–0.9, in line
with or modestly above raw-return momentum, with lower volatility and shallower
momentum-crash drawdowns. Distinct from the repo's MomentumTopN (raw trailing
return) and TimeSeriesMomentum (vol-scaled sign): this ranks cross-sectionally on
the trailing Sharpe level itself.

## Rule sketch

- Monthly, compute each asset's trailing Sharpe = mean/std of daily returns over
  a lookback (param, ~126 days). Rank descending; hold the top_n (param, ~2–4)
  equal-weighted. Absolute-momentum gate: keep only positive-Sharpe picks, route
  freed weight to the safe asset (VUTY). Long-only, sum to 1.
- Parameters: lookback 63–252 days; top_n 2–4.

## Universe fit

Full universe with VUTY as the absolute-momentum fallback — long-only, monthly,
price-history only, clean fit. Imperfect: the original study is a single-stock
cross-section; on ~13 asset-class ETFs the Sharpe ranking is coarse and, like
all top-N rotations here, concentrated and turnover-heavy. Trailing Sharpe over
short windows is noisy, so the ranking can be unstable month to month.
