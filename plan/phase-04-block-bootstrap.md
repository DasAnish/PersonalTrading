# Phase 4 — Block Bootstrap

## Goal
Implement stationary block bootstrap (Politis & Romano) to generate N synthetic return histories by resampling contiguous blocks, then evaluate the strategy on each to build a robustness distribution.

## TODOs
- [ ] Implement `analytics/bootstrap.py` with `BlockBootstrap`: generates synthetic price series by resampling random contiguous return blocks of configurable length, reassembles into a price series, runs full backtest
- [ ] Use stationary block bootstrap (geometric block length distribution) to preserve autocorrelation structure of returns
- [ ] Run N bootstrap iterations (default 500) and collect Sharpe, Calmar, max DD, and annualised return for each
- [ ] Add `--method bootstrap` flag to `run_overfitting.py` with `--bootstrap-n` (default 500) and `--block-months` (default 3)
- [ ] Write `tests/test_bootstrap.py`: block lengths are geometrically distributed, synthetic series same length as original, output distribution has correct shape
- [ ] Add bootstrap results to strategy JSON output and dashboard: histogram of bootstrapped Sharpe on the Overfitting tab with a vertical line at the actual realised Sharpe

## Notes
