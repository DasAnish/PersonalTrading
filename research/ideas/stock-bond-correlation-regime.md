---
title: Stock-Bond Correlation Regime Allocation
source: https://www.aqr.com/Insights/Research/Journal-Article/A-Changing-Stock-Bond-Correlation
mechanism: regime
status: new
date_added: 2026-07-10
---

## Hypothesis (pre-registered)

Brixton, Brooks, Hecht, Ilmanen, Maloney & McQuinn (2023, Financial Analysts
Journal; AQR) show the stock-bond correlation was persistently negative
2000–2020 but positive for most of the prior three decades, driven by
inflation-uncertainty regimes. When the correlation turns positive, bonds stop
hedging equity risk and a bond-heavy defensive sleeve becomes dead weight or
worse. Edge: structural/macro — allocating the defensive sleeve conditionally
on the observed correlation regime should preserve diversification when it
exists and substitute real assets (gold, commodities) when it does not.
Expected improvement is defensive, not return-generating: portfolio Sharpe
gain 0.1–0.2 and materially lower drawdown in inflationary regimes vs a static
60/40-style mix. Should show up on the bond sleeve of any balanced allocation.

## Rule sketch

- Compute rolling correlation of daily (or monthly) equity vs bond returns,
  lookback 24–36 months.
- If correlation < threshold (0 to +0.1): defensive sleeve = bonds (VUTY).
- If correlation >= threshold: shift defensive sleeve to gold + broad
  commodities (50/50 or inverse-vol), keeping equity sleeve unchanged.
- Defensive sleeve size fixed (parameter: 30–50%); rebalance monthly.
- Optional hysteresis band (±0.05) to cut regime-flip turnover.

## Universe fit

Equity sleeve: VUSA/IWRD (universe:equity). Bond leg: VUTY (US Treasuries
GBP-hedged) — the only bond ETF, so "bonds" is a single-asset leg.
Real-asset substitutes: SGLN, COMM/WCOA. Fit imperfect: one treasury ETF
means no duration choice; GBP-hedged share class slightly distorts the USD
stock-bond correlation being measured; short history limits the number of
regime flips observed (correlation was mostly negative post-2000, so the
positive-correlation branch is thinly sampled in-sample — flag for validation).
