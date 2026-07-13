---
title: Risk-Managed Momentum (volatility-scaled momentum exposure)
source: "Barroso & Santa-Clara (2015), Journal of Financial Economics 116(1), 111–120 — 'Momentum has its moments'"
mechanism: vol-premium
status: rejected
date_added: 2026-07-13
date_built: 2026-07-13
build_note: "Vol-target overlay over top-3 momentum severely underperformed (sharpe=-0.034, dd=-16.1%, return=-1.9%). Overfitting analysis FAIL across all tests (DSR 0.004, kfold 0.4 positive folds). Strategy vulnerable to regime where momentum vol is high without accompanying momentum signals. Long-only constraint prevents leverage-up when vol low, asymmetric versus paper design."
---

## Hypothesis (pre-registered)

Momentum's returns are highly negatively skewed and suffer rare, severe crashes
(e.g. 2009's rebound), and — crucially — the risk of these crashes is
**forecastable from momentum's own recent realized volatility**: momentum
volatility spikes ahead of crashes. Barroso & Santa-Clara show that scaling
momentum exposure by the inverse of its trailing 6-month realized volatility
(targeting constant volatility) nearly doubles the Sharpe ratio (0.53 → 0.97 in
their US-equity sample), removes most of the crash risk, and makes returns far
closer to normally distributed. The economic rationale is that the momentum
premium is compensation for time-varying crash/tail risk; managing the exposure
to hold risk constant harvests the premium while sidestepping the moments when
that risk is highest. This is distinct from the repo's existing momentum ideas
(dual-momentum, 52-week-high, residual, accelerating) which concern the
**selection** signal: this idea is a **volatility-targeting overlay** applied to
whatever momentum book is held — the differentiator is the risk-scaling, not the
ranking. Expected effect: on a long-only 13-ETF adaptation, a Sharpe uplift and
a meaningfully shallower maximum drawdown versus the same momentum selection
held at constant gross exposure — with the caveat that long-only momentum
crashes are milder than the long-short crashes the paper studies, so the uplift
should be smaller (expected standalone Sharpe roughly 0.4–0.7).

## Rule sketch

- **Base book**: any momentum selection (e.g. top-k cross-sectional 12-1
  momentum) producing target weights `w_base`.
- **Overlay signal**: measure the realized volatility of the momentum book's
  returns over a trailing window (paper uses ~6 months of daily returns).
  Scale gross exposure by `target_vol / realized_vol`, capped at fully invested
  (long-only cannot lever, so the scale factor is clipped at 1.0); the freed
  capital when scaling down goes to zero-weight / lower gross exposure (or to
  VUTY if a defensive parking asset is preferred).
- **Rebalance rule**: monthly, matching repo cadence; volatility re-estimated
  each rebalance.
- **Parameters** (plausible ranges, not fitted): vol-estimation window 3–6
  months; `target_vol` chosen to match the book's long-run average vol;
  optional smoothing of the scale factor to limit turnover.

## Universe fit

Applies as an overlay across the full 13-ETF universe (VUSA, EQQQ, IWRD, IMEU,
IIND, AIGC, VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA) — needs only the momentum
book's return series to estimate its volatility. Long-only and monthly
compatible. Imperfect fit: (1) the paper's dramatic Sharpe uplift comes from
taming **long-short** momentum crashes; a long-only book has no short leg and
thus milder crashes, so expect a smaller improvement. (2) Long-only cannot lever
up when momentum vol is low, so the overlay can only ever reduce exposure, not
amplify it — asymmetric versus the paper's constant-vol targeting, which will
lower average invested exposure and drag on absolute return. (3) With no cash
instrument, scaled-down capital must sit at zero weight or be parked in VUTY,
changing the realized risk profile versus the paper's cash-parked design.
