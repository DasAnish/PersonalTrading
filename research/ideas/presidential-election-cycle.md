---
title: Presidential Election Cycle Seasonality
source: "Herbst, A.F. & Slinkman, C.W. (1984), Financial Analysts Journal 40(2), 38-44 — 'Political-Economic Cycles in the U.S. Stock Market'"
mechanism: seasonality
status: candidate
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Herbst & Slinkman analyze month-end US stock prices from 1926 to 1977 and
document both 4-year and 2-year cycles tied to the US presidential election
calendar: the 4-year cycle peaks around November of election years, and a
shorter 2-year cycle peaks on average around the ninth month following an
election. Later popularizations (the "Stock Trader's Almanac" pattern) refine
this into a claim that the first year of a presidential term tends to show
the weakest equity returns, improving through the second and (especially)
third year, with the fourth (election) year mixed. The proposed economic
mechanism is political — incumbent administrations have a documented
incentive to front-load unpopular fiscal tightening early in a term and
loosen policy (spending, rate-friendly appointments) ahead of the next
election, producing a policy-driven, not purely random, cycle in growth
expectations and equity risk premia. This is a genuinely disputed effect —
critics attribute the pattern to a small sample of cycles (roughly 12-15
non-overlapping 4-year periods since 1926) and note it may be confounded with
business-cycle and monetary-policy timing rather than being a distinct
seasonal effect — so the pre-registered expectation here is deliberately
modest and skeptical: a plausible 0.1–0.3 Sharpe tilt if real, with a
material chance the effect fails to replicate out of the original 1926-1977
US sample, similar in spirit to how the Halloween seasonality idea in this
backlog was tested and rejected. Unlike day-of-month or month-of-year
seasonal effects, this cycle operates on a 4-year (48-month) periodicity,
which is naturally compatible with monthly rebalancing — no intra-month
timing precision is required.

## Rule sketch

- **Signal**: classify each month into one of four "cycle years" based on
  months elapsed since the most recent US presidential inauguration
  (year 1 = weakest expected regime, year 3 = strongest per the popularized
  pattern, year 4/election year = mixed). This is a deterministic calendar
  signal, not derived from price data.
- **Rebalance rule**: monthly — tilt the equity sleeve (VUSA, EQQQ, IWRD,
  IMEU, IIND, AIGC) up in the historically favourable cycle years (2 and 3)
  and down toward defensive assets (VUTY, SGLN) in the historically weak
  cycle year (1), holding a neutral/base allocation in the election year
  (year 4) given the source literature's mixed findings there.
- **Parameters** (plausible ranges, not fitted): magnitude of the equity tilt
  by cycle year (e.g. ±10-20 percentage points vs. a neutral baseline);
  whether to treat year 4 as neutral or apply a smaller directional tilt;
  whether the cycle is defined from US inauguration dates specifically (this
  is a US-political-calendar effect being tested on non-US-only ETFs).

## Universe fit

The calendar signal itself needs no market data and applies economy-wide;
the tilt trades across the existing equity sleeve (VUSA, EQQQ, IWRD, IMEU,
IIND, AIGC) versus the defensive sleeve (VUTY, SGLN). What's missing or
imperfect: (1) the source study is US-centric (US elections, US equity
prices, 1926-1977 sample) — this repo's universe is broader than US equities
(IIND India, IMEU Europe, AIGC thematic), so the transmission mechanism
(US fiscal/monetary policy cycle) is weaker and less direct for the non-US
sleeves, and the tilt may need to be scoped to VUSA/EQQQ only rather than
applied universe-wide; (2) with only ~12-15 non-overlapping cycles in the
historical record, statistical power is inherently low and this is one of
the weaker-evidence ideas in the backlog — closer in credibility to the
already-rejected Halloween seasonality idea than to the validated carry or
low-beta ideas; (3) no commodity- or bond-specific presidential-cycle
literature was found, so the defensive-leg tilt (VUTY, SGLN) is this idea's
own extension rather than something directly tested in the source paper.
