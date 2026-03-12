# PersonalTrading - Development Context for Claude

A production-ready Python trading system for portfolio optimization and backtesting with Interactive Brokers integration.

## Project Overview

This system provides:
1. **Interactive Brokers Wrapper** - Async Python wrapper for IB API using `ib_insync`
2. **Market Data Service** - Historical and real-time market data fetching with caching
3. **Portfolio Management** - Position tracking, account monitoring, P&L tracking
4. **Trading Strategies** - Complete HRP portfolio optimization with backtesting
5. **Performance Analytics** - Visualization, metrics, and comprehensive reporting

---

## Current Project State

### What Exists (Production Ready)

**IB Wrapper Infrastructure** (`ib_wrapper/`)
- ✅ `client.py` - Unified IBClient interface for all IB operations
- ✅ `connection.py` - Connection management with auto-reconnect and exponential backoff
- ✅ `market_data.py` - Historical data fetching with rate limiting (50 req/10min)
  - `get_historical_bars()` - Single symbol fetching
  - `get_multiple_historical_bars()` - Batch fetching (concurrent/sequential modes)
  - `download_extended_history()` - Paginated historical data beyond IB limits
- ✅ `portfolio.py` - Position tracking, account summary, real-time updates
- ✅ `utils.py` - Rate limiting, retry logic, contract creation helpers
- ✅ `models.py` - Data models (Position, HistoricalBar, PortfolioUpdate, etc.)
- ✅ `config.py` - Configuration from .env files and YAML
- ✅ `exceptions.py` - Custom exception hierarchy

**Testing & Examples**
- ✅ `tests/` - Pytest-based unit tests with async support and mocks
- ✅ `examples/` - Working examples (fetch_historical_data.py, monitor_positions.py, etc.)

**Reference Materials**
- ✅ `references/Hierarchical-Risk-Parity/` - HRP algorithm notebook implementation
  - Contains complete working implementation of Hierarchical Risk Parity
  - Key functions: `get_quasi_diag()`, `get_cluster_var()`, `get_rec_bipart()`

### Current Capabilities

**Data Fetching**
- Historical OHLCV data for stocks, options, futures, forex
- Smart routing across exchanges (SMART exchange default)
- Multiple currencies supported (USD default, can override to GBP, EUR, etc.)
- Multiple bar sizes: 1 sec to 1 month
- Data types: TRADES, MIDPOINT, BID, ASK
- Automatic rate limiting and retry with exponential backoff

**Portfolio Tracking**
- Real-time position monitoring
- Account value tracking (NetLiquidation, BuyingPower, etc.)
- Realized and unrealized P&L
- Real-time portfolio updates via callbacks

**Connection Management**
- Async/await throughout
- Auto-reconnect on disconnect
- Paper and live trading support
- Read-only mode available

**Portfolio Optimization Strategies**
- ✅ `strategies/base.py` - Abstract BaseStrategy class for all strategies
- ✅ `strategies/hrp.py` - Hierarchical Risk Parity implementation
- ✅ `strategies/equal_weight.py` - Equal-weight baseline benchmark
- ✅ `strategies/__init__.py` - Strategy registry and factory pattern for pluggable strategies

**Backtesting Framework**
- ✅ `backtesting/engine.py` - Core backtesting simulation engine
- ✅ `backtesting/portfolio_state.py` - Portfolio state tracking over time
- ✅ `backtesting/transaction.py` - Transaction modeling with costs

**Analytics & Visualization**
- ✅ `analytics/metrics.py` - Performance metrics (Sharpe, drawdown, CAGR, volatility)
- ✅ `analytics/visualizations.py` - Chart generation using matplotlib
- ✅ `scripts/serve_results.py` - Interactive web dashboard (Flask + Chart.js)

**Data Management**
- ✅ `data/cache.py` - Historical data caching (parquet format)
- ✅ `data/preprocessing.py` - Data alignment and cleaning

### What Doesn't Exist Yet

