# tests/

pytest + pytest-asyncio suite. Run with `pytest` from the repo root.

- `conftest.py` — shared fixtures
- IB layer — `test_connection.py`, `test_market_data.py`, `test_portfolio.py`, `test_cache.py`, `test_api.py`
- Strategy/engine — `test_core_architecture.py`, `test_backtest_e2e.py`, `test_engine_failures.py`, `test_rebalance.py`, `test_results_io.py`
- Metrics/validation — `test_metrics_invariants.py`, `test_overfitting.py`, `test_overfitting_ext.py`, `test_cpcv.py`, `test_bootstrap.py`, `test_blend.py`, `test_splitters.py`
- Optimization — `test_optimization.py`
- Pipeline/server — `test_pipeline_scripts.py`, `test_jobs.py`, `test_live_risk.py`, `test_report.py`

```bash
pytest
pytest --cov=strategies --cov=backtesting --cov-report=html
```
