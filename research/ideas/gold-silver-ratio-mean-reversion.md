---
title: Gold–Silver Ratio Mean Reversion (long-only metals tilt)
source: Escribano & Granger (1998), Journal of Forecasting 17(2)
mechanism: mean-reversion
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

Gold and silver prices are cointegrated — they share a long-run equilibrium
relationship, so the gold/silver price ratio is mean-reverting even though each
metal individually trends. When the ratio is stretched high (silver cheap
relative to gold) it tends to fall back; when stretched low (silver expensive)
it tends to rise. A long-only tilt harvests this by shifting weight between the
two physical-metal ETFs based on the ratio's deviation from its trailing mean:
overweight silver when the ratio is high, overweight gold when low. The edge is
a statistical mean-reversion premium in the *relationship*, not a directional
metals bet — a uniform move in both metals cancels out. Expected Sharpe modest,
0.3–0.6, because the effect is strongest only at extremes and the long-only
constraint (cannot short the expensive leg) captures only half the convergence.
Low correlation to equities makes even a modest-Sharpe sleeve a useful
diversifier. Effect confined to the precious-metals pair.

## Rule sketch

- Monthly, compute ratio = price(SGLN) / price(SSLN) and its trailing z-score
  over a lookback (param, default ~250 trading days; range 120–500).
- Map z-score to a gold/silver weight split: high ratio (silver cheap, z > 0)
  tilts weight toward SSLN; low ratio (z < 0) tilts toward SGLN. E.g.
  `w_silver = clip(0.5 + k * z, w_min, w_max)`, `w_gold = 1 - w_silver`, with
  gain `k` and floor/cap params (default band ~20/80).
- Optionally hold only the two metals; or embed as a metals sleeve inside a
  broader portfolio. Rebalance monthly.

## Universe fit

Maps cleanly to exactly two assets: SGLN (physical gold) and SSLN (physical
silver) — both in the universe with long history. Long-only, monthly, two-asset
weight split — a precise fit for the long-only version of the ratio trade.
Imperfect: the textbook trade is market-neutral long/short (long the cheap
metal, short the expensive one); long-only can only *tilt*, not short, so it
keeps directional metals exposure and captures a fraction of the pure
convergence premium. No third metal to diversify the pair.
