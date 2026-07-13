---
name: recommend-allocation
description: Recommend how to allocate capital across validated strategies from current live state — report only, never executes
disable-model-invocation: true
argument-hint: [extra cash £]
---

> **IMPORTANT: NEVER send orders into IB Gateway.** This skill produces a written recommendation and a manual order list ONLY. The user enters every order by hand in IB. Never place, submit, modify, or cancel any trade order programmatically, and never call any IB order tool.

Recommend how to allocate capital across the strategy book, grounded in the
current live state rather than free-form guessing. All the numbers come from a
tested state snapshot — do NOT scrape result files yourself or recompute
metrics in-model.

## 1. Build the state snapshot

Run the gatherer (it writes `results/recommendation_input.json`):

```
python scripts/recommend_allocation.py
```

Then read `results/recommendation_input.json`. It contains:

- `constraints` — account is an **ISA** (no tax constraints), max portfolio
  drawdown tolerance **30%**, phase is **small-real-slice** (size new bets
  conservatively).
- `account_nav` — latest recorded net liquidation + total cash.
- `ledger` — current virtual slices (`strategies`: holdings/cash/slice_value),
  `personal` residual, and `reconciliation` (non-empty = the ledger claims more
  shares than IB holds; flag it, recommend nothing that depends on the bad row).
- `trackers` — watchlist strategies with since-added paper performance.
- `meta_portfolio` — the decorrelated blend (`selected`, `blend`, `blend_dsr`).
- `meta_selection` — the selection-rule meta-backtest; if
  `selection_percentile_vs_random` is low (say < 60), treat top-k selection as
  weak evidence and lean on validation + decorrelation instead.
- `strategies` — per strategy: `sharpe`, `cagr`, `max_drawdown`, `validation`
  (PASS/FAIL), `registration` (ok/breach/review_due/None), `data_end`.

If `scripts/recommend_allocation.py` reports few strategies or a stale
`data_end`, say so and suggest running `python scripts/run_nightly.py` first.

## 2. Reason to a recommendation

Judgement is yours, but respect these rules:

- **Only recommend funding strategies whose `validation` is PASS.** Name FAIL /
  unvalidated ones as watch-only.
- **Never recommend adding to a strategy whose `registration` is `breach`** —
  call it out as a candidate to cut instead.
- **Prefer decorrelation**: favour strategies in `meta_portfolio.selected` /
  with weight in `blend`; avoid stacking capital on strategies driven by the
  same mechanism.
- **Weigh tracker evidence**: a tracked strategy with positive, steady
  since-added performance is stronger evidence than backtest alone.
- **Size for the phase**: small-real-slice means modest per-strategy caps and
  keeping meaningful unallocated cash; the whole book must stay within the 30%
  portfolio drawdown tolerance.
- If an argument is given, treat it as **extra cash (£)** available to deploy.

## 3. Output — a report, not orders

Write a markdown recommendation to stdout (and optionally
`results/recommendation_report.md`) with:

1. **Current split** — personal vs each slice vs unallocated cash (from
   `ledger` + `account_nav`).
2. **Recommendations** — for each suggested change: strategy, rationale
   (validation, decorrelation, tracker/meta evidence), and a target £ size
   respecting the caps above. Include what to trim (breaches, FAILs).
3. **Manual order list** — the concrete buys/sells to enter. For the share-level
   arithmetic of any single strategy, run
   `python scripts/rebalance_report.py --strategy-slice <key> [--budget <£>]`
   and present its table — do not compute share counts in-model.
4. **Reminder** — the user must enter every order manually in IB Gateway, then
   record what they actually filled via the live-risk page's "mark as traded"
   (or it will not appear in the ledger).

End by restating: this is a recommendation only — nothing here places, submits,
modifies, or cancels any order.
