# PersonalTrading: HRP Strategy & Backtesting System

A production-ready Python framework for portfolio optimization and backtesting using Hierarchical Risk Parity (HRP) with Interactive Brokers integration.

## Features

### 🎯 Core Capabilities

- ✅ **Hierarchical Risk Parity (HRP)** - Advanced portfolio optimization using machine learning-based hierarchical clustering
- ✅ **Complete Backtesting Engine** - Realistic simulation with transaction costs, monthly rebalancing, position tracking
- ✅ **Performance Analytics** - Sharpe ratio, drawdown, CAGR, volatility, return attribution analysis
- ✅ **Interactive Brokers Integration** - Real-time + historical data with automatic rate limiting
- ✅ **Historical Data Caching** - Efficient parquet-based caching to avoid API rate limits
- ✅ **Multi-Panel Visualizations** - 5-panel analysis (portfolio value, drawdown, weights, attribution, metrics)
- ✅ **Flexible Data Management** - Built-in cache system with on-demand refresh (--refresh flag)
- ✅ **Async-First Design** - Built on `asyncio` for efficient concurrent operations
- ✅ **Type-Safe** - Full type hints for IDE support and validation
- ✅ **Reconnection Logic** - Automatic reconnection with exponential backoff

## Quick Start

### 1️⃣ Run HRP Backtest (Cached Data - Fast)

```bash
python scripts/run_hrp_backtest.py
```

Outputs:
- `results/portfolio_history.csv` - Daily portfolio state
- `results/transactions.csv` - All trades executed
- `results/performance_comparison.csv` - Strategy metrics

### 2️⃣ View Interactive Dashboard

```bash
# Windows
scripts/start_dashboard.bat

# macOS/Linux
bash scripts/start_dashboard.sh

# Or directly
python scripts/serve_results.py
```

Then open: **http://localhost:5000**

### 3️⃣ Refresh with Latest IB Data (Optional)

```bash
python scripts/run_hrp_backtest.py --refresh
```

Fetches fresh data from Interactive Brokers and updates the cache.

---

## 📊 Interactive Dashboard Features

The web-based dashboard provides:

- **📈 Portfolio Value Chart** - Compare strategy performance over time
- **📉 Drawdown Analysis** - Visualize peak-to-trough declines
- **⚖️ Portfolio Weights** - See allocation changes at each rebalancing
- **💹 Metrics Comparison** - Side-by-side strategy performance
- **📋 Transaction History** - Detailed trade-by-trade breakdown
- **📱 Responsive Design** - Works on desktop, tablet, and mobile

**→ See [docs/dashboard.md](docs/dashboard.md) for detailed guide**

## Installation

1. Clone the repository:
```bash
git clone https://github.com/DasAnish/PersonalTrading.git
cd PersonalTrading
```

2. Install dependencies:
```bash
pip install -e .
```

For development (includes testing tools):
```bash
pip install -e ".[dev]"
```

## Prerequisites

- Python 3.9 or higher
- IB Gateway or Trader Workstation (TWS) running
- API connections enabled in IB Gateway/TWS settings

### IB Gateway/TWS Setup