- ❌ Additional strategies (mean-variance, risk parity, etc.)
- ❌ Order execution simulation
- ❌ Live trading strategy execution
- ❌ Parameter optimization/tuning
- ❌ Multi-strategy comparison (3+ strategies)

---

## Pluggable Strategy System

### Overview

The system now supports pluggable portfolio optimization strategies that can be easily tested and compared. Strategies inherit from `BaseStrategy` and implement the `calculate_weights()` method.

### Available Strategies

1. **Hierarchical Risk Parity (HRP)**
   - Files: `strategies/hrp.py`
   - Command: `python scripts/run_backtest.py --strategy hrp`
   - Parameters: `--hrp-linkage-method` (single|complete|average|ward)

2. **Trend Following (Momentum-based)**
   - Files: `strategies/trend_following.py`
   - Command: `python scripts/run_backtest.py --strategy trend_following`
   - Parameters: `--lookback-days`, `--half-life-days`, `--signal-threshold`
   - Algorithm: EWMA momentum signals normalized by volatility with risk parity weighting

3. **Equal Weight (Benchmark)**
   - Files: `strategies/equal_weight.py`
   - Command: `python scripts/run_backtest.py --strategy equal_weight`
   - Parameters: None

### Strategy Registry

All strategies are registered in `strategies/__init__.py` using a pluggable registry pattern:

```python
STRATEGY_REGISTRY = {
    'hrp': {'class': HRPStrategy, 'display_name': 'Hierarchical Risk Parity', ...},
    'trend_following': {'class': TrendFollowingStrategy, 'display_name': 'Trend Following', ...},
    'equal_weight': {'class': EqualWeightStrategy, 'display_name': 'Equal Weight', ...}
}
```

New strategies can be added by:
1. Creating a class that inherits from `BaseStrategy`
2. Implementing `calculate_weights(prices)` method
3. Registering in `STRATEGY_REGISTRY` with metadata

### Backtesting Specifications

- **Symbols**: VUSA, SSLN, SGLN, IWRD
- **Market**: Exchange=SMART, Currency=GBP, SecType=STK
- **Position Sizing**: Units = (Net Account Value × Weight) / Stock Price
- **Backtesting**: Maximum available historical data
- **Rebalancing**: Monthly (end of month)
- **Transaction Costs**: 7.5 basis points per trade
- **Default Comparison**: Primary strategy vs Equal Weight benchmark
- **Visualization**: Portfolio value, drawdown, benchmark comparison

### Hierarchical Risk Parity (HRP) Algorithm

HRP is one of the available strategies. It uses a 3-stage process:

1. **Tree Clustering**
   - Calculate correlation matrix from returns
   - Convert to distance matrix: `d = sqrt(0.5 * (1 - corr))`
   - Hierarchical clustering using `scipy.cluster.hierarchy.linkage()` with configurable linkage method

2. **Quasi-Diagonalization**
   - Reorganize covariance matrix so similar assets are together
   - `get_quasi_diag()` traverses linkage matrix from root to leaves
   - Output: sorted list of asset indices

3. **Recursive Bisection**
   - Start with all weights = 1
   - Iteratively bisect and allocate inversely to cluster variance
   - `get_rec_bipart()` returns final weights (sum to 1.0)

**Reference**: De Prado, M. L. (2016). "Building Diversified Portfolios that Outperform Out of Sample"

### Trend Following Strategy

Trend Following uses momentum signals to dynamically allocate across assets. It implements a systematic approach based on:

1. **Momentum Calculation**
   - Uses 2-year (504 trading days) historical lookback period
   - Applies EWMA (Exponentially Weighted Moving Average) with 60-day half-life
   - Emphasizes recent price trends while discounting older data
   - Formula: momentum = weighted average of returns × 252 (annualized)

2. **Signal Normalization**
   - Divides momentum by asset volatility (Sharpe-like ratio)
   - Accounts for risk differences: high momentum/low vol assets favored
   - Computed over same 2-year lookback for consistency

3. **Signal Smoothing**
   - Applies 5-day exponential smoothing to reduce noise
   - Prevents overtrading on daily fluctuations
   - Preserves larger trend changes

