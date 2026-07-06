---
title: Cross-Asset Carry (ex-ante yield ranking)
source: "Koijen, Moskowitz, Pedersen & Vrugt (2018), Journal of Financial Economics 127(2) 197–225 — 'Carry'"
mechanism: carry
status: validated
date_added: 2026-07-05
---

## Hypothesis (pre-registered)

Koijen, Moskowitz, Pedersen & Vrugt define an asset's *carry* as its
model-free, ex-ante expected return assuming prices do not change — the return
you earn just from holding the position. They decompose any security's
expected return into carry plus expected price appreciation, and show carry
predicts returns both cross-sectionally and in time series across a wide set
of asset classes (global equities, global bonds, commodities, US Treasuries,
credit, currencies, options). A portfolio that overweights high-carry assets
and underweights low-carry assets earns a positive premium in every class they
test, and this premium is not subsumed by known predictors — carry is a
unifying characteristic rather than an asset-class-specific quirk. The economic
rationale is a mix of a risk premium (high-carry assets tend to load on global
downside/liquidity risk and lose in "carry unwinds") and a
structural/expectational bias (investors underreact to the information in
current yields). Because this repo is **long-only, monthly, and holds ETFs
rather than futures**, only the long leg of the effect and a coarse ex-ante
carry proxy are available, so the realistic expectation is a modest premium —
plausibly a 0.3–0.6 Sharpe standalone on the tilt, most of it coming from the
bond/equity carry ranking rather than the commodity sleeve where the ETF
structure hides the true roll carry. The edge should show up as high-carry
sleeves (bonds when the curve is steep, high-dividend equity regions)
outperforming low- or negative-carry sleeves (gold/silver, which have negative
carry from storage and no yield) over holding periods, net of the price moves
that carry does not predict perfectly.

## Rule sketch

- **Signal**: compute an ex-ante carry proxy per asset each month, using only
  currently-observable yields — no return forecasting:
  - **VUTY (US Treasuries)**: carry ≈ current yield-to-maturity minus the
    short rate (roll-down of the curve); when unavailable, proxy by the
    trailing distribution yield of the ETF.
  - **Equity ETFs (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC)**: carry ≈ trailing
    12-month dividend/distribution yield (optionally plus a slow earnings-yield
    term); this is the "hold and collect dividends" return if price is flat.
  - **Commodity ETFs (SGLN, SSLN, BRNT, CRUD, COMM, WCOA)**: carry is the roll
    yield of the underlying futures. Gold/silver ≈ small negative carry
    (storage, no coupon); oil/broad-commodity carry flips sign with
    contango/backwardation. Proxy the sign from the futures term structure if
    a data feed is available, else assign a conservative small-negative prior
    and flag the asset as low-confidence.
- **Rebalance rule**: monthly. Rank all assets by carry proxy; overweight the
  top-carry group, underweight/zero the bottom group. Long-only, so the
  "short" leg is simply zero or minimum weight rather than a negative position.
- **Parameters** (plausible ranges): number of top-carry assets held (top-3 to
  top-6 of 13); weighting within the held set (equal vs. carry-proportional);
  dividend-yield lookback (trailing 12m vs. forward estimate); optional cap on
  any single sleeve (e.g. ≤40%) to stop the tilt collapsing entirely into
  bonds when the curve is steep.

## Universe fit

Maps cleanly to VUTY (bond carry = the strongest, cleanest signal here) and
the equity sleeve (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC via dividend yield).
SGLN/SSLN naturally rank low (negative carry), which is economically correct
and gives the ranking something to underweight. What's missing or imperfect:
(1) **no live futures curve** — the true carry of BRNT, CRUD, COMM, WCOA is
their roll yield, which an ETF price series does not expose; without a term-
structure feed these assets can only be given a crude prior, so the commodity
portion of the signal is the weakest link and should be tested with and
without those assets included; (2) the source paper's headline results use
**futures and the long-short spread**; a long-only ETF tilt captures only part
of the premium and inherits directional market exposure the original
market-neutral construction hedged away; (3) dividend-yield-as-equity-carry
ignores buyback yield and expected earnings growth, so cross-region equity
carry comparisons (e.g. IIND vs. VUSA) are noisier than the bond signal. This
idea is distinct from the existing `diversification` strategies (HRP, risk
parity, min-var) — those weight by *risk/covariance*, whereas carry weights by
*ex-ante yield*, an orthogonal characteristic — and should be evaluated as a
standalone `carry` sleeve, the first in the library.
