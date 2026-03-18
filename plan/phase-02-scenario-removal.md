# Phase 2 — Scenario Removal (Leave-One-Crisis-Out)

## Goal
Systematically exclude each crisis period from the backtest and re-evaluate strategy performance, revealing how much of a strategy's Sharpe comes from any single crisis event.

## TODOs
- [ ] Implement `run_leave_one_out()` in `analytics/stress_testing.py`: for each crisis window, re-run the full backtest on the history minus that window and return the resulting Sharpe and Calmar
- [ ] Compute "Sharpe contribution" per crisis: delta between full-history Sharpe and leave-one-out Sharpe; large positive delta means strategy depends heavily on that crisis
- [ ] Add `--scenario-removal` CLI flag to `run_backtest.py` (or `run_overfitting.py`)
- [ ] Write tests for scenario removal: correct window exclusion, correct delta computation, handles strategies with insufficient remaining data
- [ ] Add "Scenario Removal" sub-section to the Stress Periods dashboard tab: bar chart of Sharpe delta per removed crisis, with colour coding (red = strategy relied heavily on that event)

## Notes
