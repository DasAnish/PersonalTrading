# CLI Reference

All backtesting runs through `scripts/run_backtest.py`. Four modes:

---

## Mode 1: Registry-Based (Default)

```bash
python scripts/run_backtest.py [options]

--strategy {hrp|equal_weight|trend_following}    # Default: hrp
--benchmark {hrp|equal_weight|trend_following}   # Default: equal_weight
--hrp-linkage-method {single|complete|average|ward}  # Default: single
--trend-following-lookback-days INT              # Default: 504
--trend-following-half-life-days INT             # Default: 60
--refresh                                        # Force fresh data from IB
```

Examples:
```bash
python scripts/run_backtest.py                                          # HRP vs Equal Weight
python scripts/run_backtest.py --strategy hrp --hrp-linkage-method ward
python scripts/run_backtest.py --strategy trend_following --benchmark hrp
```

---

## Mode 2: YAML Definitions (Recommended)

```bash
python scripts/run_backtest.py --use-definitions \
  --strategy {hrp_single|hrp_ward|trend_following|equal_weight|...} \
  --benchmark {hrp_single|hrp_ward|...}

# Or use a pre-composed strategy
python scripts/run_backtest.py --use-definitions \
  --composed-strategy {trend_with_vol_12|hrp_with_constraints|trend_constrained_vol_target|...}
```

Available pre-defined keys:
- Markets: `uk_etfs`, `us_equities`
- Allocations: `hrp_single`, `hrp_ward`, `trend_following`, `equal_weight`
- Overlays: `vol_target_12pct`, `vol_target_15pct`, `constraints_5_40`, `constraints_10_30`, `leverage_1x`
- Composed: `trend_with_vol_12`, `hrp_with_constraints`, `trend_constrained_vol_target`

---

## Mode 3: All Strategies

Runs every available strategy and saves separate result files for each.

```bash
python scripts/run_backtest.py --all           # All strategies
python scripts/run_backtest.py --all --refresh # Force fresh data
```

Output structure:
```
results/
├── strategies_index.json
└── strategies/
    ├── hrp_single/
    │   ├── portfolio_history.json
    │   ├── transactions.json
    │   ├── weights_history.json
    │   ├── metrics.json
    │   └── info.json
    └── ... (one folder per strategy)
```

Then start the dashboard to compare any two:
```bash
python scripts/serve_results.py   # http://localhost:5000
```

---

## Mode 4: Parameter Optimization

```bash
python scripts/run_optimization.py --strategy hrp --param linkage_method=single,complete,ward

# Multiple params
python scripts/run_optimization.py --strategy trend_following \
  --param lookback_days=252,504 --param half_life_days=30,60,90

# Walk-forward (in-sample / out-of-sample)
python scripts/run_optimization.py --strategy hrp \
  --param linkage_method=single,complete,ward \
  --walk-forward --in-sample 756 --out-of-sample 252

# Custom metric
python scripts/run_optimization.py --strategy risk_parity \
  --param dummy=1 --metric sortino_ratio
```

Available strategies: `hrp`, `trend_following`, `equal_weight`, `minimum_variance`, `risk_parity`, `momentum`

Output: `results/param_sweep_<strategy>.csv` or `results/walk_forward_<strategy>.csv`

---

## Backward Compatibility

- `run_hrp_backtest.py` — deprecated, forwards to `run_backtest.py`
- Registry-based commands unchanged
- `--use-definitions` still supported
