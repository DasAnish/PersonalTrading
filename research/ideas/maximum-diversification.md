---
title: Maximum Diversification Portfolio
source: "Choueifaty & Coignard (2008), The Journal of Portfolio Management 35(1) 40–51 — 'Toward Maximum Diversification'"
mechanism: diversification
status: rejected
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Choueifaty & Coignard define the *diversification ratio* of a portfolio as the
weighted average of the constituents' individual volatilities divided by the
portfolio's own (realised) volatility — a ratio of 1 means no diversification
benefit at all (fully correlated), and it rises the more the holdings'
movements offset each other. The Most-Diversified Portfolio (MDP) is the
long-only portfolio that maximises this ratio subject to weights summing to 1.
This is a genuinely different objective from the three risk-based allocators
already in this repo: Minimum Variance minimises absolute portfolio variance
(and can concentrate heavily in the single lowest-vol asset if correlations
allow), Risk Parity equalises each asset's marginal risk contribution, and HRP
approximates risk parity via correlation-distance clustering. MDP instead
explicitly rewards *low pairwise correlation*, independent of an asset's own
volatility level — a high-vol, low-correlation asset can still earn a large
weight if it improves the ratio. The economic rationale is structural rather
than a risk premium: diversification reduces portfolio variance "for free"
(no expected-return cost), so a portfolio explicitly built to maximise it
should deliver a smoother return path and higher Sharpe than cap-weighted or
naive equal-weight benchmarks, and plausibly than MinVar/RiskParity/HRP too,
particularly on a universe spanning multiple weakly-correlated asset classes
(equities, bonds, precious metals, commodities) rather than a single-asset-
class universe. The original paper's own backtests (US and European equity
universes, long history) report volatility reduction and Sharpe improvement
versus cap-weighted and equal-weight of a similar order of magnitude to
minimum-variance portfolios; on this repo's much smaller, cross-asset-class,
long-only ETF universe the realistic expectation is a Sharpe in the same
ballpark as the existing diversification-mechanism strategies (roughly
0.4–0.8 depending on regime), with the differentiator being *lower turnover
and more stable weights* than MinVar (which can be unstable/corner-heavy)
rather than a dramatically higher headline Sharpe.

## Rule sketch

- **Signal**: trailing covariance matrix Σ (e.g. 252-day daily or trailing
  12-month monthly returns) and the vector of individual asset volatilities σ
  (diagonal of Σ, square-rooted).
- **Optimisation**: solve for long-only weights w (w ≥ 0, sum(w) = 1) that
  maximise (wᵀσ) / sqrt(wᵀΣw) — equivalent to a quadratic program very close
  in form to the existing `MinimumVarianceStrategy`'s scipy SLSQP setup, but
  on correlation-normalised exposures rather than raw variance.
- **Rebalance rule**: monthly, consistent with this repo's standard cadence.
- **Parameters** (plausible ranges, not fitted): covariance lookback window
  (126–504 trading days); optional per-asset weight cap (e.g. ≤40%) to match
  the existing constraint-overlay pattern (`ConstraintStrategy`) and prevent
  the optimiser collapsing into 1–2 assets when correlations are unusually
  low for a stretch.

## Universe fit

Maps cleanly onto the full 30-asset universe defined in
`strategy_definitions/universe.json` (equity, bond, and commodity groups) —
this is a pure price/covariance-based method with no dependence on yield,
carry, or fundamental data, so every asset in the universe is usable without
a proxy or caveat. The idea is expected to differentiate most clearly from
the existing `MinimumVarianceStrategy`, `RiskParityStrategy`, and
`HRPStrategy` (all tagged `diversification`) precisely because those three
optimise variance/risk-contribution directly, while MDP optimises a
correlation-based ratio — a head-to-head comparison across all four on the
same universe and rebalance schedule would be the natural first backtest.
Nothing structurally missing: unlike the carry or vol-regime ideas in this
backlog, this needs only the price history already collected for every asset.
