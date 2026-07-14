---
title: Dynamic Crisis Hedge — fast trend selects the defensive asset
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3383173
mechanism: hedging-overlay
status: validated
date_added: 2026-07-10
---

## Hypothesis (pre-registered)

Harvey, Hoyle, Rattray, Sargaison, Taylor & Van Hemert (2019, Journal of
Portfolio Management 45(5)) evaluate crisis hedges over 1985–2018: puts are
reliable but ruinously expensive; long bonds carry positively but are an
unreliable hedge (negative stock-bond correlation is historically rare); gold
and credit protection sit in between; time-series momentum — especially
faster windows — delivered "crisis alpha" in all major drawdowns at little
long-run cost. Edge: structural — in a crisis, the best defensive asset
varies (bonds in deflationary crashes, gold/commodities in inflationary
ones), and fast trend identifies which is working *during* the event.
Expected: overlay leaves calm-period returns roughly unchanged and improves
crisis-period performance vs the static gold or bond overlays already in this
repo; portfolio-level Sharpe gain 0.1–0.2, max-drawdown reduction 20–35%.

## Rule sketch

- Crisis trigger: equity anchor (broad equity ETF) below its 10-month SMA
  (parameter: 8–12 months) at monthly rebalance.
- Calm state: pass underlying weights through unchanged.
- Crisis state: carve out hedge budget h (20–40%) from risk assets and give it
  to the defensive candidate(s) — bonds, gold, broad commodities — with the
  best fast trend (1–3 month total return, parameter), top-1 or top-2
  inverse-vol weighted. If all candidates trend negative, hedge budget goes to
  the least-bad (or bonds as default).
- Monthly rebalance; overlay form, applied to any underlying allocation.

## Universe fit

Equity anchor: VUSA or IWRD. Defensive candidates: VUTY, SGLN, COMM/WCOA
(SSLN too volatile for a hedge sleeve). Differs from existing
gold_safe_haven_overlay / bond_duration_crisis_hedge_overlay by *selecting
among* defensive assets dynamically rather than fixing one ex ante.
Imperfections: no puts or credit protection instruments (the paper's most
reliable hedges are unavailable); crisis sample in an 8-year backtest is 1–2
episodes — validation power is low and the overfitting battery will likely
WARN on sample size.