4. **Weak Signal Thresholding**
   - Sets signals with |value| < 0.1 to zero
   - Avoids trading on marginal signals
   - Reduces transaction costs on uncertain positions

5. **Risk Parity on Signals**
   - Allocates inversely to volatility among strong signals
   - Positions weighted by (signal / volatility)
   - Equal risk contribution from momentum factors
   - Long-only: only positive signals used, cash drag when all weak

**Example Usage**:
```python
from strategies import TrendFollowingStrategy, UKETFsMarket

market = UKETFsMarket()
trend = TrendFollowingStrategy(
    underlying=market,
    lookback_days=504,      # 2 years
    half_life_days=60,      # EWMA decay
    smooth_window=5,        # Signal smoothing
    signal_threshold=0.1    # Threshold for weak signals
)

weights = trend.calculate_weights(prices_df)
```

### Implementation Status

1. ✅ **Planning** - Comprehensive plan created
2. ✅ **Setup** - Directory structure created, dependencies installed
3. ✅ **HRP Algorithm** - Ported from reference notebook
4. ✅ **Backtesting Engine** - Simulation framework implemented
5. ✅ **Analytics** - Performance metrics and visualization complete
6. ✅ **Data Management** - Caching and preprocessing implemented
7. ✅ **Strategy Registry** - Pluggable strategy system implemented
8. ✅ **Integration** - End-to-end backtest script with CLI arguments
9. ✅ **Dashboard** - Interactive web results visualization
10. ✅ **Validation** - Tested with historical UK ETF data

### Command-Line Interface

**Generic Backtest Script**: `python scripts/run_backtest.py`

**Two Modes of Operation**:

#### Mode 1: Registry-Based (Traditional - Backward Compatible)

Uses built-in strategy registry:

```bash
# Available arguments
--strategy {hrp|equal_weight|trend_following}    # Default: hrp
--benchmark {hrp|equal_weight|trend_following}   # Default: equal_weight
--hrp-linkage-method {single|complete|average|ward}  # Default: single
--trend-following-lookback-days INT              # Default: 504
--trend-following-half-life-days INT             # Default: 60
--refresh                                        # Force fresh data from IB
```

**Examples**:
```bash
# Default: Test HRP vs Equal Weight
python scripts/run_backtest.py

# Test HRP with ward linkage
python scripts/run_backtest.py --strategy hrp --hrp-linkage-method ward

# Test Trend Following vs HRP
python scripts/run_backtest.py --strategy trend_following --benchmark hrp

# Force fresh data from IB
python scripts/run_backtest.py --refresh
```

#### Mode 2: YAML Definitions (Recommended)

Loads strategies from configuration files in `strategy_definitions/`. No code changes needed to create new strategies.

```bash
# Enable definitions mode
--use-definitions

# Strategy selection (keys from YAML files)
--strategy {uk_etfs|hrp_single|hrp_ward|trend_following|equal_weight|...}
--benchmark {uk_etfs|hrp_single|hrp_ward|trend_following|equal_weight|...}

# Use pre-composed multi-layer strategies
--composed-strategy {trend_with_vol_12|hrp_with_constraints|trend_constrained_vol_target|...}
```

**Examples**:
```bash
# Simple comparison: Trend Following vs HRP Ward
python scripts/run_backtest.py --use-definitions \
  --strategy trend_following \
  --benchmark hrp_ward

# Use pre-composed strategy
python scripts/run_backtest.py --use-definitions \
  --composed-strategy trend_with_vol_12

# Different allocations with custom overlays
python scripts/run_backtest.py --use-definitions \
  --strategy hrp_single \
  --benchmark equal_weight
```

**Why Use YAML Definitions?**
- ✓ No code changes needed
- ✓ Version control friendly
- ✓ Composable multi-layer strategies
- ✓ Easy strategy sharing
- ✓ Clear parameter documentation

**Creating Custom Strategies**:

1. Create YAML file in `strategy_definitions/` subdirectory
2. Define parameters in YAML format
3. Use immediately with `--use-definitions`

