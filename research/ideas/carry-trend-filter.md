---
title: Carry Conditioned on Trend (carry-trend interaction)
source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2695101
mechanism: carry
status: rejected
date_added: 2026-07-10
date_built: 2026-07-10
build_verdict: FAIL
build_note: "Negative returns (-4.46%), Sharpe -1.39, validation FAIL (DSR/minBTL/CPCV all fail). Strategy loses money; trend filter did not improve carry performance."
---

## Hypothesis (pre-registered)

Baz, Granger, Harvey, Le Roux & Rattray (2015, SSRN 2695101) dissect carry,
momentum and value in cross-section and time series and find the signals are
lowly correlated and complementary: carry earns a premium but suffers in
risk-off unwinds ("carry crashes"), while trend avoids those same episodes.
Conditioning carry positions on the asset's own trend should keep most of the
carry premium while cutting its left tail — the interaction, not either signal
alone, is the edge. Economically: carry is compensation for crash risk; trend
is a cheap proxy for the crash state, so the filter sheds the state where the
premium realises its risk. Expected: filtered carry Sharpe 0.5–0.8 standalone
(vs unconditional carry ~0.4–0.6 here), with visibly shallower max drawdown.
Applies to the cross-asset carry ranking already in this repo.

## Rule sketch

- Start from the existing ex-ante yield ranking (cross_asset_carry machinery).
- Filter: only allocate to a carry-selected asset if its own 6–12 month total
  return is positive (parameter: lookback 126/189/252 days); assets failing
  the filter route their weight to the safe asset or renormalise across
  survivors (both variants worth trying).
- Top-N selection: N = 2–4. Monthly rebalance.
- No new signal data needed — composition of two existing signal families.

## Universe fit

Same universe as cross_asset_carry (validated): equities, VUTY, SGLN/SSLN,
BRNT/CRUD, COMM/WCOA via ex-ante yield proxies. Fit caveat unchanged from the
carry idea: no true futures-curve carry for commodities, only proxy yields —
so the filter's value-add is tested on proxy carry, not textbook carry.
Long-only monthly native.
