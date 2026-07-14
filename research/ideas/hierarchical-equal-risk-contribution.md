---
title: Hierarchical Equal Risk Contribution (HERC)
source: Raffinot (2018), SSRN 3237540
mechanism: diversification
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

HERC extends Lopez de Prado's Hierarchical Risk Parity by replacing HRP's naive
recursive-bisection weighting with an equal-risk-contribution split guided by the
actual shape of the correlation dendrogram, and by cutting the tree at an
optimal number of clusters rather than always splitting in two. This should
allocate risk more evenly across genuine correlation clusters than HRP, improving
diversification and lowering drawdown, especially on a heterogeneous multi-asset
universe with clear equity/bond/commodity blocks. The edge is the same
estimation-robust, machine-learning diversification premium as HRP (no matrix
inversion, so less sensitive to noisy covariances than min-variance), but with a
better risk-balanced split. Expected Sharpe comparable to the repo's validated
HRP / network-risk-parity family (~0.7–1.1 here), with equal or shallower max
drawdown and slightly higher volatility. Distinct from the existing HRP,
minimum-variance, risk-parity and network-risk-parity strategies: HERC is
dendrogram-shaped ERC with an optimal tree cut, and can optionally use downside
risk (CVaR/CDaR) as the cluster risk measure.

## Rule sketch

- Monthly, over a covariance lookback (param, ~252 days; range 126–500):
  1. Build the correlation-distance matrix and hierarchically cluster it
     (linkage param: ward/single/average — reuse the repo's HRP linkage code).
  2. Select the number of clusters by the dendrogram gap (or a fixed
     `n_clusters` param).
  3. Top-down, split risk **equally between the two branches at each node**
     (equal risk contribution), recursing to leaves.
  4. Within each final cluster, weight assets by inverse cluster risk (variance
     or, optionally, CVaR — `risk_measure` param).
- Long-only, sum to 1, rebalance monthly. Optional min/max caps (params).

## Universe fit

Best on the full 13-ETF universe (or core_8) where distinct equity/bond/
commodity/gold clusters exist for the dendrogram to find — same data footprint as
HRP (returns matrix only), long-only, monthly, clean fit. Also worth running on
core_6/all to see how cluster structure changes with breadth. Imperfect: with
only ~13 assets the dendrogram is shallow and the "optimal cluster count" step
has little to bite on, so HERC may collapse toward HRP; the benefit grows with
universe size, which is modest here.