See [strategy_definitions/CUSTOM_STRATEGIES.md](strategy_definitions/CUSTOM_STRATEGIES.md) for complete guide.

Example custom strategy file: `strategy_definitions/allocations/my_momentum.yaml`
```yaml
type: allocation
class: TrendFollowingStrategy
market: uk_etfs
description: Custom momentum strategy with aggressive parameters

parameters:
  lookback_days: 252
  half_life_days: 30
  smooth_window: 3
  signal_threshold: 0.15
```

Usage:
```bash
python scripts/run_backtest.py --use-definitions \
  --strategy my_momentum \
  --benchmark hrp_ward
```

**Available Pre-Defined Strategies**:

Markets: `uk_etfs`, `us_equities`
Allocations: `hrp_single`, `hrp_ward`, `trend_following`, `equal_weight`
Overlays: `vol_target_12pct`, `vol_target_15pct`, `constraints_5_40`, `constraints_10_30`, `leverage_1x`
Composed: `trend_with_vol_12`, `hrp_with_constraints`, `trend_constrained_vol_target`

List all:
```bash
python -c "from strategies.strategy_loader import StrategyLoader; \
  loader = StrategyLoader(); \
  print('Allocations:', list(loader.list_strategies('allocation').keys()))"
```

#### Mode 3: All Strategies (NEW - March 2026)

Runs all available strategies in a single command and outputs separate result files for each strategy.

```bash
# Run all strategies with separate result files
--all                 # Automatically loads all strategies from YAML definitions

# Optional flags
--refresh            # Force fresh data from IB (skips cache)
```

**Examples**:
```bash
# Run all available strategies and generate separate results
python scripts/run_backtest.py --all

# Force fresh data from Interactive Brokers
python scripts/run_backtest.py --all --refresh
```

**Output Structure**:
```
results/
├── strategies_index.json          # Master index with all strategies
└── strategies/
    ├── hrp_single/
    │   ├── portfolio_history.json
    │   ├── transactions.json
    │   ├── weights_history.json
    │   ├── metrics.json
    │   └── info.json
    ├── hrp_ward/
    │   └── ... (same structure)
    ├── trend_following/
    │   └── ... (same structure)
    ├── equal_weight/
    │   └── ... (same structure)
    └── ... (all other strategies)
```

**Using with Dashboard**:
```bash
# Run all strategies
python scripts/run_backtest.py --all

# In another terminal, start the dashboard
python scripts/serve_results.py

# Open http://localhost:5000
# Dashboard automatically discovers all strategies from results/strategies_index.json
# Use dropdowns to select and compare any two strategies
```

**Why Use --all Mode?**
- ✓ Comprehensive testing of all strategies in one run
- ✓ Organized results in separate files for each strategy
- ✓ Dynamic strategy picker in dashboard (no need to rerun for each comparison)
- ✓ Separate JSON files enable efficient data loading on demand
- ✓ Master index enables strategy discovery and metadata

**Backward Compatibility**:
- Old script: `run_hrp_backtest.py` (deprecated, forwards to `run_backtest.py`)
- All existing registry-based commands work unchanged
- Legacy --use-definitions mode still supported
- New --all mode is opt-in

### Key Implementation Details

**GBP Currency Override**
```python
# UK ETFs require GBP currency override (default is USD)
df = await client.get_historical_bars(
    symbol='VUSA',
    currency='GBP',  # Override default USD
    exchange='SMART',
    sec_type='STK',
    bar_size='1 day'
)
```

**Monthly Rebalancing**
```python
# Generate end-of-month dates
rebalance_dates = pd.date_range(start, end, freq='M')
# Align to actual trading days in data
```

**Lookback Window**
- Use 252 trading days (1 year) for correlation/covariance calculation
- First rebalance occurs 1 year after data start

**Transaction Costs**
- 7.5 bps = 0.075% of trade value
- Deducted from cash on each trade
- Formula: `abs(quantity × price) × 0.00075`

