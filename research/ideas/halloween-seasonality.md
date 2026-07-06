---
title: Halloween Indicator ("Sell in May") seasonal rotation
source: "Bouman & Jacobsen (2002), American Economic Review — 'The Halloween Indicator, Sell in May and Go Away: Another Puzzle'"
mechanism: seasonality
status: rejected
date_added: 2026-07-05
---

## Hypothesis (pre-registered)

Bouman & Jacobsen document that average equity returns in the November–April
("winter") half of the year are significantly higher than in the May–October
("summer") half, a pattern they find in 36 of 37 countries studied over long
samples (some back to the 1800s), with the effect notably strong and
persistent in European markets. No fully settled economic explanation exists
— proposed mechanisms include institutional trading patterns (e.g. reduced
summer trading activity and risk appetite, "Sell in May" as a self-fulfilling
convention), lower realized summer liquidity, and vacation-related
risk-aversion effects — meaning this is best treated as a persistent
behavioural/institutional-flow anomaly rather than a compensated risk premium.
Because it is a well-known, widely tested calendar effect rather than a subtle
statistical artifact, and because publication has plausibly caused some
arbitrage-driven decay since 2002, a realistic expectation for a simple
long-only rotation strategy built on it today is a modest Sharpe improvement
over a static buy-and-hold equity/bond blend — plausibly 0.1–0.3 Sharpe
uplift from the rotation, not a standalone high-Sharpe strategy. The edge, if
any survives, should show up primarily as a difference in the *distribution*
of returns between the two halves of the year (higher winter Sharpe, weaker
or flat summer Sharpe) rather than as a large absolute return spread today.

## Rule sketch

- **Signal**: pure calendar signal — no price data required. "Winter" =
  November through April inclusive; "summer" = May through October inclusive.
- **Rebalance rule**: monthly, matching this repo's cadence — the rotation
  only actually changes composition at the two seasonal boundary months
  (end-October → November, end-April → May); other monthly rebalances within
  a season just re-confirm the existing sleeve weights (naturally low
  turnover, at most 2 sleeve-switching transitions per year).
- **Winter allocation**: full weight (or a large majority, e.g. 70–100%) to
  the equity sleeve (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC — equal-weighted, or
  reusing an existing core allocation like HRP or momentum-top-N as the
  "risk-on" sleeve rather than reinventing equity weighting).
- **Summer allocation**: rotate the equity-sleeve weight (fully or partially)
  into a defensive sleeve — VUTY (bonds) alone, or a VUTY/SGLN blend, since
  the universe has no pure cash/T-bill instrument.
- **Parameters** (plausible ranges): winter/summer month boundaries could be
  tested at the classic Nov 1–Apr 30 split vs. slightly shifted variants
  (e.g. Oct 15–Apr 15, as some replications use); rotation intensity 50–100%
  (partial tilt vs. full binary switch); defensive-sleeve composition
  (100% VUTY vs. VUTY/SGLN blend, e.g. 70/30).

## Universe fit

Equity sleeve maps to VUSA, EQQQ, IWRD, IMEU, IIND, AIGC. Defensive sleeve
maps to VUTY (GBP-hedged US Treasuries) and optionally SGLN (gold) as a
partial diversifier during the "off" season. What's missing: (1) the original
study benchmarks local-currency equity indices generally, not this specific
mixed thematic/regional ETF set, so the effect's strength on, e.g., AIGC
(AI/tech theme) or IIND (India) individually is an extrapolation rather than
something directly tested in the source paper; (2) no pure cash/money-market
instrument exists in the universe, so the "defensive" sleeve carries VUTY's
duration/rate risk instead of being risk-free, which dampens the theoretical
benefit of moving out of equities in the weak season; (3) this is a
calendar-only signal with zero adaptivity to prevailing market conditions, so
it should be evaluated against, not blended, with existing trend/momentum
strategies that already occupy similar defensive-rotation territory (Trend
Following, Protective Asset Allocation) to see whether the calendar signal
adds information beyond what those already capture.
