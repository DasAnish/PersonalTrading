---
title: Low-Volatility Anomaly (The Volatility Effect)
source: "Blitz, D. & van Vliet, P. (2007), Journal of Portfolio Management 34(1) — 'The Volatility Effect: Lower Risk Without Lower Return' (SSRN 980865)"
mechanism: vol-premium
status: validated
date_added: 2026-07-08
date_built: 2026-07-10
build_verdict: WARN
build_note: "Strong Sharpe 3.46, return 9.19%, max drawdown -3.01%. Validation WARN (all tests WARN, no FAIL). Signal is valid but sensitive to vol lookback window. KFold stability moderate. Candidate for parameter sweep."
---

## Hypothesis (pre-registered)

Blitz & van Vliet document that stocks with low past total volatility earn
*higher* risk-adjusted returns than high-volatility stocks — the opposite of
the CAPM prediction — with a global low-minus-high decile alpha spread of about
12% per year over 1986–2006, observed independently in the US, European and
Japanese markets and not explained by size or value. The economic rationale is
a mix of structural and behavioural forces: leverage-constrained investors bid
up high-volatility assets seeking high absolute returns (the same constraint
that drives betting-against-beta), benchmark-relative managers avoid low-vol
names because they generate tracking error, and behavioural biases (lottery
preference, overconfidence in volatile stocks) inflate high-vol prices. Ranking
on *total volatility* (standard deviation of trailing returns) is the key
distinction from the backlog's existing vol-premium idea, Low-Beta Defensive
Tilt (long-only BAB, Frazzini & Pedersen), which ranks on *market beta* and is
framed as a leverage-adjusted long/short; here the signal is total realised
volatility and the implementation is a simple long-only tilt to the
lowest-volatility assets, with no beta estimation or leverage. Expected
standalone Sharpe: roughly 0.4–0.7, delivered mainly through a large reduction
in portfolio volatility and drawdown for equity-like returns, i.e. a higher
Sharpe rather than higher raw return.

## Rule sketch

- **Signal**: for each asset compute trailing total volatility — standard
  deviation of monthly returns over the past 36 months (the paper's window),
  or a shorter 12-month realised vol for responsiveness.
- **Rebalance rule**: monthly, matching this repo's cadence.
- **Portfolio construction**: long-only — rank all assets from lowest to
  highest volatility, overweight the lowest-vol tercile/half and zero-weight
  the highest; weight either equally within the held set or inversely to
  volatility (which biases further toward the lowest-vol names).
- **Parameters** (plausible ranges, not fitted): volatility lookback 12–36
  months; held fraction lowest 30–50% of the universe; weighting scheme
  equal vs inverse-vol.

## Universe fit

Applies to the full 13-ETF universe (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC,
VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA) — needs only a return history per
asset. Long-only and monthly-rebalance compatible with no adaptation.
Imperfections: (1) the original study is a within-equity cross-section; in a
mixed-asset ETF universe a raw total-volatility ranking will mechanically and
persistently favour the structurally low-vol assets — VUTY (hedged
Treasuries) will almost always screen lowest, then broad equity (IWRD) over
single-country/thematic (IIND, AIGC), with oil (BRNT, CRUD) and silver (SSLN)
screening highest — so the strategy risks collapsing into a near-static
bond-heavy allocation rather than harvesting a genuine cross-sectional
low-vol *anomaly*; a within-equity-sleeve application (VUSA, EQQQ, IWRD, IMEU,
IIND, AIGC) is the cleaner test; (2) the low-vol effect is documented at the
single-stock level and may be much weaker across a dozen broad ETFs than
across hundreds of names; (3) inverse-vol weighting overlaps conceptually with
the diversification/risk-parity family already in the backlog, so the
distinguishing feature to preserve is the *tilt/exclusion* of high-vol assets,
not merely vol-scaling of weights.
