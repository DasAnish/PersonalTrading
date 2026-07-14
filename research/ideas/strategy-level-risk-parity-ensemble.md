---
title: Strategy-Level Risk Parity Ensemble (volatility-weighted meta-portfolio)
source: "Qian, E. (2005), PanAgora Asset Management — 'Risk Parity Portfolios: Efficient Portfolios Through True Diversification' (https://www.panagora.com/assets/PanAgora-Risk-Parity-Portfolios-Efficient-Portfolios-Through-True-Diversification.pdf)"
mechanism: meta
status: validated
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Qian's risk parity insight — that allocating by inverse volatility (so each
position contributes roughly equal risk rather than equal capital) produces a
more efficient, less concentration-prone portfolio than naive equal-capital
weighting — is normally applied *across assets*. The same logic applies one
level up, *across trading strategies*: if a meta-portfolio blends several
sub-strategies with materially different volatilities (e.g. a low-vol
minimum-variance allocation next to a higher-vol momentum allocation), a
naive equal-capital (1/N) blend lets the higher-vol sub-strategy dominate the
combined portfolio's risk budget even though each receives equal weight in
name. Weighting sub-strategies by their trailing inverse volatility instead
should produce a more balanced ensemble where no single sub-strategy's return
stream dominates realized portfolio risk, which is the same diversification
argument that motivates risk parity at the asset level. This repo's existing
`MetaPortfolioStrategy` explicitly implements pure equal-weight (1/N)
blending of sub-strategies (see `strategies/meta_portfolio.py` docstring:
"Each sub-strategy receives equal weight"); this idea is a distinct weighting
rule for the same combination mechanism, not a restatement of what already
exists. Economically the edge here isn't a new risk premium — it's a
construction-quality improvement (better realized diversification across
sub-strategies), so the expected effect is a modest Sharpe uplift versus the
equal-weight meta-portfolio baseline (plausibly +0.05–0.15 Sharpe) and a more
material reduction in the ensemble's volatility clustering around whichever
sub-strategy happens to be running hottest.

## Rule sketch

- **Signal**: for each sub-strategy in the ensemble, compute its trailing
  realized volatility (e.g. annualized std. dev. of monthly returns over a
  12–24 month trailing window) from its own backtested/live equity curve.
- **Weighting rule**: weight each sub-strategy by `1 / trailing_volatility`,
  normalized so weights sum to 1 — the direct strategy-level analogue of
  naive (inverse-vol) risk parity, as opposed to full equal-risk-contribution
  optimization which would additionally require estimating cross-strategy
  correlations.
- **Rebalance rule**: monthly, matching this repo's cadence and re-estimating
  each sub-strategy's trailing volatility at each rebalance.
- **Parameters** (plausible ranges): volatility lookback window 6–24 months;
  optional floor/cap per sub-strategy weight (e.g. 5–50%) to prevent a
  temporarily very-low-vol sub-strategy from dominating the blend; minimum
  number of sub-strategies before the scheme is meaningful (≥3).

## Universe fit

This is a portfolio-of-strategies idea, not an asset-selection idea — it
applies to whichever `strategy_definitions/allocations/` or `composed/`
entries are chosen as the ensemble's members (e.g. HRP, trend following,
momentum, minimum variance), and is agnostic to the underlying 13-ETF
universe as long as each member strategy already trades within it. What's
missing or imperfect: (1) naive inverse-vol weighting ignores correlation
between sub-strategies' return streams — two highly-correlated sub-strategies
would each get weighted as if independent, overstating the diversification
benefit versus a full equal-risk-contribution (covariance-aware) scheme; (2)
trailing volatility is a backward-looking estimate and can lag a
sub-strategy's true current risk regime, the same estimation-lag critique
that applies to asset-level risk parity; (3) this idea should be evaluated
against the existing equal-weight `MetaPortfolioStrategy` as the direct
baseline, since the mechanism (combine sub-strategies into one weight vector)
is identical — only the weighting rule differs.
