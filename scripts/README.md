# scripts/

Command-line entry points. See [../docs/cli.md](../docs/cli.md) for full flags.

## Backtesting & analysis
- `run_backtest.py` — main backtest entry (4 modes: single, all, YAML definitions, composed)
- `run_full_analysis.py` — **canonical** validation + overfitting run for a strategy
- `run_overfitting.py` / `run_all_overfitting.py` — DSR / PBO / k-fold / SPA
- `run_optimization.py` — parameter sweep & walk-forward
- `recompute_metrics.py` — recompute metrics on existing results (e.g. after a metrics fix)

## Pipeline & data
- `run_nightly.py` — nightly pipeline: freshness gate → refresh → backtest → analysis → archive
- `full_run.py` — full end-to-end run
- `refresh_data.py` / `validate_cache.py` — pull fresh IB data / verify the parquet cache
- `extend_history.py` — splice proxy history onto short series
- `rebuild_index.py` — rebuild `results/strategies_index.json`

## Strategy tooling
- `build_meta_portfolio.py` — assemble a meta-portfolio from component strategies
- `add_strategy_tags.py` / `tag_mechanisms.py` — attach taxonomy/mechanism tags

## Live / reporting
- `rebalance_report.py` — generate a manual-rebalance recommendation report
- `generate_report.py` — analysis reports
- `snapshot_nav.py` / `snapshot_positions.py` — capture live NAV/positions into `live_tracking/`
- `serve_results.py` — start the dashboard server
- `start_dashboard.bat` / `start_dashboard.sh` — dashboard launch helpers

## Subpackages
- `server/` — Flask dashboard: routes, REST run/job API (`api.py`, `jobs.py`), risk view, templates + static
- `backtest_lib/` — shared library (CLI parsing, config, data fetch, run-all) used by the entry scripts
