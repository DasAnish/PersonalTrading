---
title: National-Market Mean Reversion (Parametric Contrarian)
source: "Balvers, R., Wu, Y. & Gilliland, E. (2000), Journal of Finance 55(2) — 'Mean Reversion across National Stock Markets and Parametric Contrarian Investment Strategies'"
mechanism: mean-reversion
status: validated
date_added: 2026-07-08
---

## Hypothesis (pre-registered)

Balvers, Wu & Gilliland find strong evidence that a country's equity index
price mean-reverts toward a common world benchmark: national indices that have
underperformed the world index tend to subsequently outperform, and vice
versa, with an estimated half-life of reversion of roughly 3–3.5 years. A
"parametric contrarian" strategy that ranks markets by their deviation from
the world index — buying the most beaten-down relative to their long-run
relationship — outperforms both buy-and-hold and naive contrarian strategies,
even after factor and transaction-cost adjustments; the paper notes the
selection is done at monthly frequency across 18 developed markets. The
economic rationale is overreaction at the country/market level: local
sentiment, capital flows and home-bias-driven mispricing push national indices
away from fundamentals, and the correction is slow. This is distinct from the
backlog's existing mean-reversion idea (Long-Term Reversal, De Bondt & Thaler)
because that is single-asset overreaction reversal on individual securities'
own multi-year returns, whereas this is a *cross-sectional relative-value*
reversion of country indices toward a shared world benchmark. Expected
standalone Sharpe: modest, roughly 0.3–0.6 — the slow (multi-year) half-life
means the signal is low-frequency and the standalone return is unspectacular,
but its correlation to trend/momentum strategies should be low or negative,
making its main value diversification within an ensemble.

## Rule sketch

- **Signal**: build a "world" benchmark (IWRD, or an equal-weight composite of
  the equity ETFs). For each country/regional equity ETF compute the log price
  ratio to the benchmark and its deviation from that ratio's trailing long-run
  mean (e.g. z-score of the relative price over a 24–48 month window). A large
  *negative* deviation (country cheap vs world) is a buy signal; large positive
  deviation is underweight/exclude.
- **Rebalance rule**: monthly, matching this repo's cadence (paper selects
  monthly).
- **Portfolio construction**: long-only — overweight the most negatively
  deviated equity ETFs, zero-weight the most positively deviated; weight
  proportional to the (negative) deviation or equal-weight the cheap half.
- **Parameters** (plausible ranges, not fitted): relative-mean lookback 24–48
  months; z-score entry threshold ~0.5–1.5 std; held fraction cheapest 40–60%
  of the equity sub-universe.

## Universe fit

Maps naturally to the equity regional/country ETFs in the universe: VUSA
(US S&P 500), EQQQ (US Nasdaq-100), IMEU (MSCI Europe), IIND (MSCI India),
with IWRD (MSCI World) as the world benchmark and AIGC as an optional
thematic-equity constituent. Long-only and monthly-rebalance compatible.
Imperfections: (1) the paper uses 18 developed national markets; this repo has
only a handful of distinct equity regions (US, Europe, India, plus broad
World), so the cross-section is thin and much of the "US vs world" signal is
really a US-vs-Europe/India tilt; (2) VUSA and EQQQ are both US, so they are
highly collinear and shouldn't both count as independent country bets;
(3) the 3–3.5-year half-life means very slow signal turnover, which is
favourable for costs but demands a long backtest history to estimate reliably;
(4) the non-equity assets (VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA) do not
belong in a country-index mean-reversion signal and should be excluded from
this strategy's investable set.
