---
title: Long-Term Reversal (Overreaction)
source: "De Bondt & Thaler (1985), The Journal of Finance 40(3) 793–805 — 'Does the Stock Market Overreact?'"
mechanism: mean-reversion
status: rejected
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

De Bondt & Thaler's foundational overreaction study finds that portfolios of
extreme past "losers" (bottom decile by trailing 3–5 year return)
substantially outperform portfolios of extreme past "winners" over the
following 3–5 years — roughly 25% cumulative outperformance over 36 months
in their original US equity sample — and attribute this to systematic
investor overreaction to a sustained run of bad or good news, which then
slowly corrects as fundamentals reassert themselves. This is a **long-horizon**
contrarian effect, and it is economically and empirically distinct from the
`MeanReversionStrategy` already implemented in this repo, which trades a
**short-horizon** (20-day) contrarian signal. The two are not the same effect
measured at different lookbacks: George & Hwang (2004) — see the separate
`52-week-high-momentum` idea in this backlog — explicitly find that
short/medium-term momentum and long-term reversal behave as largely separate
phenomena in the same data, so this idea should be evaluated as a genuinely
different mechanism sharing only the `mean-reversion` tag, not folded into
the existing short-term implementation by just lengthening its lookback
parameter. Expected effect size, adapted to this universe: the original
effect is large but measured on individual stocks, where firm-specific
overreaction and subsequent correction (earnings surprises, analyst
re-rating, distress-and-recovery) is the dominant driver. This project's
universe is entirely diversified index/commodity ETFs, where idiosyncratic,
single-name overreaction is structurally averaged away — so the realistic
expectation is a much weaker effect than the original paper, and it is an
open question whether it survives at the asset-class level at all (index-
level 3-5 year reversal has historically been documented mainly across
*equity markets/countries* and *commodity sectors*, not within a single
broad index) — a standalone Sharpe in the 0.0–0.3 range would not be
surprising, and this idea carries a real risk of showing no exploitable edge
once tested.

## Rule sketch

- **Signal**: trailing total return over a long formation window (36–60
  months), computed per asset; rank ascending (worst trailing performers =
  "losers").
- **Rebalance rule**: hold the bottom_n (or bottom tercile) equal-weighted.
  The source paper's own test rebalances **annually** on formation-period
  return, a much lower turnover cadence than this repo's standard monthly
  rebalance — implementing this idea faithfully means either accepting an
  annual (or similarly infrequent) rebalance schedule for this specific
  strategy, or explicitly testing a monthly-rebalance adaptation as a
  deviation from the source methodology and flagging the mismatch in any
  writeup.
- **Parameters** (plausible ranges, not fitted): formation window (36–60
  months); holding-period rebalance frequency (annual, per source, vs.
  monthly as a repo-consistency deviation); bottom_n or bottom-fraction
  selected as "losers" (e.g. bottom 3–5 of the full universe).

## Universe fit

Technically implementable across the full 30-asset universe (needs only
long price history, which constrains it to assets/funds with a sufficiently
long track record for a 36–60 month formation window). This is the weakest
universe fit of the four ideas added in this scan: the effect's evidence
base is thousands of individual stocks, where genuine firm-specific
mispricing can persist and correct; with only 30 diversified ETFs (each
itself a basket of hundreds of underlying names), most of the idiosyncratic
return dispersion the original effect exploits is already diversified away
at the fund level before this strategy would ever see it. The idea is
recorded here for completeness and because it is a clearly differentiated,
well-sourced `mean-reversion` mechanism relative to the repo's existing
short-horizon implementation — but it should be treated as the
highest-risk-of-no-edge candidate in this batch, not a high-conviction
build candidate.
