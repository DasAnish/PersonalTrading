---
title: Network Risk Parity (graph-theory portfolio construction)
source: "https://link.springer.com/article/10.1057/s41260-023-00347-8 — 'Network Risk Parity: graph theory-based portfolio construction', Journal of Asset Management (2023)"
mechanism: diversification
status: validated
date_added: 2026-07-13
date_built: 2026-07-13
build_verdict: PASS
build_note: "Base (252d lookback): Sharpe 0.836, total return 42.04%, max DD -17.95%, validation WARN. Variant (126d): Sharpe 1.045 (better), return 61.28%, DD -9.53%, validation PASS (excellent). Variant selected for deployment."
---

## Hypothesis (pre-registered)

Risk-based allocation improves when the asset covariance/correlation structure
is represented as a **network graph** rather than a hierarchical tree. Network
Risk Parity builds a graph whose nodes are assets and whose edges encode
correlation strength (e.g. a minimum spanning tree or a filtered correlation
network), then allocates risk according to each asset's position/centrality in
that graph so that peripheral, weakly-connected assets receive more weight and
densely-connected clusters are down-weighted. The economic rationale is the
same diversification premium HRP targets — avoid concentrating risk in
correlated blocks, and sidestep the unstable covariance-matrix inversion that
mean-variance requires — but the graph representation captures cross-cluster
linkages that HRP's strict binary tree discards, which the paper argues yields
better out-of-sample risk-adjusted returns and lower turnover. This is
mechanically distinct from the repo's existing HRP / risk-parity /
minimum-variance strategies: HRP recursively bisects a dendrogram, whereas this
weights by network topology (centrality) over a filtered graph. Expected
standalone Sharpe: roughly 0.4–0.7, in line with other diversification
strategies on this universe, with the differentiator being steadier drawdowns
and lower turnover than mean-variance rather than a higher raw return.

## Rule sketch

- **Signal / construction**: from a trailing covariance estimate, build a
  correlation network, filter it (minimum spanning tree or threshold graph),
  and compute a node centrality measure (degree / eigenvector / betweenness).
  Allocate weight inversely to centrality and/or to equalize each node's risk
  contribution given the graph, then normalize to sum to 1 (long-only, fully
  invested).
- **Rebalance rule**: monthly, matching repo cadence, on a trailing covariance
  window.
- **Parameters** (plausible ranges, not fitted): covariance lookback 120–252
  trading days; centrality measure ∈ {degree, eigenvector, betweenness};
  graph filter ∈ {MST, correlation-threshold}; optional shrinkage on the
  covariance estimate.

## Universe fit

Applies to the full 13-ETF universe (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC, VUTY,
SGLN, SSLN, BRNT, CRUD, COMM/WCOA) — needs only the return covariance, which is
already computed for the existing HRP/risk-parity strategies. Long-only and
monthly-compatible with no adaptation. Imperfect fit: (1) with only ~13 nodes
the network is small, so centrality measures are coarse and some graph filters
(e.g. betweenness on an MST) may be unstable — expect sensitivity to the
covariance window. (2) The natural clusters here (three equity blocks, one
bond, precious metals, energy, broad commodities) are few and fairly obvious,
so the incremental benefit over the repo's existing HRP may be modest; the test
is whether graph centrality beats HRP's dendrogram bisection out-of-sample on
this specific low-asset-count universe.
