---
name: backtest-all
description: Run all backtesting strategies and generate results
disable-model-invocation: true
argument-hint: [--refresh]
---

Run all available strategies in a single backtest run.

1. Run: `python scripts/run_backtest.py --all $ARGUMENTS`
2. Wait for completion and report any errors
3. Summarize the performance metrics for each strategy from the results
