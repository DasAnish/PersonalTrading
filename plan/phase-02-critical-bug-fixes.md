# Phase 2 — Critical Bug Fixes

**Model**: sonnet

## Goal
Fix the silent-corruption and robustness bugs found in the audit. Every fix ships with a test.

## TODOs
- [x] `data/cache.py:79–90` — fuzzy cache fallback: parse the candidate filename's date range and accept it only if it covers the requested end date (within `max_age_days`); log at WARNING with requested-vs-actual ranges; add `allow_fuzzy: bool = True` parameter so strict callers/tests can disable the fallback entirely
- [x] `data/cache.py:127–133` — atomic cache writes: write to `<name>.parquet.tmp` then `os.replace(tmp, final)`; remove tmp on failure
- [x] `backtesting/engine.py:202–246` — replace bare `except Exception` in the rebalance loop with `except (ValueError, KeyError, np.linalg.LinAlgError)`; log at ERROR with `exc_info=True`; add `failed_rebalances: list` field (default empty) to `BacktestResults` and append the failed date. Apply the same treatment to the silent-skip in `scripts/run_backtest.py` `_run_single_backtest` (~lines 476–480)
- [x] `strategies/minimum_variance.py:66–68` — after computing `cov`: if `np.linalg.cond(cov) > 1e8`, log WARNING and add ridge `1e-6 * np.trace(cov)/n * np.eye(n)`; re-check and escalate the ridge once (×100) if still ill-conditioned
- [x] `strategies/hrp.py:42–96` — `get_quasi_diag`: raise `ValueError("Empty linkage matrix")` on empty/None input; in `HRPStrategy.calculate_weights`, raise `ValueError` if `returns.corr()` contains NaN (degenerate/constant series) before calling `linkage`
- [x] `strategies/momentum.py:69–79` — replace the silent equal-weight fallback with `raise ValueError(f"Insufficient data for momentum: ...")`, matching min-variance/HRP behavior. NOTE in commit message: momentum-family results change on next regeneration
- [x] `backtesting/portfolio_state.py` `execute_rebalance` — validate `prices` and `target_weights` are `pd.Series` at the top; raise `TypeError` with the actual type otherwise
- [x] `scripts/server/api.py` `/api/compare` — reject >10 strategies (HTTP 400) and <2 (already handled); add strategy-key validator `^[A-Za-z0-9_\-]+$` in `scripts/server/data.py` and apply inside `load_strategy_data` (path traversal via `strategy_key` reaches `RESULTS_DIR / "strategies" / strategy_key` at data.py:91 from every route)
- [x] New tests: `tests/test_cache.py` (fuzzy warn/reject, atomic write, no tmp left on success, old file intact on failed write), `tests/test_strategy_guards.py` (momentum raises, min-var near-singular cov gets ridge, HRP empty-linkage raises, portfolio_state type errors), `tests/test_api.py` (Flask test client: traversal key rejected, 11-strategy compare → 400), engine failed-rebalance tracking test

## Validation
- `python -m pytest -m "not slow" -q --ignore=tests/test_connection.py --ignore=tests/test_portfolio.py` → all green including new tests
- Manual: `/api/strategy/..%2F..%2Fetc/overfitting` style key → 400/404 (not a filesystem read)
- `black --check` clean; all touched files ≤600 lines

## Rollback
Single commit `Phase 2: critical bug fixes`.

## Notes
- The momentum change is intentionally behavioral: early rebalance dates with insufficient history are now skipped by the engine (logged) instead of silently equal-weighted.
