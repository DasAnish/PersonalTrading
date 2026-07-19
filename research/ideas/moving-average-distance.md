---
title: Moving Average Distance (MAD) cross-sectional tilt
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111334
mechanism: momentum-cs
status: rejected
date_added: 2026-07-19
---

## Hypothesis (pre-registered)

Avramov, Kaplanski & Subrahmanyam (Review of Financial Economics 39(2), 2021):
the ratio of the 21-day to 200-day moving average (MAD) predicts equity returns
in the cross-section — value-weighted hedge alphas ≈9%/yr, predictability beyond
momentum, 52-week high, and profitability, stronger on the long side, and
surviving institutional trading costs. Economic rationale: anchoring — investors
under-react when short-run prices detach from the long-run anchor, so high-MAD
assets continue outperforming. Pre-registered expectation here: long-only top-N
MAD tilt on the equity-heavy universe behaves like momentum_top2 family
(Sharpe ~1.0–1.3) with its own signal timing; the long-side dominance in the
paper is a good fit since we cannot short.

## Rule sketch

- Per asset: MAD = SMA(21d) / SMA(200d).
- Rank cross-sectionally each month; hold top ``top_n`` (3) assets with MAD > 1,
  inverse-vol weighted (63d).
- If fewer than top_n assets have MAD > 1, allocate the shortfall to defensive
  assets (VUTY, SGLN).
- Monthly rebalance; universe core_8 (variant: equity).

## Universe fit

Directly implementable long-only monthly from daily closes. Doesn't fit: the
paper's stock-level breadth (thousands of names) — with 8–17 ETFs the
cross-section is coarse; long-side-only restriction matches the paper's
stronger side.
