---
title: Momentum Turning Points — blended slow/fast time-series momentum
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3489539
mechanism: trend
status: validated
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Garg, Goulding, Harvey & Mazzoleni (JFE 149, 2023) show that pure slow (12m) TSM
reacts late at trend turning points while pure fast (1m) TSM generates false alarms;
the intersection of the two signals defines four market cycles (Bull +/+,
Correction +/−, Rebound −/+, Bear −/−) with predictive content — notably
predictably negative returns when both signals are negative. Intermediate-speed
portfolios blending slow and fast signals show higher Sharpe, shallower drawdowns
and more positive skew than either speed alone. Economic rationale: return mean
persistence plus realization noise makes a single-speed filter suboptimal; the
blend translates cycle information into unconditional alpha. Pre-registered
expectation on this universe: Sharpe above the pure time_series_momentum
implementations (1.28 core8) with a smaller max drawdown, driven by cutting
exposure in Bear states and re-entering faster in Rebounds.

## Rule sketch

- Per asset each month: slow signal = sign(trailing 252d return), fast signal =
  sign(trailing 21d return).
- Exposure: Bull (+/+) = 1.0; Correction (+/−) and Rebound (−/+) = 0.5
  (intermediate speed = equal blend of the two signals); Bear (−/−) = 0.
- Long-only weights proportional to exposure / trailing 63d vol (vol-scaled),
  normalised to sum 1; if all exposures 0, hold defensive assets (VUTY/SGLN)
  equal-weight.
- Monthly rebalance; universe core_8 (variant: all).

## Universe fit

Directly implementable long-only monthly on the ETF universe with daily closes
only. Nothing missing. Caveat: paper studies the US equity market series; here
applied cross-asset per instrument — treat cross-asset transfer as part of the
hypothesis being tested. Monthly rebalance samples the fast (1m) signal coarsely;
false-alarm cost appears as turnover.
