# PersonalTrading

A Python framework for portfolio strategy research, backtesting, and analysis using Interactive Brokers data.

> **Research only.** All orders are entered manually via IB Gateway. No programmatic order execution.

---

## Features

- **6 allocation strategies**: HRP, Trend Following, Equal Weight, Minimum Variance, Risk Parity, Momentum
- **Overlay composition**: VolatilityTarget, Constraint, Leverage overlays applied to any strategy
- **YAML strategy definitions**: define and compose strategies declaratively
- **Backtesting engine**: monthly rebalancing, 7.5 bps transaction costs, realistic position sizing
- **Parameter optimization**: grid search and walk-forward analysis
- **Web dashboard**: compare any two strategies interactively via Flask + Chart.js
- **IB integration**: async data fetching with parquet caching, falls back to cache when offline
- **Analytics**: Sharpe, Sortino, Calmar, VaR/CVaR, drawdown, rolling metrics

---

## Quick Start

### Run a backtest

```bash
# HRP vs Equal Weight (default)
python scripts/run_backtest.py

# Trend Following vs HRP
python scripts/run_backtest.py --strategy trend_following --benchmark hrp

# HRP with Ward linkage
python scripts/run_backtest.py --strategy hrp --hrp-linkage-method ward

# Force fresh data from IB
python scripts/run_backtest.py --refresh
```

### Run all strategies

```bash
python scripts/run_backtest.py --all
```

Saves results under `results/strategies/<strategy_name>/`.

### View dashboard

```bash
python scripts/serve_results.py   # http://localhost:5000
```

### Run optimization

```bash
# Parameter sweep
python scripts/run_optimization.py --strategy hrp --param linkage_method=single,complete,ward

# Walk-forward
python scripts/run_optimization.py --strategy trend_following \
  --param lookback_days=252,504 --param half_life_days=30,60,90 \
  --walk-forward --in-sample 756 --out-of-sample 252
```

---

## Strategies

| Strategy | Key Parameters |
|----------|----------------|
| `hrp` | `--hrp-linkage-method {single\|complete\|average\|ward}` |
| `trend_following` | `--trend-following-lookback-days`, `--trend-following-half-life-days` |
| `equal_weight` | — |
| `minimum_variance` | — |
| `risk_parity` | — |
| `momentum` | — |

### YAML Definitions (recommended)

```bash
python scripts/run_backtest.py --use-definitions --strategy hrp_ward --benchmark equal_weight
python scripts/run_backtest.py --use-definitions --composed-strategy trend_with_vol_12
```

Pre-defined YAML keys live in `strategy_definitions/`:
- **Allocations**: `hrp_single`, `hrp_ward`, `trend_following`, `equal_weight`, `minimum_variance`, `risk_parity`, `momentum_top2`
- **Overlays**: `vol_target_12pct`, `vol_target_15pct`, `constraints_5_40`, `constraints_10_30`, `leverage_1x`
- **Composed**: `trend_with_vol_12`, `hrp_with_constraints`, `trend_constrained_vol_target`

See [strategy_definitions/CUSTOM_STRATEGIES.md](strategy_definitions/CUSTOM_STRATEGIES.md) for how to define your own.

### Programmatic Composition

```python
from strategies import (
    AssetStrategy, HRPStrategy, TrendFollowingStrategy,
    VolatilityTargetStrategy, ConstraintStrategy, EqualWeightStrategy
)

assets = [AssetStrategy(s, currency='GBP') for s in ['VUSA','SSLN','SGLN','IWRD']]

hrp = HRPStrategy(underlying=assets, linkage_method='ward')
trend = TrendFollowingStrategy(underlying=assets, lookback_days=504)

hrp_vol_targeted = VolatilityTargetStrategy(underlying=hrp, target_vol=0.15)
trend_constrained = ConstraintStrategy(underlying=trend, min_weight=0.05, max_weight=0.40)

meta = EqualWeightStrategy(underlying=[hrp_vol_targeted, trend_constrained])
```

---

## Installation

```bash
git clone https://github.com/DasAnish/PersonalTrading.git
cd PersonalTrading
pip install -e .

# With dev tools
pip install -e ".[dev]"
```

**Requirements**: Python 3.9+, IB Gateway or TWS (optional — cached data works offline)

### IB Gateway setup

1. Enable API: Settings → API → Settings → Enable ActiveX and Socket Clients
2. Set port: `4001` (Gateway paper) / `4002` (Gateway live) / `7497` (TWS paper) / `7496` (TWS live)
3. Trust IP: add `127.0.0.1`

Configure via `.env`:
```env
IB_HOST=127.0.0.1
IB_PORT=4001
IB_CLIENT_ID=1
```

---

## Project Structure

```
PersonalTrading/
├── scripts/
│   ├── run_backtest.py          # Main entry point (4 modes)
│   ├── run_optimization.py      # Parameter sweep & walk-forward
│   └── serve_results.py         # Dashboard server
│
├── strategies/                  # All strategy implementations
│   ├── core.py                  # AssetStrategy, AllocationStrategy, OverlayStrategy
│   ├── hrp.py                   # Hierarchical Risk Parity
│   ├── trend_following.py       # EWMA momentum
│   ├── equal_weight.py
│   ├── minimum_variance.py
│   ├── risk_parity.py
│   ├── momentum.py
│   └── overlays.py              # VolTarget, Constraint, Leverage
│
├── strategy_definitions/        # YAML strategy configs
│   ├── assets/                  # VUSA, SSLN, SGLN, IWRD
│   ├── allocations/             # hrp_single, hrp_ward, trend_following, ...
│   ├── overlays/                # vol_target_12/15pct, constraints_*, leverage_1x
│   ├── composed/                # Pre-built overlay compositions
│   └── markets/                 # uk_etfs, us_equities
│
├── backtesting/                 # Simulation engine
├── optimization/                # Grid search, walk-forward
├── analytics/                   # Metrics & visualisations
├── data/                        # Parquet caching, preprocessing
├── ib_wrapper/                  # Async IB API wrapper
├── mcp_server/                  # MCP server for Claude integration
├── docs/                        # Detailed documentation
└── tests/
```

---

## Documentation

| Topic | File |
|-------|------|
| Project overview & IB specs | [docs/project.md](docs/project.md) |
| Strategy architecture & algorithms | [docs/strategies.md](docs/strategies.md) |
| CLI reference (all 4 modes) | [docs/cli.md](docs/cli.md) |
| Dashboard usage & API | [docs/dashboard.md](docs/dashboard.md) |
| Session log & known issues | [docs/session_log.md](docs/session_log.md) |

---

## Testing

```bash
pytest
pytest --cov=strategies --cov=backtesting --cov-report=html
```

---

## Backtesting Specs

- **Symbols**: VUSA, SSLN, SGLN, IWRD (UK ETFs, GBP, SMART exchange)
- **Rebalancing**: Monthly (end of month)
- **Transaction costs**: 7.5 bps per trade
- **Position sizing**: `Units = (NAV × Weight) / Price`
- **Default lookback**: 252 days (HRP), 504 days (Trend Following)

---

## References

- De Prado (2016) — "Building Diversified Portfolios that Outperform Out of Sample" (HRP)
- [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)

---

**Disclaimer**: For research purposes only. Not financial advice.
