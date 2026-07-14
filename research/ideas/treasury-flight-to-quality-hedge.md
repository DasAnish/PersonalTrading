---
title: Treasury Flight-to-Quality Hedge Overlay
source: "https://www.sciencedirect.com/science/article/abs/pii/S1057521922004173 — 'Stock-bond dependence and flight to/from quality'"
mechanism: hedging-overlay
status: validated
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

The stock-bond return correlation is regime-dependent rather than constant:
it tends to turn negative during demand-shock and flight-to-quality episodes
(equity sell-offs driven by growth scares), when capital rotates from equities
into government bonds and pushes bond prices up as equity prices fall, but
turns positive during inflation-surprise or monetary-tightening shocks (2022
being the canonical recent example), when bonds sell off alongside equities
and offer no protection. This regime-dependence means government bonds are a
*conditional* hedge, not an unconditional one — structurally the same
"hedge vs. safe haven" distinction Baur & Lucey draw for gold (already in
this backlog as `gold-safe-haven-hedge.md`), but the trigger and the
transmission mechanism are different: gold's safe-haven effect is a
monetary/store-of-value flow largely independent of interest-rate direction,
while the Treasury hedge works specifically through the duration/discount-rate
channel and fails precisely when the equity shock's source is rate-driven
rather than growth-driven. This motivates a distinct overlay (in this repo's
`OverlayStrategy` sense) that tilts toward VUTY specifically when the
prevailing shock looks growth/demand-driven (equity drawdown without a
concurrent bond sell-off) rather than a static duration allocation. Because
the effect reverses sign in some regimes, the expected benefit is asymmetric
and regime-conditional: a plausible 0.1–0.2 Sharpe uplift and drawdown
reduction in growth-shock episodes, offset by the overlay being neutral-to-
mildly-negative in inflation-shock episodes — the overlay should not be
expected to help in every equity drawdown, only in the subset with a
flight-to-quality character.

## Rule sketch

- **Regime signal**: classify the prevailing shock type using the *joint*
  behaviour of the equity sleeve and VUTY over a trailing short window (e.g.
  20 trading days) — a flight-to-quality regime is signalled by equities
  falling while VUTY rises or holds flat (negative realized stock-bond
  correlation); an inflation/rate-shock regime is signalled by both equities
  and VUTY falling together (positive realized correlation). No implied-rate
  or inflation-expectations instrument is available in this universe, so the
  classification must be realized-return-based.
- **Overlay rule**: when a flight-to-quality regime is detected, add a tilt
  of `duration_tilt_pp` percentage points to VUTY, funded pro-rata from the
  equity sleeve; when an inflation/rate-shock regime (or no stress) is
  detected, hold the base strategy's weights unchanged — critically, this
  overlay should *not* fire a positive VUTY tilt during positive-correlation
  sell-offs, which is the key difference from a naive "always buy bonds in a
  drawdown" rule.
- **Rebalance rule**: monthly, matching this repo's cadence — note the
  20-day classification window is finer than the monthly rebalance, so the
  regime read at each rebalance date is a point-in-time snapshot rather than
  a continuously-monitored signal, and this granularity mismatch should be
  tested explicitly.
- **Parameters** (plausible ranges): classification window 15–40 trading
  days; `duration_tilt_pp` 10–20 percentage points; correlation threshold for
  regime classification (e.g. rolling correlation < −0.1 vs. > +0.1).

## Universe fit

VUTY (US Treasuries, GBP-hedged) is the direct target asset; the equity
sleeve driving the regime signal maps to VUSA, EQQQ, IWRD, IMEU, IIND, AIGC.
Base strategies this overlay could sit on top of include any existing
allocation strategy in `strategy_definitions/allocations/` or `composed/`,
mirroring how `GoldSafeHavenOverlayStrategy` already wraps other strategies.
What's missing or imperfect: (1) no inflation-expectations or real-yield
instrument in the universe, so the growth-shock-vs-rate-shock classification
is inferred purely from realized stock-bond correlation, a noisy and
backward-looking proxy for the true shock source; (2) only one Treasury
instrument (VUTY) is available, so there is no ability to vary duration
exposure (short vs. long bonds) the way the source literature sometimes does
to isolate the effect; (3) this idea is deliberately distinct from the
existing `regime`-tagged strategies (`AdaptiveAssetAllocationStrategy`,
`ProtectiveAssetAllocationStrategy`), which are full standalone allocation
schemes — this is a narrower *overlay* that tilts an existing base strategy's
weights, matching the `gold-safe-haven-hedge` idea's pattern rather than the
broader regime-switching allocations.
