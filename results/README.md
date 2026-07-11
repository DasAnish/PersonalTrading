# results/

Generated output — backtest results, validation reports, and run archives. **Machine-written; do not hand-edit.**

- `strategies/` — per-strategy folders with backtest series, metrics, and analysis
- `strategies_index.json` — index of all strategies and their headline metrics
- `jobs/` — one folder per dashboard REST job (hashed id), holding that run's status/output
- `spa_analysis.json` — latest SPA go/no-go results
- `mechanism_coverage.json` — mechanism/family coverage across the strategy set
- `meta_portfolio.json` — current meta-portfolio composition
- `run_manifest.json`, `metadata.json` — provenance and data-vintage tracking for the last run
- `cache_validation.json`, `data_refresh.json` — freshness-gate output
- `live_positions.json` — last captured live positions
- `performance_charts.png`, `performance_comparison.csv` — rendered comparison artifacts
- `nightly_console.log` — console log from the last nightly run
