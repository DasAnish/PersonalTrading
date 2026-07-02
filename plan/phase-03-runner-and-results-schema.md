# Phase 3 — Runner Extraction + Unified Results Schema

**Model**: sonnet

## Goal
Split the 1190-line `scripts/run_backtest.py` into library modules and make the on-disk results
contract a single source of truth. This unblocks the report exporter (Phase 5) and the
CPCV/bootstrap/scenario-rerun work (Phases 7–9), which need a programmatic runner.

## Import surface to preserve (verified)
- `tests/test_backtest_e2e.py:17` imports `scripts.run_backtest._run_single_backtest` → update atomically.
- `scripts/run_hrp_backtest.py:31` does `from run_backtest import main` → keep `main` importable.
- `mcp_server/server.py:340` shells out to `scripts/run_backtest.py --all` → CLI flags are an external contract.

## TODOs
- [ ] New `backtesting/runner.py`: move `_run_single_backtest` (run_backtest.py:383) as public `run_single_backtest(strategy, prices, start, end, engine, default_lookback_days=252)` and `_compute_portfolio_values` (:370) as `compute_portfolio_values`; replace the module-global `LOOKBACK_DAYS` with the parameter; module-level imports; full type hints
- [ ] New `backtesting/results_schema.py`: constants `STRATEGY_FILES` (portfolio_history/transactions/weights_history/metrics/info → filenames), `STRESS_TEST_FILE`, `OVERFITTING_FILE`, `INDEX_FILE = "strategies_index.json"`; loaders `strategy_dir(results_dir, key)`, `load_strategy_payload(results_dir, key)`, `load_portfolio_values(results_dir, key) -> pd.Series`
- [ ] New `backtesting/results_io.py`: move `clean_value` + `serialize_backtest_results` (run_backtest.py:285) and ONE `save_strategy_results(result_data, strategy_key, results_dir, stress_report=None, config=None)` that supersedes BOTH the function at :228 and the drifted inline block at :794–872. Semantics = union of the two: writes stress_test.json when report supplied, always writes the config block, index is rebuilt under `--all` and merged otherwise (document in module docstring)
- [ ] New `strategies/catalog.py`: move `get_all_available_strategies` (:169) and `extract_strategy_params` (:145)
- [ ] Rewire `scripts/run_backtest.py` into a thin CLI (~450 lines): arg parsing, IB fetch/cache orchestration, `--all` loop calling runner + results_io, legacy modes; keep `main` and all existing flags
- [ ] Replace hand-rolled result readers with `results_schema` loaders in `scripts/server/data.py:105–111`, `scripts/run_overfitting.py:119–139`, `scripts/run_all_overfitting.py:94–103`
- [ ] New `tests/test_results_io.py`: round-trip (serialize small `BacktestResults` → save with/without stress payload to tmp_path → reload via schema loaders), index merge semantics, config block present; update `tests/test_backtest_e2e.py` import

## Validation
- `python -m pytest -m "not slow" -q` → green vs baseline
- `python scripts/run_backtest.py --all --stress-test` succeeds from parquet cache (no IB); spot-diff 2–3 `results/strategies/<key>/*.json` vs pre-refactor output (momentum family differs — expected, Phase 2)
- Dashboard smoke test: `python scripts/serve_results.py` + load overview and one strategy page
- `wc -l scripts/run_backtest.py` ≤600; new modules ≤600; `black --check` clean

## Rollback
Single commit `Phase 3: runner extraction + results schema`.

## Notes
- The two current save paths differ subtly (index rebuild vs merge; `config` setdefault vs always-write) — the union semantics above are the documented decision.
