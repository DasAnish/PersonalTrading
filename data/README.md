# data/

Market-data access, caching, and preprocessing.

- `market_data_service.py` — fetches historical prices; pulls from IB when Gateway is up, falls back to the local parquet cache when offline
- `cache.py` — parquet cache read/write and freshness bookkeeping
- `cache/` — the parquet cache itself (per-symbol price history)
- `preprocessing.py` — cleaning, alignment, returns computation, and proxy-history splicing (extending short series with a correlated proxy)

The freshness gate in the nightly pipeline reads cache vintages from here. See [../docs/nightly.md](../docs/nightly.md).
