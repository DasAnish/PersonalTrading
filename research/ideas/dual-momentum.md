---
title: Dual Momentum (relative + absolute)
source: Antonacci (2014), McGraw-Hill — "Dual Momentum Investing"; Antonacci (2013), SSRN — "Risk Premia Harvesting Through Dual Momentum"
mechanism: momentum-cs
status: built
date_added: 2026-07-05
---

> **Note: this hypothesis is retroactive.** Dual momentum is already implemented
> in this repo as `DualMomentumStrategy` (`strategies/dual_momentum.py`) prior to
> this idea file being written. It is included in the backlog for completeness
> and to anchor the schema with a real example, not as evidence of the
> pre-registration discipline described in `research/README.md` — that
> discipline applies to ideas added from this point forward.

## Hypothesis (pre-registered)

Antonacci's dual momentum combines two well-documented premia: **relative
momentum** (cross-sectional — assets that have recently outperformed tend to
keep outperforming over 3–12 month horizons) and **absolute momentum** (time-
series — an asset's own trailing return sign predicts its near-term trend,
acting as a crude trend/crash filter). The economic rationale offered by
Antonacci is behavioural (under-reaction to information, herding, disposition
effect) combined with a risk-based explanation for absolute momentum (it
correlates with regime — trending markets reward following the trend, and it
sidesteps prolonged drawdowns by moving to cash when an asset's own trailing
return turns negative). Combining both filters is intended to capture the
relative-momentum premium while avoiding relative momentum's worst drawdowns
(picking the "best of a bad bunch" during a broad selloff). Antonacci reports
Sharpe ratios in the 0.7–1.0 range and roughly halved max drawdown versus
buy-and-hold equities, on US equities/bonds/REITs/gold over 1974–2013.
Applied to a smaller, higher-vol multi-asset-class universe like this one, a
more realistic expectation is Sharpe 0.4–0.7, with the main value proposition
being drawdown mitigation rather than raw Sharpe uplift.

## Rule sketch

- **Signal**: trailing total return over a lookback window (default 252
  trading days ≈ 12 months) per asset.
- **Relative momentum**: rank all risky assets by trailing return; select the
  top N (default `top_n=2`).
- **Absolute momentum**: for each selected asset, check whether its own
  trailing return is above a threshold (default `abs_threshold=0.0`, i.e. any
  positive return passes). If not, that allocation is held as cash
  (zero-weight) rather than redistributed, unless `cash_redistribute=True`.
- **Rebalance rule**: monthly, matching this repo's cadence.
- **Parameters** (plausible ranges): `top_n` 1–3; `lookback_days` 126–252 (6–12
  months); `abs_threshold` 0.0 to a small positive buffer (e.g. 0.02) to avoid
  whipsaw around zero.

## Universe fit

Implemented in this repo across multiple universes — see
`strategy_definitions/composed/dual_momentum_15vol.json`,
`dual_momentum_30vol.json`, `dual_momentum_full_universe_15vol.json`,
`dual_momentum_full_universe_30vol.json`, and `dual_momentum_invested_15vol.json`.
The classic 4-asset implementation uses VUSA, SSLN, SGLN, IWRD; the
full-universe variants extend relative-momentum ranking across all 13 ETFs
(equities, gold/silver, oil, broad commodities, bonds). Nothing structural is
missing — the strategy maps cleanly onto this long-only, monthly-rebalanced
universe, which is close to Antonacci's original design intent (a small set of
liquid, low-cost, long-only building blocks).
