---
title: Hurst-Exponent Regime Filter (trend vs mean-reversion per asset)
source: Lo (1991), Econometrica 59(5) — Long-Term Memory in Stock Market Prices
status: built
mechanism: regime
date_added: 2026-07-20
---

## Hypothesis (pre-registered)

Lo (1991) formalised testing for long-range dependence in asset returns
(rescaled-range / Hurst analysis); the applied literature since (e.g. Qian &
Rasheed 2004) uses the Hurst exponent H as a per-series predictability gauge:
H > 0.5 indicates persistence (trend-following should work), H < 0.5
anti-persistence (mean-reversion should work). Economic rationale: different
assets/periods sit in different microstructure and flow regimes; conditioning
the RULE CHOICE on measured persistence should beat applying one rule
everywhere. This universe's evidence agrees: trend rules PASS on core_8 while
mean-reversion works on equity sub-universes. Pre-registered expectation:
per-asset rule-switching earns Sharpe between pure TSM (1.28) and MTP (1.5x)
with k-fold stability; if H estimation noise dominates (252d window is short
for H), it will land below pure TSM — that is the failure mode being tested.

## Rule sketch

- Per asset: estimate H from trailing 252d daily returns as the slope of
  log(std of k-day aggregated returns) vs log(k), k in {1, 2, 4, 8, 16}.
- H > 0.55: trend rule — exposure = 1 if 252d return > 0 else 0.
- H < 0.45: reversion rule — exposure = 1 if 21d return < 0 else 0.5.
- 0.45 ≤ H ≤ 0.55: neutral — exposure 0.5.
- Weights ∝ exposure / 63d vol, normalised; all-zero fallback defensive
  (VUTY, SGLN). Monthly; universe core_8.

## Universe fit

Long-only monthly from daily closes; nothing missing. Caveat: H estimated on
252 observations is noisy (±0.1); the neutral band absorbs some noise, and the
verdict tests whether the signal survives estimation error at this window.
