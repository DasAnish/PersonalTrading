---
title: Commodity Momentum with Intra-Market Correlation Filter
source: Fuertes, Miffre & Rallis (2010), Journal of Banking & Finance 34(10)
mechanism: momentum-cs
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Cross-sectional momentum in commodities earns a positive risk premium
(hedging-pressure / underreaction to term-structure information), and the
premium is cleaner when the momentum signal is filtered by how correlated the
commodity is to the rest of the commodity complex. Low-correlation winners
carry more idiosyncratic, less crowded momentum, so tilting toward recent
winners that also sit apart from the pack should raise the information ratio
versus naive commodity momentum. Because commodities have low correlation to
equities, even a modest-Sharpe commodity momentum sleeve adds portfolio
diversification value. Expected standalone Sharpe 0.3–0.6 (commodity momentum
is noisier and more drawdown-prone than equity momentum), with the correlation
filter expected to improve it modestly and, more importantly, reduce
concentration into whichever commodity is currently trending hardest. Edge
concentrated in the commodity sleeve; near-zero direct effect on equity regions.

## Rule sketch

- Monthly, over the commodity subset compute a 6-month trailing return (range
  3–12 months) and rank cross-sectionally.
- For each commodity compute its average pairwise correlation to the other
  commodities over the same window; down-weight or exclude high-correlation
  names so the held basket favours winners with distinct behaviour.
- Hold the top-ranked, lower-correlation commodities (equal-weight, ~2–3
  names), rebalanced monthly. Optionally apply an absolute-momentum gate:
  drop to zero commodity exposure (hold VUTY/cash) when the whole complex has
  negative trailing return.

## Universe fit

Maps to the commodity ETFs only: SGLN, SSLN (metals), BRNT, CRUD (oil),
COMM/WCOA (broad). VUTY/cash as the absolute-momentum fallback. Long-only,
monthly rebalanced — clean fit for the momentum and correlation legs, both
computable from price history. Imperfect: the source paper's strongest signal
is the *term-structure / roll-yield* leg, which is **not implementable here** —
these are physically-backed or single-contract ETFs with no exposed futures
curve, so backwardation/contango cannot be measured. This idea therefore keeps
only the momentum + correlation portion. Universe is also small (5–6 commodity
ETFs, some overlapping, e.g. BRNT/CRUD both oil), limiting cross-sectional
breadth versus the paper's full futures cross-section.
