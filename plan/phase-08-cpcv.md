# Phase 8 — CPCV (Combinatorial Purged Cross-Validation)

**Model**: sonnet

## Goal
De Prado's CPCV: a full distribution of out-of-sample Sharpe ratios telling us whether a
strategy is genuinely skilled or path-dependent. (Closes old plan Phase 3.)

## TODOs
- [ ] New `analytics/cpcv.py` with `CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=10)`: partition trading days into k contiguous groups; generate all C(k,2) test-group pairs; apply purge + embargo around test boundaries via `optimization.splitters`; evaluate each combination with `backtesting.runner.run_single_backtest` restricted to the test windows. Document explicitly: these strategies have no fitting step, so "train" data is simply excluded from evaluation — CPCV here measures path-robustness of OOS performance
- [ ] `CPCVResult`: list of per-combination OOS Sharpes, mean, median, 5th percentile, `prob_oos_sharpe_positive`, verdict thresholds (PASS if P(Sharpe>0) ≥ 0.9 and 5th pct > −0.5; WARN if P ≥ 0.7; else FAIL)
- [ ] Restructure `scripts/run_overfitting.py` CLI: `--method {dsr,cpcv,bootstrap}` dispatch (existing `--param`/`--n-trials` behavior preserved under `dsr`, old flags still accepted); add `--cpcv-folds` (default 6) and `--embargo-days` (default 10)
- [ ] JSON `cpcv` section via `overfitting_results.py`; dashboard: OOS Sharpe histogram on the Overfitting tab (reuse charts.js histogram helper)
- [ ] New `tests/test_cpcv.py`: exactly C(k,2) combinations generated; embargo rows excluded from evaluation; no-lookahead property (mutating data outside the test windows leaves each combination's result unchanged); summary stats shape

## Validation
- `python -m pytest -m "not slow" -q` → green
- `python scripts/run_overfitting.py --strategy hrp_single --method cpcv` writes the cpcv section; dashboard histogram renders
- `black --check` clean; files ≤600 lines

## Rollback
Single commit `Phase 8: CPCV`.
