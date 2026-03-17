# MCP Tools (ib-trading server)

Claude Code has direct access to these tools via the `ib-trading` MCP server (registered in `.mcp.json`).

Market data tools fall back to the local parquet cache (`data/cache/`) when IB Gateway is offline. Portfolio tools require a live IB connection on port 4001.

## Available Tools

| Tool | Requires IB | Description |
|------|-------------|-------------|
| `get_account_summary` | Yes | Live account values |
| `get_positions` | Yes | Current portfolio holdings |
| `get_historical_data` | No (cached) | OHLCV history for a single symbol |
| `get_multiple_historical_data` | No (cached) | Concurrent fetch for multiple symbols |
| `list_strategies` | No | List all registered and JSON-defined strategies |
| `run_backtest` | No | Run a backtest and return results |
| `get_backtest_results` | No | Load saved results from `results/` |

## Notes

- IB Gateway port: **4001** (paper trading)
- Always use `currency='GBP'` for UK ETFs
- `get_multiple_historical_data` fetches symbols concurrently via `asyncio.gather`
- Backtest results are saved to `results/strategies/<key>/`
