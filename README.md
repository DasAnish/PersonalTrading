# PersonalTrading

A Python framework for portfolio strategy research, backtesting, validation, and overfitting analysis using Interactive Brokers data.

> **Research only.** All orders are entered manually via IB Gateway. No programmatic order execution — ever.

---

## Features

- **~30 strategy families**: HRP, Trend Following, Dual/Volatility/Cross-asset Momentum, Min Variance, Risk Parity, Max Diversification, Adaptive/Protective Asset Allocation, Mean Reversion, Long-term Reversal, 52-week High, Low-Vol / Low-Beta / Quality tilts, Cross-asset Carry, plus a suite of seasonality strategies (Halloween, turn-of-month, gold-autumn, presidential-cycle)
- **Overlay composition**: VolatilityTarget, VarianceTarget, Constraint, Leverage, plus risk overlays (turbulence, gold safe-haven, bond-duration hedge) applied to any base strategy
- **30-asset UCITS ETF universe**: global equities, bonds, precious metals, and broad commodities (`strategy_definitions/universe.json`)
- **YAML strategy definitions**: 60+ allocations and 118+ composed configs, defined and composed declaratively
- **Backtesting engine**: monthly rebalancing, 7.5 bps transaction costs, realistic position sizing
- **Validation & overfitting stack**: Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO), k-fold CV, and SPA as the go/no-go gate
- **Parameter optimization**: grid search and walk-forward analysis
- **Nightly pipeline**: data-freshness gate, full backtest refresh, run archive, and data-vintage tracking
- **Web dashboard**: compare strategies interactively via Flask + Chart.js, with a REST run/job API
- **MCP server**: exposes market data, portfolio, and backtesting tools to Claude
- **IB integration**: async data fetching with parquet caching, falls back to cache when offline
- **Analytics**: Sharpe, Sortino, Calmar, VaR/CVaR, drawdown, rolling metrics (annualization inferred from series spacing)

---

## Quick Start

### Run a backtest

```bash
# HRP vs Equal Weight (default)
python scripts/run_backtest.py

# Trend Following vs HRP
python scripts/run_backtest.py --strategy trend_following --benchmark hrp

# YAML definition
python scripts/run_backtest.py --use-definitions --strategy hrp_ward --benchmark equal_weight

# Force fresh data from IB
python scripts/run_backtest.py --refresh
```

Results save under `results/strategies/<strategy_name>/`.

### Validate a strategy

```bash
# Full validation + overfitting analysis (canonical entry)
python scripts/run_full_analysis.py --strategy <name>

# Overfitting only (DSR / PBO / k-fold / SPA)
python scripts/run_overfitting.py --strategy <name>
```

### Nightly pipeline

```bash
python scripts/run_nightly.py   # freshness gate → refresh → backtest → analysis → archive
```

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

## Universe

30-asset UCITS ETF universe defined in `strategy_definitions/universe.json`:

| Class | Count | Examples |
|-------|-------|----------|
| Equity (global / regional / EM) | 18 | VUSA, EQQQ, IWRD, IMEU, ASHR, WSML |
| Bond | 5 | VUTY, HYLD, AGGU, SEGA, TIGG |
| Commodity & precious metals | 7 | SSLN, SGLN, COMM, BRNT, CRUD, AIGC |

Buckets (`equity`, `bond`, `commodity`, `europe_equity`, `em_equity`, `all`) let strategies target subsets.

---

## Strategy Definitions (YAML)

```bash
python scripts/run_backtest.py --use-definitions --strategy hrp_ward --benchmark equal_weight
python scripts/run_backtest.py --use-definitions --composed-strategy trend_with_vol_12
```

Definitions live in `strategy_definitions/`:
- **`allocations/`** — 60+ base strategy configs
- **`overlays/`** — vol/variance targets, constraints, leverage, risk overlays
- **`composed/`** — 118+ pre-built overlay compositions
- **`portfolios/`** — meta-portfolio combinations
- **`markets/`** — universe subset definitions

See [strategy_definitions/CUSTOM_STRATEGIES.md](strategy_definitions/CUSTOM_STRATEGIES.md) to define your own.

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
2. Set port: `4001` (Gateway live) / `7497` (TWS paper) / `7496` (TWS live)
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
├── scripts/                     # Entry points
│   ├── run_backtest.py          # Backtest (4 modes)
│   ├── run_full_analysis.py     # Canonical validation + overfitting
│   ├── run_overfitting.py       # DSR / PBO / k-fold / SPA
│   ├── run_nightly.py           # Nightly pipeline (freshness gate → archive)
│   ├── run_optimization.py      # Parameter sweep & walk-forward
│   ├── serve_results.py         # Dashboard server
│   └── server/                  # Dashboard REST run/job API
│
├── strategies/                  # ~30 strategy families + overlays, catalog, taxonomy
├── strategy_definitions/        # YAML: universe, assets, allocations, overlays, composed, portfolios
├── backtesting/                 # Simulation engine
├── optimization/                # Grid search, walk-forward
├── analytics/                   # Metrics & visualisations
├── data/                        # Parquet caching, preprocessing, proxy-history splicing
├── ib_wrapper/                  # Async IB API wrapper
├── mcp_server/                  # MCP server for Claude integration
├── research/                    # Research backlog & idea schema
├── results/                     # Backtest & validation output archive
├── docs/                        # Detailed documentation
└── tests/
```

---

## Documentation

| Topic | File |
|-------|------|
| Project overview & IB specs | [docs/project.md](docs/project.md) |
| Strategy architecture & algorithms | [docs/strategies.md](docs/strategies.md) |
| Overfitting analysis (DSR, PBO, k-fold, SPA) | [docs/overfitting.md](docs/overfitting.md) |
| CLI reference (all modes) | [docs/cli.md](docs/cli.md) |
| Dashboard usage & API | [docs/dashboard.md](docs/dashboard.md) |
| Nightly pipeline & freshness gate | [docs/nightly.md](docs/nightly.md) |
| MCP tools (ib-trading server) | [docs/mcp-tools.md](docs/mcp-tools.md) |
| Session log & known issues | [docs/session_log.md](docs/session_log.md) |
| Full file/directory reference | [docs/project-structure.md](docs/project-structure.md) |

---

## Testing

```bash
pytest
pytest --cov=strategies --cov=backtesting --cov-report=html
```

---

## Backtesting Specs

- **Universe**: 30 UCITS ETFs (GBP, SMART exchange)
- **Rebalancing**: Monthly (end of month)
- **Transaction costs**: 7.5 bps per trade
- **Position sizing**: `Units = (NAV × Weight) / Price`
- **Metrics annualization**: inferred from series spacing (never hard-coded)

---

## References

- De Prado (2016) — "Building Diversified Portfolios that Outperform Out of Sample" (HRP)
- Bailey & López de Prado — Deflated Sharpe Ratio, Probability of Backtest Overfitting
- Hansen (2005) — Superior Predictive Ability (SPA) test
- [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE). Includes a [NOTICE](NOTICE) file with required attribution notices (Apache §4(d)) — any redistribution, modified or not, must carry that file's contents forward.

---

**Disclaimer**: For research purposes only. Not financial advice.
