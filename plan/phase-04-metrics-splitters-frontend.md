# Phase 4 — Metrics Dedup, Splitters, Frontend Modules

**Model**: sonnet

## Goal
Remove metric duplication from the web layer, extract shared time-series splitting utilities
(needed by Phases 6 and 8), and modularize the dashboard's inline JavaScript.

## TODOs
- [ ] Delete `_compute_cagr` / `_compute_omega_ratio` from `scripts/server/api.py:14–43` — they duplicate `analytics/metrics.py` `calculate_cagr` (:186) and `calculate_omega_ratio` (:229); call the analytics functions from the endpoints instead
- [ ] Add `history_to_series(portfolio_history: list) -> pd.Series` helper in `scripts/server/data.py`; replace the 5 copy-pasted list→Series conversions in api.py (lines ~138, 169, 306, 375, 381)
- [ ] Split `analytics/metrics.py` (684 lines): move lines 521–684 (`calculate_monthly_returns`, `calculate_rolling_metric`, `generate_metrics_summary`, `calculate_return_attribution`) to new `analytics/summary.py`; re-export via `analytics/__init__.py` so existing importers (run_backtest.py:39, scripts/test_hrp_backtest.py:21) keep working
- [ ] New `optimization/splitters.py`: `contiguous_folds(t, n_folds) -> list[tuple[int, int]]` (extracted from `analytics/overfitting.py:511–530`), `rolling_windows(n_days, in_sample, out_sample, step)` (extracted from `optimization/walk_forward.py:147–159`), and new `apply_embargo(train_idx, test_idx, embargo)` + `purge(train_idx, test_idx, horizon)` for Phases 6/8; refactor `walk_forward.py` and `calculate_kfold_stability` to consume them
- [ ] New `scripts/server/static/js/`: `api.js` (fetch + error handling), `format.js` (pct/number/verdict-badge helpers), `charts.js` (chart wrappers incl. a reusable histogram helper for CPCV/bootstrap later), `tabs.js` (tab switching + lazy loaders); slim `templates/strategy.html` (1297 lines) and `overview.html` (498) down to page-specific glue
- [ ] Splitter unit tests in `tests/test_optimization.py` (or new file): exact fold boundaries, residual-discard behavior preserved vs old implementations, embargo/purge row exclusion

## Validation
- `python -m pytest -m "not slow" -q` → green vs baseline; k-fold and walk-forward results numerically identical to pre-refactor on a fixed seed/fixture
- `wc -l analytics/metrics.py` ≤600
- Dashboard manual pass: every tab on overview + strategy pages renders, charts draw, CSV export works
- `black --check` clean

## Rollback
Single commit `Phase 4: metrics dedup, splitters, frontend modules`.
