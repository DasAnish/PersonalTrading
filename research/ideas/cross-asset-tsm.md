---
title: Cross-Asset Time-Series Momentum (bond signal scales equity exposure)
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2891434
mechanism: trend
status: built
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Pitkäjärvi, Suominen & Vaittinen ("Cross-asset signals and time series momentum",
JFE 2020; SSRN 2891434) document cross-asset time-series momentum: past 12-month
bond market returns positively predict future equity returns, and past equity
returns negatively predict bond returns. A diversified cross-asset momentum
portfolio earned a ~45% higher Sharpe than pure time-series momentum. Economic
rationale: slow macro information diffusion across asset classes — bond markets
impound discount-rate/growth news before equities reprice, and equity strength
predicts capital rotation out of bonds. Pre-registered expectation on this
universe: Sharpe comparable to or above time_series_momentum_core8 (1.28), with
the bond-confirmation filter cutting equity exposure ahead of tightening-driven
drawdowns (2022-style), so a shallower max drawdown than own-asset TSM alone.

## Rule sketch

- Bond signal: trailing 252d return of bond sleeve (mean of VUTY, AGGU).
- Equity assets: exposure 1.0 if own 252d return > 0 AND bond signal > 0;
  0.5 if exactly one positive; 0 if both negative.
- Bond/defensive assets: exposure 1.0 if own 252d return > 0, else 0.5
  (equity strength predicts bond weakness — halve, don't zero, long-only).
- Weights proportional to exposure / trailing 63d vol, normalised; all-zero
  fallback: defensive equal-weight (VUTY, SGLN).
- Monthly rebalance; universe core_8.

## Universe fit

Implementable directly: bond sleeve (VUTY, AGGU) and equity sleeve (VUSA, EQQQ,
IWRD, etc.) both present with daily closes; long-only monthly. Doesn't fit: the
paper's currency and commodity cross-signals (no FX instruments; commodity
cross-links weaker) — equity-bond pair only, which is the paper's strongest link.
