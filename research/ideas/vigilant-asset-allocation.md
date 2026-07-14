---
title: Vigilant Asset Allocation (VAA — offensive-breadth binary crash gate)
source: Keller & Keuning (2017), SSRN 3002624
mechanism: regime
status: rejected
date_added: 2026-07-14
---

## Hypothesis (pre-registered)

VAA is an aggressive dual-momentum rotation with a binary, all-or-nothing crash
switch driven by the breadth of the *offensive* universe itself (not a separate
canary as in DAA). In healthy markets it concentrates hard into the top few
13612W-momentum offensive assets; the instant ANY offensive asset shows negative
momentum, it retreats fully into the best defensive asset. The edge is the same
crash-protection/trend premium as PAA/DAA, but the very sensitive trip-wire
(one bad asset triggers full defense) trades some upside capture for a shallower
drawdown profile. Expected Sharpe 0.7–1.0 with max drawdown materially below a
plain relative-momentum rotation, at the cost of being out of the risky market a
large fraction of the time (the paper notes VAA is often >50% defensive).
Distinct from the already-built PAA (fractional cash from count of positive-
momentum assets) and DAA (external canary universe): VAA's gate is binary and
keyed to the offensive universe's own breadth. Benefit concentrates around
equity bear markets.

## Rule sketch

- Offensive universe: equity/gold/commodity sleeve. Defensive universe: bonds
  (VUTY, AGGU). Monthly, compute 13612W momentum (weighted avg of 1/3/6/12-month
  returns, weights 12/4/2/1; ~21/63/126/252 trading days) for all assets.
- Breadth gate: count offensive assets with 13612W momentum <= 0. If count == 0
  (all positive), hold the top-N offensive assets by momentum (N ~ 1–3, param),
  equal-weighted. If count >= 1, hold 100% of the single best-momentum defensive
  asset. (Params: breadth threshold, top_n; the classic G4 uses threshold 1 and
  top 1.)
- Rebalance monthly.

## Universe fit

Offensive = VUSA, EQQQ, IWRD, IMEU, IIND, SGLN, COMM, BRNT. Defensive = VUTY,
AGGU. Fully long-only, monthly — clean fit; all signals are trailing-return
momentum from price history. Imperfect: VAA's binary trip-wire is very sensitive
to universe size — a larger offensive universe makes "all positive" rare, so the
strategy may sit in bonds excessively on this 8-asset offensive set; the top_n
and breadth threshold may need to be looser here than the paper's small-universe
G4 defaults.
