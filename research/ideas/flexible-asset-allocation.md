---
title: Flexible Asset Allocation (Generalized Momentum — return + volatility + correlation)
source: Keller & van Putten (2012), SSRN 2193735
mechanism: momentum-cs
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Generalized momentum harvests three complementary edges at once instead of
relying on trailing return alone. Each asset is scored on (1) relative
momentum (trailing return rank), (2) low volatility, and (3) low average
correlation to the other assets — then the top-ranked subset is held, gated by
an absolute-momentum filter that moves a sleeve to cash/bonds when trailing
return is negative. The return rank captures the well-documented momentum risk
premium / underreaction bias; the volatility and correlation screens tilt the
selected basket toward the diversification and low-volatility anomalies, which
should raise realized Sharpe and cut drawdown relative to a pure
relative-momentum rotation. Because the three signals are only partly
correlated, blending them should be more robust out-of-sample than any single
sleeve. Expected Sharpe 0.6–0.9, meaningfully above a plain top-N momentum
rotation on the same universe, with a shallower max drawdown thanks to the
absolute-momentum cash gate. Edge should show up broadest across the
multi-asset mix (equity regions + bonds + gold + commodities), where the
correlation screen has the most to work with.

## Rule sketch

- Monthly, at each rebalance compute for every asset over a 4-month lookback
  (range ~3–6 months): trailing total return, realized volatility, and average
  pairwise correlation to all other assets.
- Rank each asset on all three (high return, low vol, low correlation). Combine
  into a weighted score `w_R * rank_R + w_V * rank_V + w_C * rank_C` with
  default weights ~1.0 / 0.5 / 0.5 (plausible ranges 0.5–1.5 each).
- Select the top N assets (N ~ 3–5 of the 13).
- Absolute-momentum gate: any selected asset whose trailing return is negative
  is replaced by the defensive asset (VUTY, else cash-equivalent) for that
  month.
- Equal-weight the surviving selections. Rebalance monthly.

## Universe fit

Uses the full 13-ETF universe — VUSA, EQQQ, IWRD, IMEU, IIND, AIGC (equity
regions/themes), VUTY (defensive/absolute-momentum fallback), SGLN, SSLN
(metals), BRNT, CRUD, COMM/WCOA (commodities). All three signals (return,
volatility, correlation) are computable from monthly price history alone, so
the fit is clean and fully long-only with monthly rebalancing. Imperfect: the
paper's universe is broader (includes cash/T-bills as a distinct sleeve); here
the absolute-momentum fallback leans on VUTY as the sole defensive line, so in
a simultaneous stock+bond selloff the gate offers less protection than a true
cash sleeve would. No leverage and no shorting, matching the long-only leg.
