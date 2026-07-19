---
title: Strategy-Level (Factor) Momentum — time-series momentum applied to sleeve returns
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3014521
mechanism: meta
status: built
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Ehsani & Linnainmaa (Journal of Finance, 2022) show factor returns exhibit
time-series momentum: a factor's own trailing 12-month return predicts its next-month
return, and holding only factors with positive trailing returns outperforms holding
all factors. Applied here at the strategy-sleeve level: each month hold (equal-weight)
only the library sleeves whose own trailing 12-month paper NAV return is positive,
with the freed weight parked in the defensive sleeve (VUTY/SGLN blend). Economic
rationale: factor premia are autocorrelated because arbitrage capital moves slowly
and crowding builds gradually; the same slow-moving-capital argument applies to
mechanism-level sleeve returns. Pre-registered expectation: Sharpe uplift of
0.1–0.3 over the static equal-weight blend of the same sleeves, with lower drawdown
(the timing kicks sleeves out during their regime-mismatch periods). Distinct from
strategy_level_risk_parity_ensemble (risk weighting, no return timing) and from
meta_risk_managed (vol scaling, not sign timing).

## Rule sketch

- Sub-strategy set: 4–6 validated, mechanism-diverse sleeves (e.g. DAA canary,
  min-CVaR core6, TSM core8, stock-bond correlation regime, network RP defensive).
- Each rebalance (monthly): simulate/read each sleeve's trailing 252-trading-day
  return from its own weight path; include sleeve iff trailing return > 0.
- Blend included sleeves equal-weight; weight of excluded sleeves goes to a
  defensive asset (VUTY or 50/50 VUTY/SGLN), keeping the portfolio long-only.
- Parameters: lookback 252d (variant: 126d), monthly rebalance.

## Universe fit

Fully implementable long-only, monthly, on the current UCITS universe — the signal
is computed from sleeve paper NAVs, not from any instrument we lack. Requires the
meta layer to compute sub-strategy trailing returns (portfolio_values plumbing as in
VolatilityTargetStrategy); no futures curve or implied-vol data needed. Caveat: with
T≈10y and monthly rebalances the timing signal has few independent flips per sleeve;
judge on k-fold stability, not point Sharpe.
