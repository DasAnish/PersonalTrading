---
title: Low Idiosyncratic-Volatility Defensive Tilt
source: Ang, Hodrick, Xing & Zhang (2006), Journal of Finance 61(1)
mechanism: vol-premium
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Ang, Hodrick, Xing & Zhang document the "idiosyncratic volatility puzzle":
assets with high residual (market-neutralised) volatility earn abnormally low
returns, so a long-only tilt toward the lowest-idiosyncratic-volatility assets
should earn superior risk-adjusted returns. Idiosyncratic volatility is the
standard deviation of the residual from a market-model regression, isolating
asset-specific risk from market-driven variance. This is the same low-risk
anomaly family as the repo's validated LowVolatilityTilt (total vol) and
LowBetaTilt (systematic beta), but keyed to residual volatility specifically —
economically distinct because it neutralises the market component. Expected
Sharpe ~0.8–1.2 with a defensive, shallow-drawdown profile. On this multi-asset
ETF universe the low-IVOL cohort will tend to include bonds/gold (low residual
vol vs an equity proxy), giving a naturally diversified defensive basket.

## Rule sketch

- Monthly, over a lookback (param, ~252 days) fit r_asset = a + b*r_mkt (proxy
  IWRD/VUSA); idiosyncratic vol = std(residuals). Rank ascending; equal-weight
  the bottom_n lowest-IVOL assets (param ~4–6); zero the rest. Long-only, sum 1.
- Parameters: lookback 126–504 days; bottom_n 3–6.

## Universe fit

Full universe, IWRD proxy — long-only, monthly, price-history only, clean fit
(same footprint as LowBetaTilt/LowVolatilityTilt). Imperfect: for non-equity
assets the market-model residual is nearly the whole return (they have little
equity beta), so low-IVOL overlaps heavily with low-total-vol for bonds/gold;
the market-neutralisation mainly differentiates the ranking among the equity
ETFs. A single equity proxy is a crude market model for a cross-asset universe.
