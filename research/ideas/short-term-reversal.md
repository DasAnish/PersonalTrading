---
title: Short-Term (1-Month) Reversal
source: Jegadeesh (1990), Journal of Finance 45(3)
mechanism: mean-reversion
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Assets that did worst over the most recent month tend to bounce back the
following month, and recent winners give back some gains — a short-horizon
reversal driven by liquidity-provision compensation and investor overreaction /
price-pressure that unwinds quickly. A long-only cross-sectional tilt harvests
this by overweighting the previous month's biggest losers among the universe.
This is economically distinct from the two reversal ideas already in the repo:
the z-score MeanReversion (20-day band around a moving average) and the
Long-Term Reversal (36–60 month De Bondt–Thaler overreaction). The 1-month
horizon is the classic Jegadeesh reversal and sits between them. Expected Sharpe
modest, 0.2–0.5 at the monthly-rebalanced asset-class level (the effect is
strongest in single stocks and is heavily eroded by transaction costs and by the
coarse monthly frequency), with high turnover. Reversal is most reliable on the
liquid equity-region ETFs; commodities/gold may show weaker or trend-dominated
behaviour. Included mainly as a low-correlation diversifier to the momentum
sleeve, not as a standalone high-Sharpe bet.

## Rule sketch

- Monthly, compute each asset's trailing ~1-month (21-trading-day) total return
  (lookback param, range 15–25 days).
- Rank ascending; select the bottom_n worst performers (param, ~2–4) and
  equal-weight them. All others zero.
- Rebalance monthly. (No skip-month gap — the classic reversal holds the most
  recent losers directly; a momentum sleeve is what uses the 1-month skip.)

## Universe fit

Best on the liquid equity-region ETFs (VUSA, EQQQ, IWRD, IMEU, IIND); can run
over the full universe but gold/commodities may dilute the effect. Long-only,
monthly, price-history only — clean fit. Imperfect: the anomaly's documented
edge is at daily/weekly horizons on single stocks; forcing it to monthly
rebalancing on ~13 asset-class ETFs captures only a coarse, weakened version, and
turnover (fully reshuffling into last month's losers) is high relative to the
repo's other allocations. Cannot short the winners (long-only), so it captures
only the loser-rebound leg.
