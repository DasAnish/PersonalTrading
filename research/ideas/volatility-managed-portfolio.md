---
title: Volatility-Managed Portfolio
source: Moreira & Muir (2017), Journal of Finance 72(4)
mechanism: vol-premium
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Moreira & Muir show that scaling exposure inversely with recent realized
*variance* raises Sharpe ratios and produces positive alpha across the market,
value, momentum, profitability and betting-against-beta factors and the carry
trade. The mechanism: when volatility spikes, expected returns do not rise
proportionally, so taking less risk in high-vol states and more in calm states
improves the risk/return trade-off. This is distinct from a constant-volatility
target (the repo's VolatilityTargetStrategy overlay scales toward a fixed vol,
i.e. proportional to 1/vol): the vol-managed rule scales proportionally to
1/variance and does not target a constant vol. Expected Sharpe uplift over a
static equal-weight risky sleeve of ~0.1–0.3, with materially lower drawdown in
turbulent regimes. In the long-only, no-leverage version implemented here,
exposure is capped at 1 and the un-invested remainder parks in bonds, so the
effect is a defensive de-risking in high-vol months.

## Rule sketch

- Monthly, estimate realized variance of the equal-weight risky base over a
  lookback (param, ~63 days). exposure = clip(target_vol^2 / realized_var, 0, 1)
  with target_vol a param (annualized, default 0.10).
- Weights = exposure spread equally over the risky assets + (1 - exposure) to
  the safe asset (VUTY). Rebalance monthly.
- Parameters: lookback 21–126 days; target_vol 0.06–0.15.

## Universe fit

Risky base = equity/commodity/gold sleeve; safe asset = VUTY. Long-only,
monthly, price-history only — clean fit. Imperfect: the paper allows leverage
(scaling above 1 in calm periods) which is the source of much of its upside;
the long-only cap at 1 keeps only the de-risking (downside-management) half, so
the realized benefit is more drawdown-reduction than alpha. The single target
variance is a crude stand-in for the paper's factor-specific conditional
variance.