**Result Files**
- Portfolio histories: `hrp_portfolio_history.csv`, `ew_portfolio_history.csv`
- Transactions: `hrp_transactions.csv`, `ew_transactions.csv`
- Metrics: `performance_comparison.csv`
- Metadata: `metadata.json` (includes actual strategy names and parameters)
- Charts: `performance_charts.png`

---

## Dependencies

**Current** (pyproject.toml):
- `ib_insync>=0.9.86` - Interactive Brokers API wrapper
- `pandas>=2.0.0` - Data manipulation
- `numpy>=1.24.0` - Numerical computing
- `python-dotenv>=1.0.0` - Environment variable management
- `pyyaml>=6.0` - YAML configuration

**To Add for HRP Strategy**:
- `scipy>=1.11.0` - Hierarchical clustering (linkage function)
- `matplotlib>=3.7.0` - Visualization
- `pyarrow>=12.0.0` - Parquet caching (optional but recommended)

---

## Project Structure

```
PersonalTrading/
├── ib_wrapper/              # IB API wrapper (PRODUCTION)
│   ├── client.py
│   ├── connection.py
│   ├── market_data.py
│   ├── portfolio.py
│   ├── utils.py
│   ├── models.py
│   ├── config.py
│   └── exceptions.py
├── tests/                   # Unit tests (PRODUCTION)
├── examples/                # Usage examples (PRODUCTION)
├── references/              # Reference implementations
│   └── Hierarchical-Risk-Parity/
│       └── Hierarchical Clustering.ipynb
├── strategies/              # TO BUILD: Trading strategies
├── backtesting/             # TO BUILD: Backtesting framework
├── analytics/               # TO BUILD: Performance analytics
├── data/                    # TO BUILD: Data management
├── scripts/                 # Runnable scripts
│   └── run_hrp_backtest.py  # TO BUILD: Main backtest script
├── pyproject.toml           # Project configuration
├── .env                     # Environment variables (IB credentials)
└── CLAUDE.md               # This file
```

---

## Important Context & Constraints

### Data Fetching
- **Rate Limit**: 50 requests per 10 minutes (automatically handled by RateLimiter)
- **Bar Size for EOD**: Use `bar_size='1 day'` and extract 'close' column
- **Maximum History**: Use `download_extended_history()` which paginates in 1-year chunks
- **Data Format**: Returns pandas DataFrame with columns: date, open, high, low, close, volume, average, barCount

### IB Connection
- **Paper Trading**: Port 7497 (TWS) or 4001 (IB Gateway)
- **Live Trading**: Port 7496 (TWS) or 4002 (IB Gateway)
- **Connection**: Async/await required, auto-reconnect enabled
- **Client ID**: Configurable, default=1

### Testing Strategy
- Use pytest with pytest-asyncio
- Mock IB instance for unit tests
- Integration tests use real IB connection (optional)
- Test fixtures in conftest.py

### Code Quality Standards
- Type hints preferred (but not enforced by mypy currently)
- Black formatting (line length 88)
- Async/await throughout
- Comprehensive error handling
- Logging at appropriate levels (DEBUG, INFO, WARNING, ERROR)

---

## Next Steps

1. **Review Plan**: User reviews the detailed implementation plan in plan file
2. **Approve & Begin**: User approves plan, implementation begins
3. **Setup Phase**: Create directory structure, update pyproject.toml, install dependencies
4. **Core Development**: Implement HRP algorithm, backtesting engine, analytics
5. **Integration**: Build end-to-end backtest script
6. **Validation**: Run backtest on historical UK ETF data
7. **Results Analysis**: Review performance metrics, charts, and compare to benchmark

---

## Reference Files

**Critical Files for HRP Implementation**:
- `references/Hierarchical-Risk-Parity/Hierarchical Clustering.ipynb` - Algorithm source
  - Cell 14: `get_quasi_diag()` implementation
  - Cell 17: `get_cluster_var()` and `get_rec_bipart()` implementations
  - Cells 7-20: Complete workflow example

