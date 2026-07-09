---
title: Volatility / Reward-to-Risk Timing
source: "Kirby & Ostdiek (2012), Journal of Financial and Quantitative Analysis 47(2) 437–467 — 'It's All in the Timing: Simple Active Portfolio Strategies that Outperform Naïve Diversification'"
mechanism: regime
status: rejected
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Kirby & Ostdiek propose two simple dynamic weighting rules — *volatility
timing* (weight each asset inversely proportional to its recent realised
variance) and *reward-to-risk timing* (weight proportional to recent mean
return divided by recent variance, floored at zero for a long-only
implementation) — and show both outperform naive (equal-weight)
diversification on a risk-adjusted basis, and are competitive with or better
than full mean-variance optimisation, while incurring far less turnover and
estimation error than MVO. The regime signal here is purely a *volatility
level*, not a price trend: because realised volatility is strongly
autocorrelated (clustering — a high-vol period tends to be followed by
another high-vol period), scaling exposure down when an asset's recent
variance spikes reduces exposure precisely when tail risk is elevated,
without requiring any view on the direction of price. This is economically
and mechanically distinct from the two `regime` strategies already in this
repo — `AdaptiveAssetAllocationStrategy` and `ProtectiveAssetAllocationStrategy`
— both of which detect regime via price relative to a trailing moving average
(a trend/SMA signal). Kirby & Ostdiek's signal would keep exposure to an
asset that is trending strongly *and* calm, and cut exposure to an asset that
is choppy/volatile regardless of its trend direction — the two regime
families should behave differently in a sideways, choppy market (SMA-based
regime strategies stay roughly neutral; vol-timing actively de-risks) and
should therefore be tested for how differentiated their signals actually are
before assuming both belong in the same meta-ensemble. Expected effect,
adapted to this repo's smaller universe: the source paper's own claim is
modest but consistent risk-adjusted improvement over naive diversification
with low turnover, not a large standalone alpha — a realistic expectation
here is a Sharpe improvement over an equal-weight or static-vol-target
baseline in the region of 0.1–0.3, concentrated in periods where realised
volatility spikes precede drawdowns (e.g. the precious-metals and equity
sleeves).

## Rule sketch

- **Signal (volatility timing)**: weight_i ∝ 1 / σ_i², where σ_i² is trailing
  realised variance (e.g. 21–63 trading days), renormalised to sum to 1.
- **Signal (reward-to-risk timing, alternative)**: weight_i ∝ max(0, μ_i /
  σ_i²), where μ_i is trailing mean return over the same window — this
  variant incorporates a direction view and is closer to a Sharpe-weighted
  allocation; floor at zero to keep the portfolio long-only.
- **Rebalance rule**: monthly, using a deliberately *shorter* volatility
  lookback (1–3 months) than the 12-month SMA used by the existing trend-
  based regime strategies, since the point of this signal is capturing
  short-horizon volatility clustering rather than a slow trend.
- **Parameters** (plausible ranges): vol/return lookback window (21–63
  trading days); choice between pure volatility-timing vs reward-to-risk
  timing; optional blend weight against a static equal-weight or
  vol-target baseline to control turnover.

## Universe fit

Maps onto the full 30-asset universe with no missing instruments — both
variants need only trailing price history, which every asset already has.
One caveat worth flagging explicitly: the source paper's timing signal is
built purely from *realised* (backward-looking) volatility, since this
universe has no VIX-like implied-volatility instrument to use as a forward-
looking regime signal — later literature on volatility timing sometimes uses
implied vol where available, and that variant is not implementable here.
This idea should be evaluated against the existing `VolatilityTargetStrategy`
overlay (which scales a *given* portfolio's overall exposure to a fixed vol
target) — Kirby & Ostdiek's rule instead changes the *relative* weights
between assets based on their individual vol, which is a different
mechanism (cross-sectional re-weighting vs whole-portfolio scaling) and the
two could plausibly be combined (vol-timed weights, then vol-targeted
overlay) rather than treated as substitutes.
