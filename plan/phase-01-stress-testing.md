# Phase 1 — Stress Testing Framework

## Goal
Implement a crisis-period analysis module that slices backtest history into labelled stress windows and reports how each strategy performed during each crisis.

## TODOs
- [x] Define crisis periods as named constants (2008 GFC, 2011 EU Debt, 2015-16 EM rout, 2020 COVID, 2022 Rate Spike) in `analytics/stress_testing.py`
- [x] Implement `StressTester` class: accepts a backtest result DataFrame and slices it into crisis windows, computing Sharpe, max DD, recovery days, and return for each
- [x] Add `--stress-test` flag to `run_backtest.py` that runs stress analysis after a normal backtest and prints/saves results
- [x] Write `tests/test_stress_testing.py` covering: window slicing, metric computation, edge cases (strategy has no data in window)
- [x] Add "Stress Periods" tab to Flask dashboard strategy detail page with a table of metrics per crisis and a bar chart of returns per period
- [x] Add stress data to the strategy JSON output so the dashboard can load it from results files

## Notes
