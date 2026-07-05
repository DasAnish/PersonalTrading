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

---

## Validation Battery

Runs a four-test validation suite (MinBTL → DSR → CPCV → Block bootstrap) to
determine if a strategy is ready for forward deployment.

```bash
# Single strategy with defaults
python scripts/validate_strategy.py --strategy hrp_ward

# Custom CPCV and bootstrap parameters
python scripts/validate_strategy.py --strategy hrp_ward \
  --n-trials 10 \
  --cpcv-folds 6 \
  --bootstrap-n 500 \
  --block-months 3 \
  --embargo-days 10

# Machine-readable single-line JSON on stdout
python scripts/validate_strategy.py --strategy hrp_ward --json

# Whole library: battery for every strategy with saved results,
# per-key summary table + verdict counts at the end
python scripts/validate_strategy.py --all
```

Options:
- `--strategy KEY` — Strategy key to validate (exactly one of this or `--all`)
- `--all` — Run the battery for every strategy under `results/strategies/`;
  per-key errors don't abort the batch
- `--n-trials N` — Trials for DSR / MinBTL (default: auto per strategy via
  `build_n_trials_map`, i.e. the strategy's family/sibling count)
- `--cpcv-folds K` — CPCV fold count (default: 6)
- `--bootstrap-n N` — Bootstrap iterations (default: 500)
- `--block-months M` — Bootstrap block size in months (default: 3)
- `--embargo-days D` — Embargo (purge) days for CPCV (default: 10)
- `--json` — Print single-line JSON to stdout instead of the table
  (validation.json is always written either way)

Output: `results/strategies/<strategy_key>/validation.json` (one per strategy)

---

## Full-Scale Run

One command for the whole loop: spins off the dashboard first, then runs
data load → backtests → mechanism coverage → validation battery as
subprocess calls to the CLIs above. The dashboard reads `results/` from disk
on every request, so refreshing the browser shows each step's output live.

```bash
# Backtest all + coverage + battery, dashboard at http://localhost:5000
python scripts/full_run.py

# Force fresh IB data, add library-wide SPA check and static reports
python scripts/full_run.py --refresh --spa --reports

# Headless (no dashboard)
python scripts/full_run.py --no-dashboard
```

Options:
- `--refresh` — Force fresh price data from IB Gateway (default: parquet cache)
- `--spa` — Also run `run_all_overfitting.py --spa` after the battery
- `--reports` — Also regenerate static md/html reports for every strategy
- `--no-dashboard` — Don't spin off the dashboard server

The dashboard keeps running after the script finishes. A failed backtest step
aborts the run; later steps (coverage/battery/SPA/reports) log failures but
don't abort each other.

---

## Mechanism Coverage & Tagging

Infer and tag strategy definitions with their economic mechanisms (from a
10-category vocabulary: trend, momentum-cs, mean-reversion, carry, vol-premium,
diversification, regime, hedging-overlay, seasonality, meta).

```bash
# Show mechanism coverage across all definitions
python scripts/tag_mechanisms.py --coverage

# Dry-run: show counts without writing
python scripts/tag_mechanisms.py --coverage --dry-run

# Write mech:<mechanism> tags into definitions
python scripts/tag_mechanisms.py
```

Options:
- `--coverage` — Print mechanism counts to console
- `--dry-run` — Don't write tags back to definitions
- `--definitions-dir PATH` — Override default `strategy_definitions/` location

Output: Each definition in `strategy_definitions/` gains a `tags` array with
entries like `"mech:trend"`. Used by `/build-strategies` strategist stage to
steer ideation toward underrepresented mechanisms.

---

## Backward Compatibility

- `run_hrp_backtest.py` — deprecated, forwards to `run_backtest.py`
- Registry-based commands unchanged
- `--use-definitions` still supported
