---
title: 52-Week High Momentum
source: "George & Hwang (2004), The Journal of Finance 59(5) 2145–2176 — 'The 52-Week High and Momentum Investing'"
mechanism: momentum-cs
status: validated
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

George & Hwang show that ranking assets by *nearness to their 52-week high*
(current price divided by the trailing 52-week high price) explains a larger
share of momentum profits than ranking by trailing total return, and in fact
subsumes and dominates the standard return-based momentum signal once both
are controlled for simultaneously. Their proposed mechanism is anchoring: the
52-week high acts as a psychological reference point, and investors are slow
to bid a price further above it even when justified by fundamentals, so a
price near (or at) a new 52-week high tends to keep drifting up rather than
mean-revert. Critically, the paper finds that 52-week-high-driven momentum
profits do **not** reverse over subsequent years the way standard total-
return momentum partially does — the authors treat this as evidence that
52-week-high momentum and long-horizon reversal (De Bondt & Thaler-style) are
economically distinct phenomena rather than the same effect measured at
different horizons. Expected effect: in the original US equity cross-section
the long-short 52-week-high spread portfolio earned an economically large
premium (several percent annualised, comparable to or larger than standard
momentum in the same sample). On this repo's small, long-only, diversified-
ETF universe the effect should be considerably more muted — these are indices
of hundreds of names each, and anchoring is a single-security bias that
partially averages out at the index level — so a realistic expectation is a
modest Sharpe contribution (0.2–0.5 standalone), best treated as a
signal-construction variant to compare against the existing trailing-return
Top-N momentum rather than a strong standalone edge.

## Rule sketch

- **Signal**: for each asset, compute `price_t / rolling_max(price, 252
  trading days)` — a ratio in (0, 1], with values near 1 indicating the asset
  is near its 52-week high.
- **Rebalance rule**: monthly. Rank all universe assets by this ratio,
  descending; hold the top_n equal-weighted or inverse-volatility-weighted
  (consistent with this repo's existing `MomentumTopNStrategy` weighting
  convention), zero-weighting the rest.
- **Parameters** (plausible ranges): top_n (2–5, matching the existing
  Top-N family's range); lookback window for the rolling high (252 trading
  days per the source paper; a shorter 126-day variant could be tested as a
  sensitivity check); optional inverse-volatility weighting among the
  selected set.

## Universe fit

Maps onto the full 30-asset universe, and most directly onto the 18-asset
equity group in `strategy_definitions/universe.json` (`universe:equity`) —
the closest match to the source paper's single-stock equity sample — with
the bond and commodity groups available as an out-of-sample extension the
original paper does not test. This is a deliberately different signal
construction from the two momentum-cs strategies already in this repo:
`MomentumTopNStrategy` ranks by trailing total return, and
`VolatilityMomentumStrategy` ranks by return scaled by trailing volatility;
52-week-high momentum instead ranks by price level relative to its own
trailing ceiling, which behaves differently in a slow grind-up (total return
and 52-week-high ratio agree) versus a sharp V-shaped recovery (total return
over 12 months can be strongly negative while the price is already back near
its high, or vice versa) — the two signals should be compared for correlation
of selected assets before assuming this adds real diversification of alpha
sources rather than just relabelling the same trades. Nothing is
structurally missing from the universe; this needs only price history.
