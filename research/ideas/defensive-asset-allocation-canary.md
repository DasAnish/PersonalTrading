---
title: Defensive Asset Allocation (Breadth Momentum + Canary Universe)
source: Keller & Keuning (2018), SSRN 3212862
mechanism: regime
status: validated
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

A small "canary" universe acts as an early-warning breadth signal for the whole
portfolio: when the canary assets (a broad EM-equity proxy and an aggregate-bond
proxy) lose positive momentum, market breadth is deteriorating and the strategy
scales into cash/bonds; when the canary is healthy the strategy holds a
relative-momentum-ranked basket of risky assets. The edge is a regime/crash-
protection premium — most of trend-following's benefit comes from avoiding deep
drawdowns, and using a separate canary (rather than the held universe's own
breadth, as PAA does) gives an earlier, less noisy defensive trigger, so the
average cash fraction is roughly halved versus PAA/VAA while keeping similar
crash protection. Expected Sharpe 0.7–1.0 with a materially shallower max
drawdown than a plain relative-momentum rotation, and the defensive benefit
should concentrate around equity bear markets (2000–02, 2008, 2020-style). This
is differentiated from the existing Protective Asset Allocation strategy, which
derives its cash fraction from the count of positive-momentum assets *within the
risky universe itself* rather than from an external canary.

## Rule sketch

- Canary universe: an EM-equity ETF (IIND/SAEM) and an aggregate-bond ETF
  (AGGU), analogues of the paper's VWO/BND. Monthly, compute 13612W-style
  momentum (weighted average of 1/3/6/12-month returns) for each canary asset.
- `b` = number of canary assets with non-positive momentum (0, 1, or 2).
  Cash/bond fraction = `b / 2` (params: canary count and step size).
- Risky fraction `1 - b/2` allocated to the top-N relative-momentum assets from
  the risky universe (N ~ 3–6, lookback via the same 13612W or a 3–12m window).
- The defensive fraction goes to the safe asset (VUTY). Equal-weight the risky
  selections. Rebalance monthly.

## Universe fit

Risky universe = the equity/commodity/gold sleeve (VUSA, EQQQ, IWRD, IMEU, IIND,
SGLN, COMM, BRNT). Canary = IIND/SAEM (EM equity) + AGGU (aggregate bond). Safe
asset = VUTY. Fully long-only, monthly — clean fit; all signals are trailing-
return momentum computable from price history. Imperfect: the paper's canary is
specifically VWO+BND on a US-centric universe; IIND (India) is a narrower EM
proxy than VWO, and AGGU's history may be shorter than the equity sleeve, which
could truncate the usable backtest window.
