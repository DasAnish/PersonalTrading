# Phase 7 — Scenario Removal Completion (Leave-One-Crisis-Out)

**Model**: sonnet

## Goal
Finish the old plan's Phase 2. The core already exists: `StressTester._run_leave_one_out`
(`analytics/stress_testing.py:255–279`) does returns-excision Sharpe deltas and the dashboard
renders them. Missing: public API, Calmar deltas, a true backtest re-run mode, CLI flag, tests.

## TODOs
- [x] Public `StressTester.run_leave_one_out()` wrapping the existing private method; add Calmar to `ScenarioRemovalResult` (`full_calmar`, `loo_calmar`, `calmar_delta`) using `calculate_calmar_ratio` (analytics/metrics.py:354); extend `StressTestReport.to_dict()` keeping ALL existing field names (dashboard reads them) and adding the new ones
- [x] `mode` parameter: `mode="excise"` (current behavior — re-slice the existing portfolio value series; stays the default, backward compatible) vs `mode="rerun"` (drop crisis rows from the *price* data and re-run the backtest via `backtesting.runner.run_single_backtest`; requires strategy + prices + engine arguments)
- [x] `--scenario-removal` CLI flag: on `scripts/run_backtest.py` (has strategy + prices in hand → rerun mode) and on `scripts/run_overfitting.py` (saved histories only → excise mode); results written into `stress_test.json`
- [x] Tests in `tests/test_stress_testing.py`: window-exclusion boundaries (first/last row of crisis), delta math, insufficient-remaining-data skip, rerun-vs-excise divergence on synthetic data where the two must differ
- [x] Update docs (`docs/overfitting.md` or session log) with the two modes and flag

## Validation
- `python -m pytest -m "not slow" -q` → green
- `python scripts/run_backtest.py --strategy <key> --stress-test --scenario-removal` (cache data) produces stress_test.json containing scenario_removal with sharpe + calmar deltas
- Dashboard Stress Periods tab still renders scenario removal (field-name compatibility)
- `black --check` clean; files ≤600 lines

## Rollback
Single commit `Phase 7: scenario removal completion`.