**Data Fetching Reference**:
- `ib_wrapper/market_data.py:225-332` - `download_extended_history()` implementation
- `examples/fetch_historical_data.py` - Example of multi-symbol fetching

**Portfolio Reference**:
- `ib_wrapper/portfolio.py` - Position tracking patterns
- `ib_wrapper/models.py` - Data models to follow

---

## Notes for Future Sessions

**Data Caching**:
- Cache fetched historical data to avoid hitting rate limits during development
- Use parquet format for efficient storage and fast loading
- Cache directory: `data/cache/`
- File naming: `{symbol}_{start_date}_{end_date}.parquet`

**Backtesting Edge Cases**:
- Handle insufficient data at start (need 252 days before first rebalance)
- Handle missing data (forward fill max 3 days, skip rebalance if >10% missing)
- Prevent negative cash (scale down trades if insufficient cash)
- Round to whole shares (track residual cash)

**Performance Expectations**:
- HRP typically shows lower volatility than equal-weight
- Sharpe ratio typically 0.5-2.0 for equity portfolios
- Max drawdown typically 15-30% for equity portfolios
- Equal-weight benchmark should have higher volatility and similar returns

**Visualization Guidelines**:
- 3-panel layout: portfolio value, drawdown, metrics table
- Clear labels, legends, grid lines
- Save as PNG for documentation
- Use consistent color scheme (e.g., blue=HRP, orange=benchmark)

---

## Contact & Resources

- **IB API Documentation**: https://interactivebrokers.github.io/tws-api/
- **ib_insync Documentation**: https://ib-insync.readthedocs.io/
- **HRP Research**: De Prado, M. L. (2016). "Building Diversified Portfolios that Outperform Out of Sample"

---

## Web Dashboard (UPDATED - March 2026)

### Interactive Results Visualization with Strategy Comparison

**File**: `scripts/serve_results.py`

**Purpose**: User-friendly web interface for viewing and comparing backtest results

**Features**:
- **Strategy Picker**: Dropdown menu to select which strategy to view
- **Comparison Mode**: Select two strategies to compare metrics side-by-side
- **View Mode Toggle**: Switch between single strategy view and comparison mode
- **Dynamic Chart Rendering**: Portfolio value, drawdown, weights, transactions
- **On-Demand Loading**: Strategies load only when selected for performance
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Interactive Charts**: Powered by Chart.js with zoom and hover details

**Usage**:
```bash
# Step 1: Run all available strategies
python scripts/run_backtest.py --all              # Generates separate result files
python scripts/run_backtest.py --all --refresh    # Force fresh data from IB

# Step 2: Start the dashboard server
python scripts/serve_results.py

# Step 3: Open browser to http://localhost:5000
# - Select Strategy 1 from dropdown
# - Click "Comparison" button to enable Strategy 2 selector
# - Select Strategy 2 to compare side-by-side
# - View metrics, charts, and transactions with dynamic updates
```

**Result Structure** (from `--all` mode):
```
results/
├── strategies_index.json          # Master index with all strategies
└── strategies/
    ├── hrp_single/
    │   ├── portfolio_history.json  # Portfolio values over time
    │   ├── transactions.json       # All trades/rebalances
    │   ├── weights_history.json    # Asset allocation over time
    │   ├── metrics.json            # Performance metrics (return, vol, sharpe, etc)
    │   └── info.json               # Strategy metadata (type, class, params)
    ├── trend_following/
    │   └── ... (same structure)
    ├── equal_weight/
    │   └── ... (same structure)
    └── ...
```

**API Endpoints**:
- `GET /` - Main dashboard with HTML/CSS/JS and strategy pickers
- `GET /api/strategies` - Returns JSON list of available strategy keys
- `GET /api/strategy/<strategy_key>` - Returns JSON with all data for strategy

**Example API Responses**:
```bash
# Get list of strategies
curl http://localhost:5000/api/strategies
# Returns: ["hrp_single", "hrp_ward", "trend_following", "equal_weight", ...]

# Get data for specific strategy
curl http://localhost:5000/api/strategy/hrp_single
# Returns: {
#   "key": "hrp_single",
#   "portfolio_history": [...],
#   "transactions": [...],
#   "weights_history": [...],
#   "metrics": {
#     "total_return": 0.45,
#     "volatility": 0.12,
#     "sharpe_ratio": 0.67,
#     ...
#   },
#   "info": {...}
# }
```

