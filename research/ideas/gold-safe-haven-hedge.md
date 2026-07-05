---
title: Gold as a Conditional Safe-Haven Hedge (stress-triggered overlay)
source: Baur & Lucey (2010), The Financial Review — "Is Gold a Hedge or a Safe Haven? An Analysis of Stocks, Bonds and Gold"
mechanism: hedging-overlay
status: new
date_added: 2026-07-05
---

## Hypothesis (pre-registered)

Baur & Lucey distinguish a **hedge** (an asset uncorrelated or negatively
correlated with another asset on average) from a **safe haven** (an asset that
is uncorrelated or negatively correlated with another asset specifically
*during periods of market stress*, regardless of its average-time behaviour).
They find gold is, on average, a hedge against stocks (weak/negative average
correlation), and — more importantly for a tactical overlay — a **safe haven**
against stocks in the days immediately following extreme negative equity
returns, though this safe-haven effect is short-lived (they document it fading
within roughly 15 trading days) and is weaker or absent versus bonds. The
economic mechanism is a flight-to-safety flow: when equity markets suffer
extreme negative shocks, capital rotates into gold as a store of value with no
counterparty/credit risk, temporarily decoupling its returns from the
equity-selloff driver. This motivates an **overlay** (in the sense of this
repo's `OverlayStrategy` pattern) that sits on top of any base allocation and
tilts weight toward gold specifically when a stress condition is detected,
rather than holding a permanent static gold allocation. Because the effect is
a short-lived, event-triggered decoupling rather than a persistent risk
premium, expected Sharpe improvement from the overlay itself is modest — plausibly
a 0.05–0.2 Sharpe uplift and a more material reduction in tail/drawdown risk
versus the un-hedged base strategy, rather than a standalone attractive Sharpe.
Note the original study is about the *stocks vs. gold* relationship in
developed-market (mostly USD) equity indices and spot gold — it does not
itself test a rebalancing rule, so the trigger design below is an extension of
the hypothesis, not something directly measured in the source paper.

## Rule sketch

- **Stress signal**: a rolling drawdown or short-window negative-return
  trigger computed on the equity sleeve (e.g. trailing 20-day drawdown from
  the trailing 6-month high on a market-cap-weighted or equal-weighted blend
  of VUSA/IWRD, or a simpler trailing-5-day return below a negative threshold
  on the same blend). No VIX-like implied-vol instrument is available in this
  universe, so the trigger must be realized-price-based.
- **Overlay rule**: when the stress signal is active, add a tilt of
  `gold_tilt_pp` percentage points to SGLN, funded pro-rata by scaling down the
  equity sleeve's weights; when inactive, hold the base strategy's weights
  unchanged (no permanent standing gold overweight from this overlay).
- **Decay**: because Baur & Lucey find the safe-haven effect fades within
  ~15 trading days, the tilt should decay back toward zero over a bounded
  window (e.g. linearly over 1–2 monthly rebalances) rather than persisting
  indefinitely once triggered.
- **Rebalance rule**: monthly, matching this repo's cadence — note this is
  coarser than the ~15-trading-day effect window documented in the source
  paper, so a monthly-rebalanced version should be expected to capture only a
  fraction of the theoretical benefit; this granularity mismatch is itself
  worth testing explicitly (e.g. does the overlay still help when it can only
  react once a month?).
- **Parameters** (plausible ranges): stress-trigger drawdown threshold
  −8% to −15% from trailing 6-month high; `gold_tilt_pp` 10–25 percentage
  points; decay window 1–3 monthly rebalances.

## Universe fit

SGLN (physical gold) is the direct target asset. The equity sleeve driving the
stress signal maps to VUSA, EQQQ, IWRD, IMEU, IIND, AIGC. Base strategies this
overlay could sit on top of include any existing allocation strategy (HRP,
trend following, momentum, etc.) in `strategy_definitions/allocations/` or
`composed/`. What's missing or imperfect: (1) no implied-volatility instrument
(VIX-equivalent) in the universe, so the stress trigger is a realized-price
proxy rather than a forward-looking stress measure; (2) the source study is in
USD; these are GBP-listed, GBP-traded ETFs, so currency effects (GBP/USD
moves during global risk-off episodes) could either reinforce or dampen the
observed safe-haven effect and should be checked rather than assumed away;
(3) SSLN (silver) is a related but historically less reliable safe haven than
gold per the same literature — could be tested as a secondary/blend target but
is not the primary hypothesis here.
