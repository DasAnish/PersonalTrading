---
title: Low Downside-Beta Defensive Tilt
source: Ang, Chen & Xing (2006), Review of Financial Studies 19(4)
mechanism: vol-premium
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Ang, Chen & Xing show downside beta — an asset's sensitivity to the market
specifically when the market falls — is priced separately from ordinary market
beta, carrying a premium of ~6% p.a. that survives controls for beta, size,
value, momentum, coskewness and liquidity. A long-only *defensive* application
holds the lowest-downside-beta assets: those that decouple from the market
exactly when it sells off, which should deliver a shallow-drawdown, high
risk-adjusted profile — the same low-risk-anomaly family as the repo's validated
low-beta and low-volatility tilts, but keyed to crash co-movement rather than
full-sample beta or total volatility. Expected Sharpe ~0.8–1.2 with a notably
smaller max drawdown than cap-weight; the distinguishing benefit over plain
low-beta is better behaviour in market crashes, where downside beta is the
relevant risk. Distinct from LowBetaTilt (full beta) and LowVolatilityTilt
(total vol) in signal construction.

## Rule sketch

- Monthly, over a lookback (param, ~252 days) estimate each asset's downside
  beta = cov(r_asset, r_mkt | r_mkt below its mean) / var(r_mkt | down days),
  market proxy IWRD (fallback VUSA).
- Rank ascending; equal-weight the bottom_n lowest-downside-beta assets (param,
  ~4–6); zero the rest. Long-only, sum to 1.
- Parameters: lookback 126–504 days; bottom_n 3–6.

## Universe fit

Full universe with IWRD as market proxy — long-only, monthly, price-history
only, clean fit (same footprint as the validated LowBetaTilt). Imperfect: a
252-day window contains only ~120 down-market days, so the conditional beta is
noisier than full-sample beta; non-equity assets (gold, bonds, commodities) have
unstable betas to an equity proxy, so their low downside beta may reflect near-
zero equity correlation rather than a genuine defensive premium — the tilt will
naturally favour those assets, which is defensible defensively but drifts from
the paper's equity-cross-section origin.
