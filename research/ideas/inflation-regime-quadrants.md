---
title: Inflation-Regime Quadrant Allocation (price-proxied)
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4153468
mechanism: regime
status: built
date_added: 2026-07-20
---

## Hypothesis (pre-registered)

Baltussen, Swinkels, van Vliet & van Vliet ("Investing in Deflation, Inflation,
and Stagflation Regimes", Financial Analysts Journal 79(3), 2023; 1875–2021
sample) show asset premiums differ sharply across inflation regimes: moderate
inflation is best for everything; deflation favours bonds (low nominal, good
real); high inflation and especially stagflation destroy real equity and bond
returns while commodities/factor premiums hold up. Economic rationale:
discount-rate and cash-flow channels respond oppositely across regimes, and
regime persistence (inflation is autocorrelated) makes trailing classification
informative. Price-proxied adaptation: commodity-sleeve trend proxies inflation,
equity-sleeve trend proxies growth. Pre-registered expectation: drawdown profile
similar to DAA canary (shallow), Sharpe ~1.0–1.4, with the distinct value-add
concentrated in 2022-style stagflation windows where equity+bond both fall.

## Rule sketch

- Inflation proxy: mean trailing 252d return of commodity sleeve (COMM, BRNT,
  SGLN) > 0 → inflationary.
- Growth proxy: mean trailing 252d return of equity sleeve (VUSA, IWRD, EQQQ)
  > 0 → expansion.
- Quadrant sleeves (long-only, inverse-vol within sleeve):
  - Expansion + non-inflationary (goldilocks): equities.
  - Expansion + inflationary: 50% equities, 50% commodities+gold.
  - Contraction + inflationary (stagflation): commodities + gold + cash-like
    short bonds (AGGU).
  - Contraction + non-inflationary (deflation): bonds (VUTY, AGGU) + gold.
- Monthly rebalance; universe core_8 (has all sleeves).

## Universe fit

All four sleeves exist in the universe (equity, commodity, gold, bonds); daily
closes only, long-only monthly. Doesn't fit: true CPI/macro data (paper uses
realized inflation) — price-proxy classification is the tested hypothesis;
misclassification risk highest at regime turns.
