---
name: optimize
description: Run parameter optimization (sweep or walk-forward) for a strategy
disable-model-invocation: true
argument-hint: <strategy> --param key=val1,val2 [--walk-forward] [--metric sharpe_ratio] [--output path.csv]
---

Run parameter optimization for a strategy. Available strategies: hrp, trend_following, equal_weight, minimum_variance, risk_parity, momentum.

If arguments are provided, parse them:
- First positional argument is the strategy name
- `--param key=val1,val2,val3` defines the parameter grid (can be repeated for multiple params)
- `--metric` sets the optimization target: sharpe_ratio (default), sortino_ratio, calmar_ratio, total_return, volatility, max_drawdown
- `--walk-forward` activates walk-forward mode with overfitting detection
- `--in-sample INT` sets in-sample window in days (default: 756 = ~3 years, walk-forward only)
- `--out-of-sample INT` sets out-of-sample window in days (default: 252 = ~1 year, walk-forward only)
- `--output PATH` saves results to a custom CSV path

Examples:
- `/optimize hrp --param linkage_method=single,complete,ward`
- `/optimize trend_following --param lookback_days=252,504 --param half_life_days=30,60`
- `/optimize hrp --param linkage_method=single,complete,ward --walk-forward`
- `/optimize momentum --param top_n=1,2,3 --metric sortino_ratio`

1. Run: `python scripts/run_optimization.py --strategy $ARGUMENTS`
2. Wait for completion and report any errors
3. Show the top 5 results by target metric, including parameter values and key metrics (Sharpe, Sortino, CAGR, Max Drawdown)
4. If walk-forward mode, also report the overfitting ratio (in-sample / out-of-sample metric)
5. Report the output CSV path where full results were saved
