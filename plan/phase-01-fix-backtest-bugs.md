# Phase 1 — Fix Backtest Bugs

## Goal
Fix the two bugs in `_run_single_backtest` that cause equal_weight to report zero returns and trend_following to always match equal_weight weights.

## Root Cause
Both bugs share the same root cause in `scripts/run_backtest.py` `_run_single_backtest`:

- `lookback_days` from `strategy.get_data_requirements()` is in **trading days**
- But `timedelta(days=lookback_days)` treats it as **calendar days**
- For equal_weight: `lookback_days=1` → only 1-2 rows sliced → `len(sliced) < 5` → all rebalances skipped → zero returns
- For trend_following: `lookback_days=509` calendar days → ~351 trading days in window → internal check `len(prices) < 509 trading days` always true → always falls back to equal_weight weights

## TODOs
- [x] In `_run_single_backtest`, convert trading-day lookback to calendar days using `×(365/252)` ratio plus a 14-day buffer
- [x] Enforce a minimum of 60 calendar days so the `len(sliced) < 5` guard never blocks strategies that need minimal lookback (equal_weight)
- [x] Run a quick smoke test confirming equal_weight now transacts: `python -c "from scripts.run_backtest import ..."` style check
- [x] Run existing `tests/test_core_architecture.py` to confirm no regressions

## Notes