1. Download and install [IB Gateway](https://www.interactivebrokers.com/en/index.php?f=16457) or [TWS](https://www.interactivebrokers.com/en/trading/tws.php)
2. Start IB Gateway/TWS and log in
3. Configure API settings:
   - Go to Settings → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set Socket port:
     - `7497` for TWS paper trading
     - `7496` for TWS live trading
     - `4002` for IB Gateway paper trading
     - `4001` for IB Gateway live trading
   - Enable "Read-Only API" if you only need market data and positions
   - Add `127.0.0.1` to trusted IPs

## Project Architecture

### Modules

| Module | Purpose | Status |
|--------|---------|--------|
| `ib_wrapper/` | Interactive Brokers API wrapper | ✅ Production |
| `strategies/` | Portfolio optimization (HRP, equal-weight) | ✅ Production |
| `backtesting/` | Backtesting simulation engine | ✅ Production |
| `analytics/` | Performance metrics & visualization | ✅ Production |
| `data/` | Data caching & preprocessing | ✅ Production |

### Key Components

**1. Interactive Brokers Wrapper** (`ib_wrapper/`)
- Async/await interface for all IB operations
- Automatic rate limiting (50 req/10 min)
- Extended history pagination
- Real-time portfolio updates

**2. HRP Strategy** (`strategies/hrp.py`)
- 3-stage hierarchical clustering algorithm
- More stable than mean-variance optimization
- Better empirical out-of-sample performance
- Based on De Prado (2016) research

**3. Backtesting Engine** (`backtesting/engine.py`)
- Monthly rebalancing
- Transaction cost modeling (7.5 bps)
- Realistic portfolio simulation
- Comprehensive history tracking

**4. Analytics** (`analytics/`)
- Sharpe ratio, CAGR, drawdown, volatility
- Return attribution analysis
- 5-panel visualization
- Performance comparison tables

**5. Data Management** (`data/`)
- Parquet-based caching
- Multi-symbol alignment
- Data quality validation
- Automatic refresh capability

## How It Works

### HRP Algorithm (3 Stages)

1. **Tree Clustering** - Hierarchical clustering on asset correlation distance
2. **Quasi-Diagonalization** - Reorder covariance matrix by asset similarity
3. **Recursive Bisection** - Allocate weights inversely to cluster variance

**Advantages**:
- ✅ More stable with correlated assets
- ✅ Avoids extreme concentration
- ✅ Better out-of-sample performance
- ✅ No need for return forecasts

### Backtesting Workflow

1. Load 4+ years of historical price data
2. Generate monthly rebalance dates
3. For each rebalance:
   - Extract 252-day lookback window
   - Calculate optimal HRP weights
   - Execute trades (sell/buy)
   - Deduct 7.5 bps transaction costs
   - Record portfolio state
4. Calculate performance metrics
5. Compare vs equal-weight benchmark
6. Generate visualization

## Quick Start - IB Integration

### Basic Connection

```python
import asyncio
from ib_wrapper import IBClient, Config

async def main():
    # Create client with default config
    client = IBClient()

    # Connect to IB
    await client.connect()
    print("Connected!")

    # Disconnect
    client.disconnect()

asyncio.run(main())
```

### Using Context Manager (Recommended)

```python
import asyncio
from ib_wrapper import IBClient

async def main():
    async with IBClient() as client:
        # Your code here
        positions = await client.get_positions()
        for pos in positions:
            print(f"{pos.symbol}: {pos.position} @ ${pos.market_price}")

asyncio.run(main())
```

### Fetch Historical Data

```python
import asyncio
from ib_wrapper import IBClient

async def main():
    async with IBClient() as client:
        # Fetch extended history for UK ETF
        bars = await client.market_data.download_extended_history(
            symbol="VUSA",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
            bar_size="1 day",
            currency="GBP",
            sec_type="STK",
            exchange="SMART"
        )

        print(f"Received {len(bars)} bars")
        print(bars.head())

asyncio.run(main())
```

### Run HRP Backtest

```python
import asyncio
from datetime import datetime
from ib_wrapper import IBClient
from data.cache import HistoricalDataCache
from data.preprocessing import align_dataframes
from backtesting.engine import BacktestEngine
from strategies import HRPStrategy, EqualWeightStrategy
from analytics.visualizations import plot_portfolio_comparison

async def run_backtest():
    symbols = ['VUSA', 'SSLN', 'SGLN', 'IWRD']
    start_date = datetime(2020, 1, 1)
    end_date = datetime(2024, 1, 1)

    async with IBClient() as client:
        cache = HistoricalDataCache()
        data_dict = {}

        # Fetch historical data
        for symbol in symbols:
            df = await cache.get_or_fetch_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                market_data_service=client.market_data,
                currency='GBP'
            )
            data_dict[symbol] = df

        # Align data
        prices = align_dataframes(data_dict)

        # Run backtests
        engine = BacktestEngine(initial_capital=10000, transaction_cost_bps=7.5)

        hrp_results = engine.run_backtest(
            HRPStrategy(), prices, start_date, end_date
        )

        ew_results = engine.run_backtest(
            EqualWeightStrategy(), prices, start_date, end_date
        )

        # Visualize results
        plot_portfolio_comparison(
            {'HRP': hrp_results, 'Equal Weight': ew_results},
            save_path='backtest_visualization.png'
        )

        # Print metrics
        print(f"HRP Return: {hrp_results.metrics['total_return']:.2f}%")
        print(f"HRP Sharpe: {hrp_results.metrics['sharpe_ratio']:.3f}")

asyncio.run(run_backtest())
```

### Monitor Portfolio

```python
import asyncio
from ib_wrapper import IBClient

async def main():
    async with IBClient() as client:
        # Get current positions
        positions = await client.portfolio.get_positions()
        for pos in positions:
            print(f"{pos.symbol}: {pos.position} shares")
            print(f"  Unrealized PnL: ${pos.unrealized_pnl:,.2f}")

        # Get account summary
        summary = await client.portfolio.get_account_summary()
        print(f"\nNet Liquidation: ${summary.get('NetLiquidation', 0):,.2f}")

asyncio.run(main())
```

### Real-time Updates

```python
import asyncio
from ib_wrapper import IBClient

async def main():
    async with IBClient() as client:
        # Subscribe to portfolio updates
        def on_update(update):
            pos = update.position
            print(f"{pos.symbol}: ${pos.unrealized_pnl:,.2f}")

        client.portfolio.subscribe_portfolio_updates(on_update)

        # Keep running to receive updates
        await asyncio.sleep(60)

asyncio.run(main())
```

## Configuration

### Environment Variables (`.env`)

Create `.env` file in project root:

```env
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
IB_ACCOUNT=DU123456
LOG_LEVEL=INFO
```

For paper trading, use port `7497`. For live trading, use port `7496`.

### YAML Config File

Create `config/ib_config.yaml`:

```yaml
ib_connection:
  host: "127.0.0.1"
  port: 7497
  client_id: 1

logging:
  level: "INFO"
  file: "logs/trading.log"
```

### Configuration Priority

1. Environment variables (`.env`) - highest priority
2. YAML config file - medium priority
3. Default values - lowest priority

## API Reference

### Key Classes

#### IBClient
Main client for all IB operations.

**Connection Methods**:
- `connect()` - Connect to IB Gateway/TWS
- `disconnect()` - Disconnect from IB
- `is_connected()` - Check connection status

**Properties**:
- `client.market_data` - MarketDataService instance
- `client.portfolio` - PortfolioManager instance

#### MarketDataService
Fetch historical and real-time market data.

**Key Methods**:
```python
# Single symbol
bars = await client.market_data.get_historical_bars(
    symbol="VUSA",
    duration="1 Y",
    bar_size="1 day",
    currency="GBP"
)

# Extended history (beyond IB limits)
bars = await client.market_data.download_extended_history(
    symbol="VUSA",
    start_date=datetime(2020, 1, 1),
    end_date=datetime(2024, 1, 1),
    bar_size="1 day",
    currency="GBP"
)

# Multiple symbols (concurrent)
data = await client.market_data.get_multiple_historical_bars(
    symbols=["VUSA", "SSLN", "SGLN", "IWRD"],
    duration="4 Y",
    bar_size="1 day",
    concurrent=False  # Use False for large batches
)
```

#### PortfolioManager
Get positions and account summary.

**Key Methods**:
```python
# Get positions
positions = await client.portfolio.get_positions()

# Get account summary
summary = await client.portfolio.get_account_summary()

# Subscribe to updates
def on_update(update):
    print(f"Position: {update.position.symbol}")

client.portfolio.subscribe_portfolio_updates(on_update)
```

#### HRPStrategy
Portfolio optimization using Hierarchical Risk Parity.

**Usage**:
```python
strategy = HRPStrategy()
weights = strategy.calculate_weights(price_data)
# Returns pd.Series: {'VUSA': 0.25, 'SSLN': 0.25, ...}
```

#### BacktestEngine
Simulate portfolio performance with transaction costs.

**Usage**:
```python
engine = BacktestEngine(
    initial_capital=10000,
    transaction_cost_bps=7.5,
    rebalance_frequency='monthly',
    lookback_days=252
)

results = engine.run_backtest(
    strategy=HRPStrategy(),
    historical_data=prices_df,
    start_date=datetime(2020, 1, 1),
    end_date=datetime(2024, 1, 1)
)
```

### Performance Metrics

Available in `results.metrics` after backtesting:

```python
{
    'total_return': -19.45,      # %
    'cagr': -4.46,                # Compound annual growth rate
    'sharpe_ratio': -6.146,       # Risk-adjusted return
    'max_drawdown': -19.53,       # % from peak
    'volatility': 15.34,          # Annualized std dev
    'total_transactions': 4,
    'total_transaction_costs': 7.52,  # £
    'final_value': 8055.12        # £
}
```

## Examples

See the `examples/` directory for complete working examples:

- [basic_connection.py](examples/basic_connection.py) - Simple connection example
- [fetch_historical_data.py](examples/fetch_historical_data.py) - Fetching market data
- [monitor_positions.py](examples/monitor_positions.py) - Viewing positions and account data
- [portfolio_realtime.py](examples/portfolio_realtime.py) - Real-time portfolio updates

Run an example:
```bash
python examples/basic_connection.py
```

## Performance Expectations

### Typical Results (UK ETF Portfolio)

| Metric | HRP | Equal Weight |
|--------|-----|--------------|
| Annual Return | 5-8% | 4-7% |
| Volatility | 12-15% | 15-18% |
| Sharpe Ratio | 0.8-1.2 | 0.6-0.9 |
| Max Drawdown | -15% to -25% | -20% to -30% |

*Note: Actual results vary based on market conditions and historical period.*

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ib_wrapper --cov=strategies --cov=backtesting --cov-report=html

# Run specific test file
pytest tests/test_market_data.py -v

# Run with verbose output
pytest -v
```

### Test Coverage

- Connection management and reconnection logic
- Market data fetching and caching
- Portfolio state tracking
- HRP weight calculation
- Backtesting engine correctness
- Performance metrics calculation

## Development

### Code Quality Tools

```bash
# Format code
black ib_wrapper/ strategies/ backtesting/ analytics/ data/ tests/

# Sort imports
isort ib_wrapper/ strategies/ backtesting/ analytics/ data/ tests/

# Lint
flake8 ib_wrapper/ strategies/ backtesting/ analytics/ data/

# Type check
mypy ib_wrapper/
```

### Code Standards

- **Formatting**: Black (line length 88)
- **Imports**: isort (black profile)
- **Type Hints**: Preferred but not enforced
- **Async/Await**: Used throughout for concurrency
- **Error Handling**: Comprehensive with custom exceptions
- **Logging**: INFO, DEBUG, WARNING, ERROR levels

### Project Structure

```
PersonalTrading/
├── ib_wrapper/                  # Interactive Brokers API wrapper
│   ├── client.py               # Unified IBClient interface
│   ├── connection.py           # Connection management
│   ├── market_data.py          # Historical & real-time data fetching
│   ├── portfolio.py            # Position tracking & account monitoring
│   ├── models.py               # Data models (Position, HistoricalBar, etc.)
│   ├── config.py               # Configuration from .env and YAML
│   ├── exceptions.py           # Custom exception hierarchy
│   └── utils.py                # Rate limiting, retry logic, helpers
│
├── strategies/                  # Portfolio optimization strategies
│   ├── base.py                 # Abstract BaseStrategy class
│   ├── hrp.py                  # Hierarchical Risk Parity implementation
│   └── equal_weight.py         # Equal-weight benchmark strategy
│
├── backtesting/                 # Backtesting simulation framework
│   ├── engine.py               # Core backtesting engine
│   ├── portfolio_state.py      # Portfolio state tracking
│   └── transaction.py          # Transaction modeling with costs
│
├── analytics/                   # Performance analysis
│   ├── metrics.py              # Sharpe, drawdown, CAGR, volatility
│   └── visualizations.py       # 5-panel matplotlib visualizations
│
├── data/                        # Data management
│   ├── cache.py                # Parquet-based historical data caching
│   └── preprocessing.py        # Data alignment and quality validation
│
├── scripts/                     # Executable scripts
│   └── run_hrp_backtest.py    # Main backtest execution (--refresh flag)
│
├── examples/                    # Working examples
│   ├── basic_connection.py     # Connect to IB
│   ├── fetch_historical_data.py # Fetch market data
│   ├── monitor_positions.py    # Real-time position tracking
│   └── portfolio_realtime.py   # Live portfolio monitoring
│
├── tests/                       # Unit and integration tests
│   ├── test_connection.py
│   ├── test_market_data.py
│   └── test_portfolio.py
│
├── references/                  # Reference implementations
│   └── Hierarchical-Risk-Parity/
│       └── Hierarchical Clustering.ipynb
│
└── pyproject.toml              # Project configuration
```

## Troubleshooting

### Connection Issues

**Problem:** `ConnectionException: Failed to connect`

**Solutions:**
- Ensure IB Gateway/TWS is running and logged in
- Check that API connections are enabled in settings
- Verify the port number matches your configuration:
  - Paper trading: 7497 (TWS) or 4001 (Gateway)
  - Live trading: 7496 (TWS) or 4002 (Gateway)
- Check that `127.0.0.1` is in trusted IPs

### Rate Limiting

**Problem:** `RateLimitException` or pacing violations

**Solutions:**
- System automatically handles 50 requests per 10 minutes
- For batch operations, use `concurrent=False`
- Use data caching (default: fast mode uses cache)
- Only use `--refresh` flag when you need fresh data

### Backtest Issues

**Problem:** "Insufficient data" or "Cannot calculate HRP"

**Solutions:**
- Ensure all symbols have at least 252 days of data
- Check cached data: `ls data/cache/`
- Refresh data: `python scripts/run_hrp_backtest.py --refresh`
- Verify data quality: check for gaps >10 days

**Problem:** Negative cash balance (leverage bug)

**Solutions:**
- Check `results/transactions.csv` for unusual trades
- Verify rebalancing is using correct portfolio values
- Ensure portfolio_state calculations are correct

### Data Quality

**Problem:** Data appears "flat" or unrealistic

**Solutions:**
- Check cached parquet files are current
- Use `--refresh` flag to get fresh IB data
- Verify symbols are correct (case-sensitive)
- Check currency is set to GBP for UK ETFs

### Visualization Issues

**Problem:** Plot not displaying or saving

**Solutions:**
- Ensure matplotlib backend works: `matplotlib.use('Agg')`
- Check file path is writable
- Verify all required data is available (weights, attribution)

## Future Enhancements

Planned improvements for future releases:

- [ ] Additional strategies (minimum variance, risk parity, mean-variance)
- [ ] Parameter sensitivity analysis (lookback windows, rebalance frequencies)
- [ ] Advanced risk constraints (sector limits, max position size)
- [ ] Live trading integration (automatic order generation/submission)
- [ ] Web dashboard (real-time monitoring of backtest results)
- [ ] Additional benchmarks (market-cap weighted, 60/40 allocation)
- [ ] Portfolio performance attribution analysis
- [ ] Scenario analysis and stress testing
- [ ] Factor analysis (value, momentum, size, quality factors)
- [ ] Multi-currency support with FX hedging

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Make changes and add tests
4. Format code: `black` and `isort`
5. Commit: `git commit -m 'Add feature description'`
6. Push and create Pull Request

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## References

### Academic Papers

- **HRP Algorithm**: De Prado, M. L. (2016). "Building Diversified Portfolios that Outperform Out of Sample"
- **Hierarchical Clustering**: Ward, J. H. (1963). "Hierarchical Grouping to Optimize an Objective Function"

### Documentation

- [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)
- [ib_insync Documentation](https://ib-insync.readthedocs.io/)
- [scikit-learn Hierarchical Clustering](https://scikit-learn.org/stable/modules/clustering.html#hierarchical-clustering)

## Acknowledgments

- Built on [ib_insync](https://github.com/erdewit/ib_insync) by Ewald de Wit
- Interactive Brokers for providing comprehensive market data API
- The open-source Python community (pandas, numpy, scipy, matplotlib)

## Disclaimer

**For Educational Purposes Only**: This software is provided for research and educational purposes. Do not use for actual trading without:

- ✅ Understanding the algorithm and backtesting methodology
- ✅ Validating results with multiple market conditions
- ✅ Testing in paper trading mode before live trading
- ✅ Understanding the risks of algorithmic trading
- ✅ Consulting with a financial advisor

The authors are not responsible for any financial losses incurred through the use of this software.

---

**Status**: ✅ Production Ready (v0.1.0) | **Last Updated**: February 2026

**Not affiliated with or endorsed by Interactive Brokers**
