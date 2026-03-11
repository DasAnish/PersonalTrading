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

### What Doesn't Exist Yet

- ❌ Trading strategies (HRP, mean-variance, etc.)
- ❌ Backtesting framework
- ❌ Performance analytics (Sharpe ratio, drawdown, etc.)
- ❌ Visualization capabilities
- ❌ Data caching/persistence layer
- ❌ Order execution simulation
- ❌ Live trading strategy execution

---

## Current Plan: HRP Trading Strategy Implementation

### Goal
Build a complete Hierarchical Risk Parity (HRP) trading strategy with backtesting capabilities for 4 UK ETFs.

### Specifications
- **Symbols**: VUSA, SSLN, SGLN, IWRD
- **Market**: Exchange=SMART, Currency=GBP, SecType=STK
- **Position Sizing**: Units = (Net Account Value × Weight) / Stock Price
- **Backtesting**: Maximum available historical data
- **Rebalancing**: Monthly (end of month)
- **Transaction Costs**: 7.5 basis points per trade
- **Benchmark**: Equal-weight portfolio
- **Visualization**: Portfolio value, drawdown, benchmark comparison

### Architecture Plan

**New Modules to Build**:

1. **strategies/** - Portfolio optimization strategies
   - `base.py` - Abstract BaseStrategy class
   - `hrp.py` - Hierarchical Risk Parity implementation (port from reference notebook)
   - `equal_weight.py` - Equal-weight benchmark

2. **backtesting/** - Backtesting framework
   - `engine.py` - Core backtesting simulation engine
   - `portfolio_state.py` - Portfolio state tracking over time
   - `transaction.py` - Transaction modeling with costs

3. **analytics/** - Performance analytics
   - `metrics.py` - Sharpe ratio, drawdown, CAGR, volatility calculations
   - `visualizations.py` - Chart generation using matplotlib

4. **data/** - Data management
   - `cache.py` - Historical data caching (parquet format)
   - `preprocessing.py` - Data alignment and cleaning

5. **scripts/** - Runnable scripts
   - `run_hrp_backtest.py` - Main backtest execution script

### HRP Algorithm Overview

**3-Stage Process** (from reference notebook):

1. **Tree Clustering**
   - Calculate correlation matrix from returns
   - Convert to distance matrix: `d = sqrt(0.5 * (1 - corr))`
   - Hierarchical clustering using `scipy.cluster.hierarchy.linkage()` with 'single' linkage

2. **Quasi-Diagonalization**
   - Reorganize covariance matrix so similar assets are together
   - `get_quasi_diag()` traverses linkage matrix from root to leaves
   - Output: sorted list of asset indices

3. **Recursive Bisection**
   - Start with all weights = 1
   - Iteratively bisect and allocate inversely to cluster variance
   - `get_rec_bipart()` returns final weights (sum to 1.0)

### Implementation Sequence

1. ✅ **Planning** - Comprehensive plan created
2. ⏳ **Setup** - Create directory structure, update dependencies
3. ⏳ **HRP Algorithm** - Port from reference notebook
4. ⏳ **Backtesting Engine** - Build simulation framework
5. ⏳ **Analytics** - Performance metrics and visualization
6. ⏳ **Data Management** - Caching and preprocessing
7. ⏳ **Integration** - End-to-end backtest script
8. ⏳ **Validation** - Test with historical data

**Estimated Time**: 12-18 hours total

### Key Implementation Details

**GBP Currency Override**
```python
# Must override default USD for UK ETFs
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
- Use 252 trading days (1 year) for HRP correlation calculation
- First rebalance occurs 1 year after data start

**Transaction Costs**
- 7.5 bps = 0.075% of trade value
- Deducted from cash on each trade
- Formula: `abs(quantity × price) × 0.00075`

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

## Web Dashboard (NEW - Feb 2026)

### Interactive Results Visualization

**File**: `scripts/serve_results.py`

**Purpose**: User-friendly web interface for viewing backtest results

**Features**:
- Portfolio value comparison chart (HRP vs Equal Weight)
- Drawdown analysis with underwater plot
- Portfolio weights visualization (stacked area chart)
- Transaction history with full details
- Performance metrics comparison table
- Responsive design (desktop, tablet, mobile)
- Interactive charts powered by Chart.js

**Usage**:
```bash
# Start dashboard
python scripts/serve_results.py

# Or use startup scripts
scripts/start_dashboard.bat    # Windows
bash scripts/start_dashboard.sh # macOS/Linux

# Then open browser: http://localhost:5000
```

**API Endpoints**:
- `GET /` - Main dashboard page (HTML)
- `GET /api/data` - Raw JSON data for all metrics, charts, and transactions

**Data Flow**:
1. Backtest generates CSV files in `results/` directory
2. Dashboard loads CSVs and serves as JSON
3. Frontend renders interactive visualizations
4. User explores results via browser tabs

**Technology Stack**:
- Backend: Flask (Python)
- Frontend: HTML5 + CSS3 + Vanilla JavaScript
- Charting: Chart.js 3.9.1
- Styling: Responsive CSS Grid + Flexbox

**Documentation**: See [DASHBOARD.md](DASHBOARD.md) for complete user guide

---

## Current Session Status

**Session Date**: 2026-02-15
**Status**: ✅ Production Ready - All features complete and documented
**Latest Addition**: Interactive web dashboard for results visualization

**Completed Components**:
- ✅ IB Wrapper + Market Data + Portfolio Management
- ✅ HRP Strategy Implementation + Backtesting Engine
- ✅ Performance Analytics + Metrics Calculation
- ✅ Data Caching with --refresh flag support
- ✅ Interactive Web Dashboard with responsive design
- ✅ Comprehensive documentation (README + DASHBOARD + CLAUDE)

**Next Actions** (Optional):
- [ ] Deploy to production server
- [ ] Add parameter tuning interface
- [ ] Implement live trading integration
- [ ] Add scenario analysis features
