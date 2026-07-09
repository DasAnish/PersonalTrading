"""Historical data fetching for the backtest CLI (IB with parquet-cache fallback).

The IB connection is opened **lazily**: when the parquet cache already covers
every requested symbol (the common case for ``--use-definitions`` backtests),
no socket is opened at all. A connection is established only on the first
cache-miss, or when ``refresh=True`` forces a fresh fetch. This avoids the
connection flood that arose from every backtester/analyst subprocess eagerly
opening its own IB socket (each with a distinct random clientId).
"""

import logging

from ib_wrapper.client import IBClient
from ib_wrapper.config import Config
from data import HistoricalDataCache

from .config import (
    BAR_SIZE,
    CURRENCY,
    END_DATE,
    EXCHANGE,
    SEC_TYPE,
    START_DATE,
    SYMBOL_SPECS,
    SYMBOLS,
)

logger = logging.getLogger(__name__)


async def fetch_historical_data(
    config: Config, cache: HistoricalDataCache, refresh: bool = False
):
    """
    Fetch historical data for all symbols, connecting to IB only when needed.

    Args:
        config: IB configuration used to build a client on the first cache-miss.
        cache: HistoricalDataCache instance
        refresh: If True, force fresh data from IB (skip cache). If False, use
            cache if available and open a connection only for missing symbols.

    Returns:
        Dict mapping symbol to DataFrame
    """
    logger.info("=" * 60)
    if refresh:
        logger.info("FETCHING FRESH DATA FROM INTERACTIVE BROKERS (CACHE SKIPPED)")
    else:
        logger.info("FETCHING HISTORICAL DATA (USING CACHE IF AVAILABLE)")
    logger.info("=" * 60)

    data_dict = {}
    client = None  # opened lazily on first cache-miss / refresh
    ib_unavailable = False  # set after a failed connect; don't retry per symbol

    async def _get_client():
        nonlocal client, ib_unavailable
        if ib_unavailable:
            raise ConnectionError("IB Gateway unavailable (earlier connect failed)")
        if client is None:
            logger.info("Cache miss — opening IB connection for live fetch...")
            candidate = IBClient(config)
            try:
                await candidate.connect()
            except Exception:
                ib_unavailable = True
                raise
            client = candidate
            logger.info("✓ Connected to IB")
        return client

    try:
        for symbol in SYMBOLS:
            logger.info(f"\nFetching {symbol}...")
            # Per-asset contract params: several assets quote in EUR/USD/CHF,
            # and a GBP-currency request for them matches no contract.
            spec = SYMBOL_SPECS.get(
                symbol,
                {"currency": CURRENCY, "exchange": EXCHANGE, "sec_type": SEC_TYPE},
            )

            try:
                if refresh:
                    # Force fresh fetch from IB, skip cache
                    logger.info("  (fetching fresh from IB...)")
                    c = await _get_client()
                    df = await c.market_data.download_extended_history(
                        symbol=symbol,
                        start_date=START_DATE,
                        end_date=END_DATE,
                        bar_size=BAR_SIZE,
                        sec_type=spec["sec_type"],
                        exchange=spec["exchange"],
                        currency=spec["currency"],
                    )
                    # Save to cache for future use
                    if not df.empty:
                        cache.save_cached_data(symbol, df, START_DATE, END_DATE)
                else:
                    # Cache-first: only touch IB if this symbol is missing.
                    # The requested range rolls daily, so allow a few days of
                    # slack before declaring a miss.
                    df = cache.load_cached_data(
                        symbol, START_DATE, END_DATE, tolerance_days=7
                    )
                    if df.empty:
                        try:
                            c = await _get_client()
                            df = await cache.get_or_fetch_data(
                                symbol=symbol,
                                start_date=START_DATE,
                                end_date=END_DATE,
                                market_data_service=c.market_data,
                                bar_size=BAR_SIZE,
                                sec_type=spec["sec_type"],
                                exchange=spec["exchange"],
                                currency=spec["currency"],
                            )
                        except Exception as ib_err:
                            # IB unreachable: fall back to newest cached file
                            # regardless of range/age. Stale beats absent for
                            # offline runs; load_best_cached_data logs how far
                            # behind the data is.
                            logger.warning(
                                f"IB fetch failed for {symbol} ({ib_err}); "
                                f"trying stale cache fallback..."
                            )
                            df = cache.load_best_cached_data(symbol)
                            if df.empty:
                                raise

                if not df.empty:
                    data_dict[symbol] = df
                    logger.info(
                        f"✓ {symbol}: {len(df)} days "
                        f"({df.index[0].date()} to {df.index[-1].date()})"
                    )
                else:
                    logger.warning(f"✗ {symbol}: No data received")

            except Exception as e:
                logger.error(f"✗ {symbol}: Failed to fetch - {e}")

        if client is None:
            logger.info("All symbols served from cache — no IB connection opened.")
    finally:
        if client is not None:
            client.disconnect()

    return data_dict
