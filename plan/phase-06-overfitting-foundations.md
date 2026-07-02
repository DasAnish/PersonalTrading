# Phase 6 — Overfitting Foundations

**Model**: sonnet

## Goal
Cheap, high-value extensions to the overfitting suite (no backtest re-runs needed):
MinBTL, purged k-fold, honest n_trials, walk-forward integration, PBO for composed strategies.
Also restructure `analytics/overfitting.py` (751 lines) under the 600-line rule.

## TODOs
- [ ] Move result dataclasses (`analytics/overfitting.py:46–152`) and `overfitting_analysis_to_dict` (:695–750) to new `analytics/overfitting_results.py`; re-export from `overfitting.py` for backward compatibility (brings it ≤600). The unified JSON stays ONE file (`overfitting_analysis.json`) gaining optional keys: `minbtl`, `walkforward`, `cpcv`, `bootstrap`, `spa` — readers/dashboard must tolerate absence
- [ ] MinBTL (~40 lines, reuses `_expected_max_sharpe` at :154): `min_years ≈ (E[maxSR(N)] / annualized_SR)²` (Bailey & López de Prado); `MinBTLResult(min_years, actual_years, verdict)` — PASS if actual ≥ min; computed inside `run_overfitting_analysis` from n_trials + series length + periods_per_year
- [ ] Purged k-fold: `calculate_kfold_stability(..., embargo_periods: int = 0)` using `splitters.contiguous_folds` + `apply_embargo`; scripts expose `--embargo-days` converted to periods; JSON key stays `"kfold"` with new `embargo_periods` field
- [ ] Fix `build_n_trials_map` (`scripts/run_all_overfitting.py:116–134`): (a) families in `PBO_PARAM_GRIDS` → n_trials = cartesian grid size; (b) otherwise group by the definition `class` field from each strategy's info.json and count real siblings; floor 2. (Current first-token prefix heuristic wrongly lumps trend_following/trend_signal_rp/trend_signal_mvo together)
- [ ] Walk-forward integration: `--walk-forward` flag on `run_all_overfitting.py`; for families in `PBO_PARAM_GRIDS`, run `WalkForwardAnalysis` (reusing grids/prices already loaded for PBO) and write a `walkforward` JSON section — `avg_in_sample`, `avg_out_sample`, `overfitting_ratio`, `n_windows`, verdict PASS<1.5 / WARN<2.5 / FAIL; guard the `avg_out_sample == 0 → inf` case in serialization
- [ ] PBO beyond the 6 base families: `build_family_return_matrix(results_dir, family_keys) -> pd.DataFrame` assembling the (T,N) matrix from existing sibling results' portfolio_history via `results_schema.load_portfolio_values`, grouping composed/overlay strategies by definition class/underlying family; run `calculate_pbo` for groups with N≥4 (fallback `s_subsets=8` with config note when T is short)
- [ ] Dashboard: MinBTL + walk-forward rows and embargo field on the Overfitting tab
- [ ] New `tests/test_overfitting_ext.py`: MinBTL monotonic in N and inversely related to SR², purged k-fold drops exactly the embargo rows, n_trials map on synthetic key sets, family matrix alignment/inner-join behavior

## Validation
- `python -m pytest -m "not slow" -q` → green
- `python scripts/run_all_overfitting.py --strategy <base-family> --walk-forward` writes minbtl + walkforward sections; existing dashboards load older JSONs without error (backward compatible)
- `wc -l analytics/overfitting.py` ≤600; `black --check` clean

## Rollback
Single commit `Phase 6: overfitting foundations`.
