---
title: Absorption Ratio (PCA systemic-risk) regime de-risking
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1633027
mechanism: regime
status: built
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Kritzman, Li, Page & Rigobon (JPM 37(4), 2011) define the absorption ratio: the
fraction of total return variance explained by the top K eigenvectors of the asset
correlation matrix (K ≈ N/5). High/rising AR means risk is concentrated — markets
tightly coupled and fragile; most crises (1997 Asia, 1998 LTCM, 2008 Lehman)
coincided with positive AR shifts. The paper shows a standardized AR shift
(15d vs 1y mean, in σ units) timing rule materially improved equity/bond switching
performance. Economic rationale: structural — when one common factor drives
everything, diversification mechanically fails, so ex-ante derisking before
correlated drawdowns adds value. Pre-registered expectation: applied as a
de-risking regime signal on a diversified allocation, similar drawdown reduction
to the DAA canary with modest CAGR give-up; Sharpe ≥ underlying with MaxDD cut by
a quarter or more. Distinct from the rejected turbulence overlay (Mahalanobis
outlier distance — a different statistic measuring unusualness, not concentration)
and from stock-bond correlation regime (pairwise, two assets only).

## Rule sketch

- Universe: all liquid assets in the panel (needs N ≥ 10 for meaningful PCA).
- Each rebalance: compute correlation matrix on trailing 252d daily returns;
  AR = sum of top-K eigenvalues / trace, K = round(N/5).
- Signal: ΔAR = (mean AR over last 15d − mean AR over last 252d) / std of AR
  over last 252d.
- ΔAR > +1σ → defensive posture (shift to VUTY/SGLN/cash sleeve);
  ΔAR < −1σ → full risk-on allocation; between → hold underlying weights.
- Underlying: risk parity or equal weight on universe:all; monthly rebalance.

## Universe fit

Implementable long-only monthly on the 29-asset panel — only needs daily closes.
Post-ragged-panel the 10y window gives enough history for the 1y AR baseline.
Doesn't fit: nothing missing (no derivatives needed). Risks: daily AR series at
monthly rebalance dates is a sampled signal (paper uses daily shifts); eigenvalue
estimates noisy with 252 obs × 29 assets — use Ledoit-Wolf shrinkage before PCA.
