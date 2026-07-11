# mcp_server/

MCP (Model Context Protocol) server that exposes this project's capabilities to Claude as tools.

- `server.py` — defines the `ib-trading` MCP server and its tools

Tools cover market data (`get_historical_data`, `get_multiple_historical_data`), portfolio (`get_account_summary`, `get_positions`), and backtesting (`list_strategies`, `run_backtest`, `get_backtest_results`) over the 30-asset universe. Market-data tools fall back to the parquet cache when IB Gateway is offline; portfolio tools require a live connection on port 4001.

See [../docs/mcp-tools.md](../docs/mcp-tools.md) for the full tool reference.
