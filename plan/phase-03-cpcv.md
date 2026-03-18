# Phase 3 — CPCV (Combinatorial Purged Cross-Validation)

## Goal
Implement De Prado's Combinatorial Purged Cross-Validation to produce a full distribution of out-of-sample Sharpe ratios, giving a rigorous answer to whether a strategy is genuinely skilled or path-dependent.

## TODOs
- [ ] Implement `analytics/cpcv.py` with `CPCVEngine`: splits time series into k groups, generates all C(k,2) train/test combinations, applies embargo buffer between train and test, runs backtest on each OOS window
- [ ] Compute output statistics: OOS Sharpe distribution (all combinations), median, mean, 5th percentile, probability(OOS Sharpe > 0)
- [ ] Integrate with `BacktestEngine` so CPCV reuses the existing strategy/backtest infrastructure (no data leakage — uses only OOS window data for each fold)
- [ ] Add `--method cpcv` flag to `run_overfitting.py` with configurable `--cpcv-folds` (default 6) and `--embargo-days` (default 10)
- [ ] Write `tests/test_cpcv.py`: correct fold count (C(k,2) combinations), embargo respected, output stats shape, no lookahead
- [ ] Add CPCV results to strategy JSON output and dashboard: histogram of OOS Sharpe distribution alongside existing DSR/PBO scores on the Overfitting tab

## Notes
