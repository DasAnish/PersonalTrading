---
title: Simple Moving-Average Trend Filter (Faber Tactical Timing)
source: "Faber, M.T. (2007), Journal of Wealth Management — 'A Quantitative Approach to Tactical Asset Allocation' (SSRN 962461)"
mechanism: trend
status: new
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Faber tests a mechanically simple timing rule — hold an asset when its price
is above its trailing 10-month (≈200-trading-day) simple moving average, hold
cash/bonds otherwise — across the S&P 500 back to 1900 and out-of-sample
across twenty-plus other equity, bond, commodity and REIT indices. The rule
delivers equity-like returns with materially lower volatility and shallower
maximum drawdown than buy-and-hold, because it sidesteps the worst of
sustained bear markets (1929–32, 2000–02, 2008) while giving up comparatively
little in strong uptrends. The economic rationale is the same underreaction /
slow-diffusion-of-information story that underlies time-series momentum more
broadly (investors adjust to new information gradually, producing
autocorrelated trends), but the *signal construction* here is a discrete
binary crossover against a simple, unweighted moving average — mechanically
different from this repo's existing `TrendFollowingStrategy`, which uses a
continuous EWMA-based momentum score (60-day half-life over a 504-day window)
normalized by volatility and smoothed. The SMA crossover is cruder (no
vol-normalization, no continuous position sizing, binary in/out per asset)
but is the specific, widely-replicated rule this paper tests, and is worth
recording as a distinct signal family rather than assuming the existing EWMA
trend strategy already spans it. Expected standalone Sharpe: roughly 0.4–0.6
per asset (in line with the paper's reported risk-adjusted improvement over
buy-and-hold), with the main benefit showing up as drawdown reduction rather
than a large absolute return uplift.

## Rule sketch

- **Signal**: for each asset, compute its trailing simple moving average
  (SMA) over `lookback_months` (paper uses 10 months ≈ 200 trading days).
  Signal is binary: **in** if current price > SMA, **out** (zero weight) if
  price ≤ SMA. No continuous scaling by momentum magnitude or volatility —
  this is the key difference from the repo's existing EWMA trend strategy.
- **Rebalance rule**: monthly, matching this repo's cadence (the original
  paper itself rebalances/checks monthly, so no granularity mismatch here).
- **Portfolio construction**: equal-weight (or fixed-weight) across all
  assets currently "in"; assets that are "out" hold zero weight, with the
  freed capital either left in cash-equivalent (not available long-only
  here) or reallocated pro-rata across the remaining "in" assets.
- **Parameters** (plausible ranges, not fitted): `lookback_months` 8–12
  (or equivalently 160–240 trading days); optional small buffer/hysteresis
  band around the SMA (e.g. ±1–2%) to reduce whipsaw trading at the
  crossover.

## Universe fit

Applies directly to every asset in the 13-ETF universe (VUSA, EQQQ, IWRD,
IMEU, IIND, AIGC, VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA) — the rule needs
nothing but a price history per asset. Long-only and monthly-rebalance
compatible with no adaptation required. What's missing or imperfect: (1) the
"out" position in the original paper is cash or T-bills; this repo has no
pure cash instrument, so an "out" signal must be redirected to VUTY or held
as a reduced-gross-exposure position rather than true cash, which will change
the realized risk/return profile versus the paper; (2) with only 13 assets
and monthly rebalancing, whipsaw around the SMA crossover (buy/sell/buy again
within a few months) is a real cost this repo's transaction-cost model should
capture, and was not a focus of the original single-asset-class study; (3)
this is deliberately a *different* signal family from the existing
`TrendFollowingStrategy` (binary SMA crossover vs. continuous vol-normalized
EWMA) — it should be evaluated as its own candidate, not assumed subsumed by
the strategy already in `strategies/trend_following.py`.
