---
title: Residual (Idiosyncratic) Momentum
source: "Blitz, D., Huij, J. & Martens, M. (2011), Journal of Empirical Finance 18(3), 506–521 — 'Residual Momentum'"
mechanism: momentum-cs
status: new
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Standard cross-sectional momentum ranks assets on *total* past return. Blitz,
Huij & Martens show that ranking instead on the *residual* return — the part of
each asset's return left over after stripping out its exposure to common
factors (in their equity study, the Fama-French market/size/value factors;
for a multi-asset ETF universe, the natural analogue is the residual from a
market-model regression on a broad benchmark such as IWRD) — produces
risk-adjusted momentum profits roughly twice as large as total-return
momentum, more consistent over time, and less concentrated in the tails of the
cross-section. The economic rationale is that total-return momentum
inadvertently loads on time-varying factor premia and market beta, so its
returns are volatile and prone to "momentum crashes" when the market sharply
reverses; residual momentum isolates the genuine underreaction/slow-diffusion
component (the behavioural edge) while neutralising the incidental factor bets,
which cuts volatility by about half without materially reducing return. This is
a distinct signal construction from the backlog's existing momentum-cs ideas —
Dual Momentum (absolute + relative *total* return) and 52-Week-High Momentum
(proximity to the trailing high) — because it ranks on beta-adjusted residuals
rather than raw price performance. Expected standalone Sharpe: roughly
0.5–0.8, with the improvement over plain momentum showing up primarily as a
higher Sharpe via lower volatility and shallower drawdowns rather than a large
uplift in raw return.

## Rule sketch

- **Signal**: for each asset, regress its trailing returns (e.g. weekly or
  monthly over a 36-month window) on a broad-market benchmark return (IWRD as
  the "market" proxy) to obtain residuals; compute the momentum score as the
  mean residual over the formation window (paper uses months t-12..t-2,
  skipping the most recent month) divided by the standard deviation of those
  residuals (a t-stat-like, information-ratio scaling).
- **Rebalance rule**: monthly, matching this repo's cadence.
- **Portfolio construction**: long-only — rank all assets by residual
  momentum score, overweight the top third/half, zero-weight the bottom;
  equal-weight or score-proportional within the held set.
- **Parameters** (plausible ranges, not fitted): formation window 6–12 months
  with a 1-month skip; residual-estimation window 24–36 months; benchmark
  proxy IWRD (or an equal-weight composite of the equity ETFs); held fraction
  top 30–50% of the universe.

## Universe fit

Applies to the full 13-ETF universe (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC,
VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA); each asset needs only a price
history plus one benchmark series for the market-model regression. Long-only
and monthly-rebalance compatible. Imperfections: (1) the original study is an
equity single-name cross-section with the full Fama-French factor set — a
13-ETF universe has no clean size/value factors, so the "residual" here is a
simpler market-model residual (benchmark beta only), which is a reasonable but
weaker version of the paper's construction; (2) with a heterogeneous
cross-asset universe (equities, bonds, gold, oil, broad commodities) a single
equity benchmark is a poor market model for the non-equity assets, so residual
momentum may be better applied within the equity sub-universe (VUSA, EQQQ,
IWRD, IMEU, IIND, AIGC) or with an asset-class-aware benchmark; (3) short
formation windows plus monthly rebalancing can generate turnover the repo's
transaction-cost model must capture.
