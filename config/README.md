# config/

Static configuration consumed at runtime.

- `default_config.yaml` — default backtest settings (costs, rebalance frequency, lookbacks, etc.)
- `price_units.json` — per-symbol price-unit metadata (handles pence-vs-pounds / scaling quirks)
- `preferred_blend.json` — the currently preferred strategy blend used by reporting/meta-portfolio

Runtime secrets (IB host/port/client-id) live in `.env`, **not** here.
