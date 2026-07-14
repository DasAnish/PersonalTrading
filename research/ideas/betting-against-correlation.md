---
title: Betting Against Correlation (Low Average-Correlation Tilt)
source: Asness, Frazzini, Gormsen & Pedersen (2020), Journal of Financial Economics 135(3)
mechanism: vol-premium
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

The low-risk (betting-against-beta) premium decomposes into a volatility
component and a correlation component. Asness, Frazzini, Gormsen & Pedersen show
that the correlation component — betting against correlation (BAC) — carries much
of the low-risk effect and discriminates between competing theories: BAC is
strong, consistent with leverage-constraint explanations, whereas the pure
lottery/skewness story predicts it should be weak. A long-only tilt toward the
assets with the lowest average pairwise correlation to the rest of the universe
harvests this premium while simultaneously maximising diversification (low-corr
assets contribute least to portfolio variance). Expected Sharpe ~0.8–1.2 on this
multi-asset universe, with a defensive, well-diversified profile. Distinct from
the validated LowBetaTilt (full beta = vol x corr), LowVolatilityTilt (vol only)
and the FAA strategy (which uses correlation as one of three blended factors, not
as a standalone objective).

## Rule sketch

- Monthly, over a lookback (param ~252 days) compute the return correlation
  matrix and each asset's mean pairwise correlation to the others. Rank
  ascending; equal-weight the bottom_n lowest-average-correlation assets (param
  ~4–6); zero the rest. Long-only, sum to 1.
- Parameters: lookback 126–504 days; bottom_n 3–6.

## Universe fit

Full universe — long-only, monthly, price-history only, clean fit. Imperfect:
average correlation is measured against this specific 13-ETF basket, so the
signal is universe-relative rather than absolute; the lowest-correlation assets
will typically be gold/bonds/commodities (structurally decoupled from equities),
so the tilt overlaps with a real-asset/defensive basket and may under-hold
equities in calm regimes. Correlation estimates are noisy on short windows.
