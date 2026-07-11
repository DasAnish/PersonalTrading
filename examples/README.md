# examples/

Standalone runnable scripts showing how to use the IB wrapper directly. Learning/reference material, not part of the backtest pipeline.

- `basic_connection.py` — connect to IB Gateway and disconnect
- `example_symbol.py` — build and qualify a contract
- `fetch_historical_data.py` — request historical bars
- `query_positions.py` / `monitor_positions.py` — read and watch portfolio positions
- `portfolio_realtime.py` — stream real-time portfolio updates

Requires a live IB connection unless noted. These do **not** place orders.
