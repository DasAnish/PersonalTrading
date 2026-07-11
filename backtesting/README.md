# backtesting/

The simulation engine that runs a strategy over historical prices and produces a return series.

- `engine.py` — core backtest loop: monthly rebalancing, 7.5 bps transaction costs, position sizing (`Units = NAV × Weight / Price`)
- `runner.py` — higher-level driver that wires a strategy + data + config into an engine run
- `portfolio_state.py` — tracks holdings, cash, and NAV through time
- `transaction.py` — trade/cost modelling
- `results_schema.py` — canonical schema for backtest output
- `results_io.py` — read/write results under `results/strategies/<name>/`

Consumed by `scripts/run_backtest.py` and the nightly pipeline; output is fed to `analytics/` for scoring.
