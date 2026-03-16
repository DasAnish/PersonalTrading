# Phase 4 — End-to-End Backtest Tests

## Goal
Write `tests/test_backtest_e2e.py` with simulated market data to verify the full backtest pipeline works correctly and the two known bugs are permanently caught.

## Test design

### Simulated data
- 1000 business days (~4 years) using `pd.bdate_range`
- VUSA: strong upward trend (`mean=+0.001/day`, σ=0.01) — trend_following should overweight
- SSLN: weak upward trend (`mean=+0.0003/day`, σ=0.01)
- SGLN: downward trend (`mean=-0.0005/day`, σ=0.01) — trend_following should underweight
- IWRD: flat (`mean=+0.0001/day`, σ=0.01)
- Fixed seed for reproducibility

### Tests
1. **`test_equal_weight_nonzero_returns`** — EqualWeight with trending data must:
   - Make at least 1 transaction (proves rebalancing runs)
   - Have `total_return != 0`
   - Have `len(portfolio_history) > 1`

2. **`test_trend_following_differs_from_equal_weight`** — TrendFollowing must:
   - Have weights that differ from EqualWeight by > 1% on at least one rebalance date
   - This catches the fallback-to-equal-weight bug

### Marker
- Decorate with `@pytest.mark.slow` (add to `pytest.ini` / `pyproject.toml`)
- Not run in normal `pytest` pass — only with `pytest -m slow`

## TODOs
- [x] Add `slow` marker registration to `pyproject.toml` or `pytest.ini` (create if needed)
- [x] Write `test_loader_builds_all_json_definitions` — fast test (no `slow` mark) that calls `loader.build_strategy(key)` for every JSON definition stem and asserts no exception is raised
- [x] Write `make_simulated_prices(n_days, seed)` helper function with 4 trending assets
- [x] Write `test_equal_weight_nonzero_returns` test
- [x] Write `test_trend_following_differs_from_equal_weight` test
- [x] Run tests with `pytest tests/test_backtest_e2e.py -m slow -v` to confirm both pass
- [x] Run `pytest tests/ -m "not slow"` to confirm existing tests still pass (4 pre-existing IB mock failures, unrelated)

## Notes
