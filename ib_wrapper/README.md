# ib_wrapper/

Async wrapper around the Interactive Brokers API (`ib_insync`). Handles connection, market data, and portfolio queries. **Read-only for trading** — this layer never places orders.

- `connection.py` — connect/disconnect and session lifecycle against IB Gateway/TWS
- `client.py` — high-level client that composes the pieces below
- `market_data.py` — historical and real-time price requests
- `portfolio.py` — account summary and positions (requires a live connection on port 4001)
- `models.py` — typed data models for contracts, bars, positions
- `config.py` — host/port/client-id config (from `.env`)
- `exceptions.py`, `utils.py` — error types and helpers

See [../docs/project.md](../docs/project.md) for IB setup.
