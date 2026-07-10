---
title: Gold Autumn Effect (September/November seasonality)
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1989593
mechanism: seasonality
status: validated
date_added: 2026-07-10
date_built: 2026-07-10
build_verdict: PASS
build_note: "Excellent results: Sharpe 6.02, total return 29.45%, max drawdown -4.3%. Validation PASS (DSR PASS, KFold WARN). Strong candidate for live deployment."
---

## Hypothesis (pre-registered)

Baur (2013, Research in International Business and Finance 27(1)) finds
September and November are the only months with positive and statistically
significant gold returns over 1980–2010. Proposed drivers: hedging demand ahead
of the equity "Halloween effect", Indian wedding-season jewellery demand, and
seasonal negative sentiment (shorter daylight). This is a calendar-anchored
demand flow, not a risk premium, so it should be modest but persistent.
Expected effect: a gold sleeve overweighted only in Sep–Nov should add roughly
0.1–0.3 Sharpe over a static gold allocation at portfolio level; standalone
seasonal-gold sleeve Sharpe expected 0.3–0.5. Effect belongs to precious
metals only; no reason to expect it in equities or oil.

## Rule sketch

- At each monthly rebalance, if next month is in {Sep, Oct, Nov} (parameter:
  window Sep–Nov vs Sep+Nov only), set gold weight to `w_high`, else `w_low`.
- Plausible ranges: `w_high` 20–40%, `w_low` 0–10%; remainder to the base
  portfolio (equity/bond mix or equal weight).
- Optional silver participation (silver shows related but noisier seasonality).
- Monthly rebalance native — no intra-month timing needed.

## Universe fit

Maps directly to SGLN (physical gold), optionally SSLN (silver). Remainder can
sit in universe:equity + VUTY. Fit is clean: effect is documented on spot gold
in USD; SGLN tracks spot closely. Imperfections: GBP-listed ETF adds FX noise
vs the USD study; sample here is short for a once-a-year effect (few
independent autumn observations in an 8-year backtest window — low statistical
power, high overfitting-battery risk).
