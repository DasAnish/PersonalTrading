---
title: CPPI Drawdown-Floor Overlay (constant proportion portfolio insurance)
source: Black & Perold (1992), Journal of Economic Dynamics and Control 16(3-4)
mechanism: hedging-overlay
status: validated
date_added: 2026-07-20
---

## Hypothesis (pre-registered)

Black & Perold (1992) formalise constant proportion portfolio insurance:
exposure = multiplier × cushion, where cushion = (NAV − floor)/NAV. With a
ratcheting floor tied to the running NAV peak, the strategy mechanically caps
drawdown near (1 − floor fraction) while keeping full exposure when the cushion
is fat. Economic rationale: not an alpha source — a convexity transform that
buys crash protection with whipsaw cost; it should PRESERVE a good underlying's
Sharpe while hard-limiting tail depth, which is exactly the ISA kill-criterion
profile (30% absolute DD kill; registered strategies use 1.5x backtest DD).
Pre-registered expectation: on a diversified underlying, max drawdown reduced
toward the floor distance (~10–15%) with ≤0.1–0.2 Sharpe give-up from whipsaw;
verdict judged on DD reduction per unit of Sharpe lost vs the 15vol overlays.

## Rule sketch

- Overlay using the underlying's simulated NAV series.
- Floor = ``floor_fraction`` (0.85) × running NAV peak (ratchet: never falls).
- Cushion = max(0, NAV − floor) / NAV; exposure = min(1, ``multiplier`` (3) ×
  cushion); weights scaled by exposure, remainder cash.
- Monthly rebalance with the underlying.

## Universe fit

Instrument-agnostic overlay over any allocation on the UCITS universe;
long-only monthly; only needs the underlying NAV. Doesn't fit: nothing.
Caveat: monthly cadence makes the floor soft (gap risk between rebalances) —
the guarantee is approximate, not hard.
