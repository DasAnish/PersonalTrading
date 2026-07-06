"""Historical data fetching for the backtest CLI (IB with parquet-cache fallback)."""

import logging

from ib_wrapper.client import IBClient
from data import HistoricalDataCache

from .config import (
    BAR_SIZE,
    CURRENCY,
    END_DATE,
    EXCHANGE,
    SEC_TYPE,
    START_DATE,
    SYMBOLS,
)

logger = logging.getLogger(__name__)


async def fetch_historical_data(
    client: IBClient, cache: HistoricalDataCache, refresh: bool = False
):
    """
    Fetch historical data for all symbols.

    Args:
        client: IBClient instance
        cache: HistoricalDataCache instance
        refresh: If True, force fresh data from IB (skip cache). If False, use cache if available.

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

    for symbol in SYMBOLS:
        logger.info(f"\nFetching {symbol}...")

        try:
            if refresh:
                # Force fresh fetch from IB, skip cache
                logger.info("  (fetching fresh from IB...)")
                df = await client.market_data.download_extended_history(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    bar_size=BAR_SIZE,
                    sec_type=SEC_TYPE,
                    exchange=EXCHANGE,
                    currency=CURRENCY,
                )
                # Save to cache for future use
                if not df.empty:
                    cache.save_cached_data(symbol, df, START_DATE, END_DATE)
            else:
                # Use cache-aware fetch (faster, uses existing data if available)
                df = await cache.get_or_fetch_data(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    market_data_service=client.market_data,
                    bar_size=BAR_SIZE,
                    sec_type=SEC_TYPE,
                    exchange=EXCHANGE,
                    currency=CURRENCY,
                )

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

    return data_dict
