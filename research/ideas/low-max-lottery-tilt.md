---
title: Low-MAX Lottery-Avoidance Tilt
source: Bali, Cakici & Whitelaw (2011), Journal of Financial Economics 99(2)
mechanism: vol-premium
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Bali, Cakici & Whitelaw show that assets with high recent maximum daily returns
("lottery-like" payoffs) subsequently underperform: investors with a preference
for positive skew overpay for the small chance of a large gain, depressing
forward returns on high-MAX assets. A long-only tilt toward the lowest-MAX
assets harvests the mirror of this premium and avoids the lottery-chasing crowd.
The signal is an extreme single-day tail feature — the average of an asset's
few largest daily returns over a trailing month — economically distinct from
average volatility (LowVolatilityTilt), residual volatility (Low-IVOL), and
systematic/downside beta. Expected Sharpe ~0.5–0.9; the effect is a behavioural
premium and may be weaker at the asset-class-ETF level than in single stocks,
but should still tilt away from whichever asset has recently spiked. Low
correlation to the momentum sleeve makes it a diversifier.

## Rule sketch

- Monthly, over a trailing window (param ~63 days / 3 months) compute each
  asset's MAX signal = mean of its top `n_max` daily returns (param, default 5).
- Rank ascending; equal-weight the bottom_n lowest-MAX assets (param ~4–6);
  zero the rest. Long-only, sum to 1.
- Parameters: lookback 21–126 days; n_max 1–10; bottom_n 3–6.

## Universe fit

Full universe — long-only, monthly, price-history only, clean fit (same
footprint as the other low-risk tilts). Imperfect: MAX is designed for a large
single-stock cross-section; on ~13 asset-class ETFs the signal is coarse and a
recent commodity/equity spike can dominate the ranking. Bonds/gold with low
day-to-day extremes will tend to be perennially selected, so the tilt overlaps
somewhat with a generic defensive basket.