**Dashboard Tabs**:
1. **Overview** - Performance metrics table and key metrics cards
2. **Portfolio Value** - Line chart showing portfolio value over time
3. **Drawdown** - Drawdown analysis (underwater plot)
4. **Weights** - Stacked area chart of asset allocation
5. **Transactions** - Table of all trades/rebalances

**Technology Stack**:
- Backend: Flask (Python)
- Frontend: HTML5 + CSS3 + Vanilla JavaScript
- Charting: Chart.js 3.9.1
- Styling: CSS Grid + Flexbox (responsive)
- Data Format: JSON (separate files per strategy)
- Data Loading: Async fetch API with caching

**Key JavaScript Functions**:
- `initializeDashboard()` - Load strategy list and populate dropdowns
- `handleStrategyChange()` - Load selected strategy data on demand
- `updateDashboard()` - Refresh all tabs and charts
- `displayMetrics()` - Render metrics table
- `displayPortfolioChart()` - Render portfolio value chart
- `displayDrawdownChart()` - Render drawdown chart
- `displayWeightsChart()` - Render weights stacked area chart
- `displayTransactions()` - Render transaction table

**Performance Optimizations**:
- Lazy loading: Only fetch strategy data when selected
- Chart limit: Limit data points to 100 for responsive rendering
- Caching: Store loaded strategy data in JavaScript memory
- On-demand: Comparison mode only loads second strategy if selected

---

## Composable Strategy Architecture (NEW - March 2026)

A major architectural refactoring that enables building complex strategies by composing simpler components.

**Core Concept**: Strategies can wrap other strategies to create powerful compositions:
```
VolatilityTarget(HRP(UKETFsMarket()))
```

**Three-Tier System**:
1. **Market Strategies** - Define which assets to trade (UKETFsMarket, USEquitiesMarket, CustomMarket)
2. **Allocation Strategies** - Calculate weights (HRPStrategy, EqualWeightStrategy wrap a market)
3. **Overlay Strategies** - Transform weights (VolatilityTargetStrategy, ConstraintStrategy wrap any strategy)

**New Files**:
- `strategies/base.py` - Added `ExecutableStrategy`, `MarketStrategy`, `AllocationStrategy`, `OverlayStrategy`
- `strategies/models.py` - Data classes: `Instrument`, `MarketDefinition`, `OverlayContext`
- `strategies/markets.py` - Market strategy implementations
- `strategies/overlays.py` - Overlay strategies (Vol Target, Constraints, Leverage)
- `COMPOSABLE_STRATEGIES.md` - Complete guide with examples

**Key Overlays**:
- **VolatilityTargetStrategy**: Scale weights to achieve target volatility (e.g., 12% annually)
- **ConstraintStrategy**: Enforce min/max weight limits per position (e.g., 5%-40%)
- **LeverageStrategy**: Apply gross leverage limits

**Benefits**:
- Modular and testable architecture
- Reusable components (markets, allocations, overlays)
- Easy to combine risk management with optimization
- Chain multiple overlays: VT(LC(HRP(Market)))
- Full backward compatibility with old API

**Example Usage**:
```python
from strategies import HRPStrategy, VolatilityTargetStrategy, UKETFsMarket

market = UKETFsMarket()
hrp = HRPStrategy(underlying=market, linkage_method='ward')
vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)

weights = vol_target.calculate_weights(prices)
```

See `COMPOSABLE_STRATEGIES.md` for comprehensive guide.

---

## Current Session Status

**Session Date**: 2026-03-12 (Updated)
**Status**: ✅ Production Ready - All-strategies mode with dynamic comparison dashboard
**Latest Feature**: All-strategies execution with separate result files and dynamic strategy picker

