# Plan: Fix backtest bugs, migrate YAML→JSON, add e2e tests

**Created**: 2026-03-16
**Status**: In Progress

## Milestones

| # | Phase | Status |
|---|-------|--------|
| 1 | [Fix Backtest Bugs](phase-01-fix-backtest-bugs.md) | ✅ Complete |
| 2 | [Update StrategyLoader for JSON](phase-02-strategy-loader-json.md) | ✅ Complete |
| 3 | [JSON Definitions + Remove YAML](phase-03-json-definitions-and-cleanup.md) | ✅ Complete |
| 4 | [End-to-End Backtest Tests](phase-04-e2e-tests.md) | ✅ Complete |
| 5 | [Update Documentation](phase-05-docs.md) | ✅ Complete |

## All TODOs

### Phase 1 — Fix Backtest Bugs
- [ ] In `_run_single_backtest`, convert trading-day lookback to calendar days using `×(365/252)` ratio plus a 14-day buffer
- [ ] Enforce a minimum of 60 calendar days so the `len(sliced) < 5` guard never blocks strategies with minimal lookback
- [ ] Smoke test confirming equal_weight now transacts
- [ ] Run existing `tests/test_core_architecture.py` to confirm no regressions

### Phase 2 — Update StrategyLoader for JSON
- [ ] Update `_find_strategy_file` to look for `.json` first, handle path-based refs
- [ ] Replace `_load_yaml` with `_load_file` handling both `.json` and `.yaml`
- [ ] Add `_build_strategy_from_def(definition)` recursive builder
- [ ] Update `build_strategy(key)` to use `_build_strategy_from_def`
- [ ] Update `list_strategies(type)` to scan `*.json` files
- [ ] Verify loading works for all existing JSON files

### Phase 3 — JSON Definitions + Remove YAML
- [ ] Create `allocations/hrp_ward.json`
- [ ] Create `allocations/trend_following.json`
- [ ] Create `allocations/minimum_variance.json`
- [ ] Create `allocations/risk_parity.json`
- [ ] Create `allocations/momentum_top2.json`
- [ ] Create `composed/hrp_with_constraints.json`
- [ ] Create `composed/trend_with_vol_12.json`
- [ ] Create `composed/trend_constrained_vol_target.json`
- [ ] Verify loader discovers and builds all new files
- [ ] Delete all `*.yaml` files from `strategy_definitions/`

### Phase 4 — End-to-End Backtest Tests
- [ ] Add `slow` marker to pytest config
- [ ] Write `test_loader_builds_all_json_definitions`
- [ ] Write `make_simulated_prices` helper
- [ ] Write `test_equal_weight_nonzero_returns`
- [ ] Write `test_trend_following_differs_from_equal_weight`
- [ ] Run slow tests to confirm both pass
- [ ] Run normal tests to confirm no regressions

### Phase 5 — Update Documentation
- [ ] Update "YAML Strategy Definitions" → "JSON Strategy Definitions" in `docs/strategies.md`
- [ ] Replace YAML example with JSON example
- [ ] Update file listing to JSON-only structure
- [ ] Remove stale YAML references
