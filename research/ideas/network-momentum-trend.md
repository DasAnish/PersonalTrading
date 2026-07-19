---
title: Network Momentum — trend-following enhanced with peer-spillover signal
source: https://arxiv.org/abs/2501.07135
mechanism: trend
status: validated
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Li & Ferreira (2025, arXiv 2501.07135, "Follow the Leader") show momentum
spillover: trending behaviour in one market leads/lags connected markets, and
blending a cross-sectional network momentum indicator with univariate trend
signals yields statistically significant improvements in Sharpe, skew and
downside performance versus univariate-only trend. Economic rationale: slow
information diffusion across connected markets — a trend established in a
leader propagates to correlated peers with a lag, so peers' recent trends carry
incremental predictive content for an asset beyond its own trend. Pre-registered
expectation here: modest Sharpe improvement over time_series_momentum_core8
(1.28) with better skew/drawdown, from confirming weak own-trends with network
agreement and vetoing false own-trend starts when the network disagrees.

## Rule sketch

- Trailing 252d correlation matrix on daily returns; asset i's neighbours =
  assets with correlation > 0.4 to i (excluding i).
- Own signal s_i = sign(252d return); network signal n_i = sign of
  correlation-weighted mean of neighbours' 252d returns.
- Exposure: s_i>0 and n_i>0 → 1.0; exactly one positive → 0.5; both ≤0 → 0.
  Assets with no neighbours fall back to own signal only (1.0/0).
- Weights ∝ exposure / trailing 63d vol, normalised; all-zero fallback:
  defensive equal-weight (VUTY, SGLN). Monthly rebalance; universe core_8
  (variant: all).

## Universe fit

Directly implementable long-only monthly on daily closes; the ETF panel gives
a natural cross-asset network (equity/bond/metal/commodity sleeves). Doesn't
fit: the paper's commodity-futures breadth (58+ markets) — with 8–29 ETFs the
network is small, so neighbour sets are coarse; treat that as part of the test.