**Completed Components**:
- ✅ IB Wrapper + Market Data + Portfolio Management
- ✅ HRP Strategy Implementation + Equal Weight Benchmark
- ✅ Pluggable Strategy System (registry + factory pattern)
- ✅ Composable Strategy Architecture (Markets, Allocations, Overlays)
- ✅ Backtesting Engine with overlay support
- ✅ Performance Analytics + Metrics Calculation
- ✅ Data Caching with --refresh flag support
- ✅ **NEW**: All-Strategies Execution Mode
- ✅ **UPDATED**: Interactive Web Dashboard with Strategy Picker
- ✅ CLI argument system for strategy selection and parameters
- ✅ Comprehensive documentation

**Recent Changes** (This Session - All-Strategies Mode):
- ✅ Implemented `--all` flag in run_backtest.py to run all available strategies
- ✅ Separate result files for each strategy in `results/strategies/<key>/`
- ✅ Master index file `strategies_index.json` with all strategy metadata
- ✅ Structured JSON output: portfolio_history.json, transactions.json, weights_history.json, metrics.json, info.json
- ✅ Updated serve_results.py with strategy picker dropdown
- ✅ Implemented comparison mode to compare any two strategies
- ✅ View mode toggle: Single View vs Comparison Mode
- ✅ Dynamic dashboard that loads selected strategy data on demand
- ✅ All tabs support comparison (Overview, Portfolio Value, Drawdown, Weights, Transactions)
- ✅ JSON API endpoints: /api/strategies and /api/strategy/<key>
- ✅ Frontend caching of loaded strategy data for performance

**Previous Session Changes** (Composable Architecture):
- ✅ Implemented `ExecutableStrategy` base class with run() method
- ✅ Created `MarketStrategy` for asset universe definitions
- ✅ Refactored `HRPStrategy` and `EqualWeightStrategy` to use `AllocationStrategy`
- ✅ Implemented `OverlayStrategy` base class with transform_weights()
- ✅ Created market strategies: UKETFsMarket, USEquitiesMarket, CustomMarket, etc.
- ✅ Created overlay strategies: VolatilityTargetStrategy, ConstraintStrategy, LeverageStrategy
- ✅ Enhanced BacktestEngine with run_backtest_with_overlay() method
- ✅ Updated strategies/__init__.py with new exports
- ✅ Created composable_strategies_demo.py with 5 comprehensive examples
- ✅ Created COMPOSABLE_STRATEGIES.md with complete user guide

**Recent Changes** (This Session - Strategy Definitions System):
- ✅ Created YAML-based strategy definitions system
- ✅ Implemented `StrategyLoader` class for loading and building strategies
- ✅ Created 16 pre-built strategy definition files (markets, allocations, overlays, composed)
- ✅ Key-based strategy referencing for composable architecture
- ✅ Integration with `run_backtest.py` via `--use-definitions` flag
- ✅ Backward compatible with traditional registry-based approach
- ✅ Full documentation: `strategy_definitions/README.md`
- ✅ Custom strategy guide: `strategy_definitions/CUSTOM_STRATEGIES.md` (650+ lines)
- ✅ 13 pre-configured strategy combinations ready to use
- ✅ No-code strategy creation via YAML files

**Previous Session Changes** (Trend Following Implementation):
- ✅ Implemented `TrendFollowingStrategy` with EWMA momentum calculation
- ✅ 2-year lookback with 60-day EWMA half-life for momentum weighting
- ✅ Volatility normalization and signal smoothing
- ✅ Weak signal thresholding to eliminate marginal trades
- ✅ Risk parity allocation based on momentum strength

**Next Actions** (Optional):
- [ ] Add market data fetching to BacktestEngine for async execution
- [ ] Implement additional strategies (mean-variance, risk parity variants)
- [ ] Parameter optimization/tuning system (walk-forward analysis)
- [ ] Multi-strategy comparison (3+ strategies with dashboard refactor)
- [ ] Live trading execution with overlay strategies
- [ ] Custom overlay creation tutorial
- [ ] Backtest Trend Following vs HRP vs Equal Weight
