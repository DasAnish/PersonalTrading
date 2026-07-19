---
title: Tail Risk Targeting — target-CVaR exposure scaling overlay
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3444999
mechanism: hedging-overlay
status: built
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Rickenberg (2019, SSRN 3444999, "Tail Risk Targeting: Target VaR and CVaR
Strategies") shows that scaling exposure to hit a target VaR/CVaR — instead of
target volatility — earns higher Sharpe ratios, better drawdown protection and
higher utility for mean-variance, CRRA and loss-averse investors; a loss-averse
investor would pay ~18%/year to switch from volatility-managed to downside-risk-
managed exposure. Economic rationale: volatility is a symmetric proxy that
throttles exposure equally after upside and downside moves, while tail-risk
measures (CVaR) react specifically to left-tail thickening, cutting exposure in
crash-prone states and staying invested through benign high-vol rallies.
Pre-registered expectation: applied over a diversified underlying (risk parity /
equal weight), lower max drawdown than the equivalent vol-target overlay at
similar or better Sharpe.

## Rule sketch

- Overlay on an underlying allocation: compute the underlying's realised
  per-period CVaR at ``alpha`` = 95% from its portfolio-value returns over the
  trailing ``lookback_days`` window (mean of the worst 5% of returns, sign
  flipped).
- Scale = target_cvar / realised_cvar, capped to [0, 1] (no leverage —
  scaling down parks the remainder in cash).
- Monthly rebalance, same cadence as the underlying.

## Universe fit

Overlay is instrument-agnostic — works over any existing allocation on the
UCITS universe, long-only monthly, using only the underlying's simulated NAV.
Doesn't fit: nothing missing. Caveat: monthly NAV sampling gives few tail
observations in a 252d window; use daily-frequency portfolio proxy where the
overlay plumbing provides it, and judge on drawdown reduction vs the matching
``*_15vol`` composed variants.
