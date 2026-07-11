# optimization/

Parameter search and out-of-sample splitting for tuning strategies.

- `param_sweep.py` — grid search over strategy parameters
- `walk_forward.py` — walk-forward analysis (rolling in-sample fit → out-of-sample test)
- `splitters.py` — train/test split logic shared by sweeps and walk-forward

Driven by `scripts/run_optimization.py`. Note: the param sweep only supports the built-in strategy classes. See [../docs/cli.md](../docs/cli.md).
