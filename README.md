# Interactive Brokers Python Wrapper

A modern, asyncio-based Python wrapper for the Interactive Brokers API using `ib_insync`. Provides simple access to market data, positions, and real-time portfolio updates.

## Features

- ✅ **Historical Market Data** - Fetch OHLCV bars with automatic rate limiting
- ✅ **Portfolio Management** - Get positions, account summary, and real-time updates
- ✅ **Real-time PnL Tracking** - Subscribe to account and position-level PnL streams
- ✅ **Async-First Design** - Built on `asyncio` for efficient concurrent operations
- ✅ **Type-Safe** - Full type hints for IDE support and validation
- ✅ **Rate Limiting** - Automatic compliance with IB API limits (50 req/10 min)
- ✅ **Reconnection Logic** - Automatic reconnection with exponential backoff
- ✅ **Clean API** - Simple, Pythonic interface to IB functionality

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

## Quick Start

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
        # Fetch 1 day of 1-minute bars for AAPL
        bars = await client.get_historical_bars(
            symbol="AAPL",
            duration="1 D",
            bar_size="1 min"
        )

        print(f"Received {len(bars)} bars")
        print(bars.head())

asyncio.run(main())
```

### Monitor Portfolio

```python
import asyncio
from ib_wrapper import IBClient

async def main():
    async with IBClient() as client:
        # Get current positions
        positions = await client.get_positions()
        for pos in positions:
            print(f"{pos.symbol}: {pos.position} shares")
            print(f"  Unrealized PnL: ${pos.unrealized_pnl:,.2f}")

        # Get account summary
        summary = await client.get_account_summary()
        print(f"\nNet Liquidation: ${summary['NetLiquidation']:,.2f}")
        print(f"Buying Power: ${summary['BuyingPower']:,.2f}")

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

        client.subscribe_portfolio_updates(on_update)

        # Keep running to receive updates
        await asyncio.sleep(60)

asyncio.run(main())
```

## Configuration

### Using Environment Variables

Create a `.env` file in your project root:

```env
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
IB_ACCOUNT=DU123456
LOG_LEVEL=INFO
```

### Using YAML Config File

Create `config/my_config.yaml`:

```yaml
ib_connection:
  host: "127.0.0.1"
  port: 7497
  client_id: 1

logging:
  level: "INFO"
  file: "logs/trading.log"
```

Load it in your code:

```python
from ib_wrapper import IBClient, Config

config = Config(config_path="config/my_config.yaml")
client = IBClient(config)
```

### Configuration Priority

1. Environment variables (highest priority)
2. YAML config file
3. Default values (lowest priority)

## API Reference

### IBClient

Main client class providing unified access to IB functionality.

#### Connection Methods

- `connect()` - Connect to IB Gateway/TWS
- `disconnect()` - Disconnect from IB
- `is_connected()` - Check connection status

#### Market Data Methods

- `get_historical_bars(symbol, duration, bar_size, **kwargs)` - Fetch historical bars
- `get_multiple_historical_bars(symbols, duration, bar_size, **kwargs)` - Fetch data for multiple symbols
- `download_extended_history(symbol, start_date, end_date, **kwargs)` - Download extended history
- `get_remaining_requests()` - Get remaining API requests in rate limit window

#### Portfolio Methods

- `get_positions()` - Get current positions
- `get_account_summary(account, tags)` - Get account summary
- `get_account_values(account)` - Get detailed account values
- `subscribe_portfolio_updates(callback)` - Subscribe to real-time portfolio updates
- `unsubscribe_portfolio_updates()` - Unsubscribe from portfolio updates
- `subscribe_pnl(account, callback)` - Subscribe to account-level PnL
- `subscribe_pnl_single(account, contract_id, callback)` - Subscribe to position-level PnL
- `unsubscribe_all_pnl()` - Unsubscribe from all PnL updates

### Data Models

#### Position
```python
@dataclass
class Position:
    symbol: str
    contract_id: int
    position: float
    market_price: float
    market_value: float
    average_cost: float
    unrealized_pnl: float
    realized_pnl: float
    account: str
```

#### PortfolioUpdate
```python
@dataclass
class PortfolioUpdate:
    timestamp: datetime
    position: Position
    update_type: str  # 'new', 'modified', 'deleted'
```

#### PnLUpdate
```python
@dataclass
class PnLUpdate:
    account: str
    daily_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    timestamp: datetime
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

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ib_wrapper --cov-report=html

# Run specific test file
pytest tests/test_connection.py -v
```

## Development

### Code Formatting

```bash
# Format code with black
black ib_wrapper/ tests/ examples/

# Sort imports with isort
isort ib_wrapper/ tests/ examples/

# Lint with flake8
flake8 ib_wrapper/ tests/ examples/

# Type check with mypy
mypy ib_wrapper/
```

### Project Structure

```
PersonalTrading/
├── ib_wrapper/           # Main package
│   ├── __init__.py       # Public API exports
│   ├── client.py         # Main IBClient class
│   ├── connection.py     # Connection management
│   ├── market_data.py    # Historical data service
│   ├── portfolio.py      # Portfolio service
│   ├── models.py         # Data models
│   ├── config.py         # Configuration management
│   ├── exceptions.py     # Custom exceptions
│   └── utils.py          # Helper functions
├── examples/             # Usage examples
├── tests/                # Test suite
├── config/               # Configuration files
├── logs/                 # Log files (gitignored)
└── pyproject.toml        # Project metadata and dependencies
```

## Troubleshooting

### Connection Issues

**Problem:** `ConnectionException: Failed to connect`

**Solutions:**
- Ensure IB Gateway/TWS is running and logged in
- Check that API connections are enabled in settings
- Verify the port number matches your IB Gateway/TWS configuration
- Check that your IP is in the trusted IPs list (127.0.0.1)

### Rate Limiting

**Problem:** `RateLimitException` or pacing violations

**Solutions:**
- The wrapper automatically handles rate limiting (50 requests per 10 minutes)
- Use `client.get_remaining_requests()` to check remaining quota
- For batch operations, use `concurrent=False` to fetch sequentially
- Consider using larger bar sizes (e.g., '1 day' instead of '1 min') for historical data

### No Data Returned

**Problem:** Empty DataFrame returned from `get_historical_bars()`

**Solutions:**
- Check that the symbol is valid and tradable
- Verify market hours (use `use_rth=False` for extended hours)
- Ensure you have market data subscription for the security type
- Try a different duration or bar size

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on [ib_insync](https://github.com/erdewit/ib_insync) by Ewald de Wit
- Interactive Brokers for providing the API

## Disclaimer

This software is for educational and research purposes only. Do not use it for actual trading without understanding the risks involved. The authors are not responsible for any financial losses incurred through the use of this software.

---

**Note:** This wrapper is not affiliated with or endorsed by Interactive Brokers.
