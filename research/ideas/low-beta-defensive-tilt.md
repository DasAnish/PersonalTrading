---
title: Low-Beta Defensive Tilt (long-only Betting-Against-Beta)
source: "Frazzini & Pedersen (2014), Journal of Financial Economics 111(1) 1–25 — 'Betting Against Beta'"
mechanism: vol-premium
status: new
date_added: 2026-07-05
---

## Hypothesis (pre-registered)

Frazzini & Pedersen show that low-beta assets earn higher risk-adjusted
returns than high-beta assets: the security market line is too flat, so
sorting on beta and going long low-beta / short high-beta (their BAB factor,
leverage-adjusted to be market-neutral) produces large positive CAPM alphas —
roughly 6.6% annualized in US equities, and the effect holds across 20 equity
markets and across asset classes (Treasuries, credit, commodities, currencies).
The mechanism is **funding/leverage constraints**: many investors cannot or
will not use leverage, so to chase return they overweight high-beta assets,
bidding their prices up and their expected returns down, while low-beta assets
are left cheap. This is a compensated structural bias, not a data-mined
pattern, and it is the theoretical backbone of the broader low-volatility /
defensive-equity anomaly. This repo cannot run the true BAB construction
(it is long-only, unlevered, monthly, and holds only ~13 ETFs), so the
implementable version is the **long leg only**: a tilt that overweights
low-beta sleeves and underweights high-beta sleeves relative to the world
portfolio. Expectation for that long-only tilt is a **defensive** profile —
similar or modestly lower total return than a cap/equal-weight blend but
meaningfully lower drawdown and volatility, so the value shows up as a Sharpe
and max-drawdown improvement (plausibly 0.1–0.3 Sharpe uplift and a lower
downside) rather than a high standalone Sharpe. The alpha of the pure
market-neutral factor is largely unavailable without shorting and leverage;
what remains long-only is the defensive risk-reduction, not the full 6.6%.

## Rule sketch

- **Signal**: estimate each asset's **beta to the world equity portfolio**
  (IWRD as the market proxy) over a trailing window of daily/weekly returns.
  Beta, not total volatility — this is the distinction from minimum-variance:
  BAB ranks by systematic co-movement with the market, not by full-covariance
  portfolio-variance minimization.
- **Rebalance rule**: monthly. Overweight the lowest-beta assets, underweight
  or zero the highest-beta assets. Long-only, so "short high-beta" becomes
  "hold minimum/zero weight in high-beta."
- **Weighting**: inverse-beta weights (weight ∝ 1/βᵢ, normalized), or a
  simpler bottom-N low-beta equal-weight bucket. Expect the tilt to naturally
  favour VUTY (near-zero/negative equity beta), SGLN, and defensive regional
  equity, and to underweight AIGC, EQQQ, IIND, and the oil sleeve.
- **Parameters** (plausible ranges): beta-estimation lookback (63–252 trading
  days); market proxy (IWRD vs. VUSA); construction (inverse-beta continuous
  vs. bottom-N bucket, N = 4–7); optional shrinkage of beta estimates toward 1
  to reduce estimation noise; single-sleeve cap to prevent full collapse into
  VUTY.

## Universe fit

Beta proxy = IWRD (or VUSA). Naturally low-beta sleeves: VUTY (bonds, ~0 or
negative equity beta), SGLN (gold), and lower-beta regional equity (IMEU).
Naturally high-beta sleeves that get underweighted: AIGC (AI/tech theme),
EQQQ (Nasdaq-100), IIND (India), BRNT/CRUD (oil). What's missing or imperfect:
(1) **no shorting and no leverage** — the true BAB factor is long low-beta,
short high-beta, and *levers the long leg to beta-1*; the long-only tilt keeps
only the defensive half and therefore captures the risk reduction but little
of the market-neutral alpha; (2) **overlap risk with minimum-variance** already
in the library — the two must be kept conceptually and empirically distinct
(min-var optimizes the full covariance matrix to minimize portfolio variance;
this ranks each asset by its single beta to a benchmark), and the idea should
be tested to confirm it is not just a noisier min-var; (3) beta on ~13 broad
ETFs is far coarser than the hundreds-of-stocks cross-section in the source
paper, so the ranking has few distinct buckets and the effect may be dominated
by the bond-vs-equity split rather than a fine beta gradient. This is the
first `vol-premium`/defensive strategy in the library beyond the vol-target
overlays, which target *portfolio* volatility rather than harvesting the
low-beta premium.
