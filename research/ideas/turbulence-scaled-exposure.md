---
title: Financial Turbulence (Mahalanobis) Risk-Scaling Overlay
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1691756
mechanism: hedging-overlay
status: rejected
date_added: 2026-07-10
date_built: 2026-07-10
build_verdict: FAIL
build_note: "Sharpe 2.51, return 7.98%, max drawdown -5.43%. Validation FAIL (DSR FAIL, KFold WARN). Overlay approach valid but fails robustness criteria; Mahalanobis calculation may be unstable on short sample."
---

## Hypothesis (pre-registered)

Kritzman & Li (2010, Financial Analysts Journal 66(5)) define financial
turbulence as the Mahalanobis distance of a cross-asset return vector from its
historical mean/covariance — it spikes when returns are unusually large OR
when correlations break structure. They show risk-asset returns are
substantially lower during turbulent periods, and turbulence is persistent
(clusters), so it is partially forecastable one step ahead. Edge: structural —
turbulence persistence lets an overlay de-risk after turbulence onset and
avoid part of the subsequent poor returns. Distinct from univariate
vol-targeting because it also fires on correlation breakdown at moderate vol.
Expected: overlay cuts max drawdown 20–40% relative to un-overlaid underlying
with roughly flat-to-slightly-lower raw return; Sharpe improvement 0.1–0.3.
Should work on any risk-asset-heavy underlying; strongest on equity/commodity
mixes.

## Rule sketch

- Monthly: compute turbulence d_t = (r_t − μ)' Σ⁻¹ (r_t − μ) over the asset
  (or asset-class) return vector; μ, Σ from a trailing window (36–60 months of
  monthly returns, or daily returns aggregated).
- If d_t above its trailing q-th percentile (q = 75–90), scale underlying risk
  weights by factor s (0.3–0.6), moving the remainder to the safe asset
  (bonds/cash proxy). Below threshold: pass weights through unchanged.
- Optional two-tier scaling (moderate/extreme turbulence).
- Implemented as an OverlayStrategy transforming an underlying's weights.

## Universe fit

Turbulence vector from a representative asset-class set: VUSA (equity), IMEU
(Europe), VUTY (bonds), SGLN (gold), COMM (commodities) — 5-asset vector keeps
Σ invertible on short samples. Underlying: any existing allocation (e.g. HRP,
equal weight). Safe leg: VUTY. Imperfections: no cash instrument, so "risk-off"
means bonds — which fails if bonds sell off with equities (exactly the
turbulent case); short history makes Σ estimation noisy — shrinkage or
asset-class-level vector needed.
