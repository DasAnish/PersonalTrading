---
title: Commodity Return Seasonality (calendar-month cross-sectional tilt)
source: "https://www.sciencedirect.com/science/article/abs/pii/S1059056024002934 — 'Return seasonality in commodity futures', International Review of Economics & Finance (2024)"
mechanism: seasonality
status: validated
date_added: 2026-07-13
date_built: 2026-07-13
build_verdict: WARN
build_note: "Base (top-2): Sharpe 0.712, total return 40.16%, max DD -11.76%, validation WARN. Variant (top-3): Sharpe 0.712 (same), return 40.16%, DD -11.76%, validation WARN. No improvement from diversification; concentration risk not significant. Base retained."
---

## Hypothesis (pre-registered)

Individual commodities exhibit persistent calendar-month seasonality in their
returns: a given commodity tends to earn higher (lower) returns in specific
months of the year, driven by structural supply/demand cycles — heating and
driving demand for energy, harvest and inventory cycles, and recurring
hedging-pressure flows from producers and consumers. The paper documents that
sorting commodity futures each month on their historical same-calendar-month
average return produces a significant long-short seasonality premium that is
largely distinct from momentum and carry. The economic rationale is
structural/flow-based (predictable, recurring physical supply-demand imbalances
and hedging pressure) rather than behavioural, which is why it can persist
without being arbitraged away. This is distinct from the repo's existing
seasonality ideas: `halloween-seasonality` and `presidential-election-cycle`
are equity calendar effects, and `gold-autumn-effect` is a single-asset
gold-only September/November pattern — this idea is a **cross-commodity**
monthly-return tilt spanning the metals and energy sleeve. Expected standalone
Sharpe on a long-only adaptation: roughly 0.2–0.5, modest because long-only
forfeits the short leg where much of the documented seasonality premium sits,
and because the commodity sub-universe here is only ~5 assets.

## Rule sketch

- **Signal**: for each commodity, estimate its expected return for the coming
  calendar month from the trailing average return in that same month across
  prior years (e.g. mean of that month's returns over a rolling `history_years`
  window). Rank commodities by this expected seasonal return.
- **Portfolio construction**: overweight the commodities with the highest
  expected seasonal return for the coming month, zero/underweight the lowest
  (long-only: hold top-ranked, drop bottom-ranked). Normalize weights to sum
  to 1 within the commodity sleeve (optionally as an overlay tilt on top of an
  equal-weight commodity allocation).
- **Rebalance rule**: monthly, matching repo cadence — the signal is inherently
  monthly.
- **Parameters** (plausible ranges, not fitted): `history_years` 5–15 for the
  seasonal-mean estimate; number long ∈ {top 1–3 of the commodity sleeve};
  optional shrinkage of the seasonal mean toward zero to fight overfitting.

## Universe fit

Maps to the commodity/precious-metal sleeve of the universe: SGLN (gold), SSLN
(silver), BRNT (Brent), CRUD (WTI), COMM/WCOA (broad commodities). Long-only
and monthly-compatible. Imperfect fit: (1) only ~5 assets carry a genuine
physical-seasonality story, so cross-sectional ranking is thin — with so few
names the long-only top-k selection is coarse. (2) The source works on
commodity **futures**; these ETFs hold spot/physical or roll futures, so the
realized seasonality may be muted or shifted versus the futures study,
especially where roll yield interacts with the seasonal pattern. (3) Estimating
a stable per-month seasonal mean from limited ETF history risks overfitting to
a handful of years — the `history_years` window and a shrinkage prior matter,
and the validation battery's overfitting checks are essential here.
