---
name: backtest
description: Run a backtest for a specific strategy against a benchmark
disable-model-invocation: true
argument-hint: <strategy> [--benchmark <benchmark>] [--refresh]
---

Run a backtest for a specific strategy. Available strategies: hrp, trend_following, equal_weight.

If arguments are provided, parse them:
- First positional argument is the strategy name
- `--benchmark` flag specifies the benchmark (default: equal_weight)
- `--refresh` forces fresh data from Interactive Brokers

1. Run: `python scripts/run_backtest.py --strategy $ARGUMENTS`
2. Wait for completion and report any errors
3. Show the performance comparison results
