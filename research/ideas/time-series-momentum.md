---
title: Time-Series Momentum (vol-scaled trailing-return sign)
source: "Moskowitz, Ooi & Pedersen (2012), Journal of Financial Economics 104(2), 228–250 — 'Time Series Momentum'"
mechanism: trend
status: validated
date_added: 2026-07-13
date_built: 2026-07-13
build_verdict: WARN
build_note: "Base (12m lookback): Sharpe 0.989, total return 20.61%, max DD -6.51%, validation WARN. Variant (9m): Sharpe 1.157 (better), return 20.02%, DD -4.47%, validation WARN. Selected variant recommended for deployment."
---

## Hypothesis (pre-registered)

The sign of an asset's own trailing 12-month excess return predicts its next
month's return: instruments that have risen over the past year tend to keep
rising, and those that have fallen tend to keep falling, across equities,
bonds, commodities and currencies. Moskowitz, Ooi & Pedersen show a
volatility-scaled portfolio built on this single rule over 58 futures markets
(1985–2009) earns an annualized Sharpe near 1.0 gross, with strong performance
during equity crises (positive convexity / "crisis alpha") because sustained
sell-offs are themselves trends. The economic rationale is initial
underreaction to news followed by delayed overreaction (behavioural), plus
demand from risk-management and hedging flows that push prices in the trend
direction. Two features distinguish this from the repo's existing trend and
SMA-crossover strategies: (1) the signal is the **sign of the raw 12-month
return** (not price vs. a moving average, and not a continuous EWMA score),
and (2) each asset's position is **scaled by the inverse of its own recent
realized volatility** so that every asset contributes roughly equal risk.
Expected standalone Sharpe on a long-only 13-ETF adaptation: roughly 0.4–0.7 —
below the paper's long-short futures figure because we cannot short and cannot
hold true cash, with the benefit concentrated in drawdown reduction and
crisis-period convexity.

## Rule sketch

- **Signal**: for each asset, sign of the trailing `lookback_months` excess
  return (paper uses 12 months). Positive → hold; non-positive → zero weight
  (long-only, so no short leg).
- **Risk scaling**: weight each held asset proportional to
  `target_vol / realized_vol_i`, where realized vol is measured over a trailing
  window (e.g. ex-ante 60-day or exponentially weighted, paper targets a
  constant per-asset vol). Normalize weights to sum to 1 (fully invested).
- **Rebalance rule**: monthly, matching repo cadence.
- **Parameters** (plausible ranges, not fitted): `lookback_months` 9–12;
  vol-estimation window 40–120 trading days; optional portfolio-level
  vol-target for overlay use.

## Universe fit

Applies to all 13 ETFs (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC, VUTY, SGLN, SSLN,
BRNT, CRUD, COMM/WCOA) — needs only each asset's price and return history.
Long-only, monthly-compatible. Imperfect fit: (1) the paper's short leg is
central to its crisis convexity; long-only forfeits the profits from shorting
falling markets, so realized crisis alpha will be weaker. (2) No cash
instrument — assets with a non-positive signal go to zero weight and capital is
redistributed to the remaining "in" assets (raising concentration) rather than
sitting in T-bills as in the paper; redirecting to VUTY is an alternative but
changes the risk profile. (3) The vol-scaling step is the key differentiator
from `sma-trend-filter` (binary, unscaled) and the existing EWMA
`TrendFollowingStrategy` (continuous score, not a raw-return sign) — evaluate as
its own signal family.
