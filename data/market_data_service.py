"""
Market data singleton service for PersonalTrading.

This module provides centralized market data management. The singleton handles:
- Fetching historical data from Interactive Brokers
- Caching with parquet format
- Providing pre-sliced data contexts to strategies

Key insight: Strategies never calculate lookback windows. The singleton
handles all data slicing, ensuring strategies receive properly windowed data.

Usage:
    # Initialize singleton (once per application)
    from ib_wrapper.client import IBClient
    from data.market_data_service import MarketDataService

    async with IBClient(...) as client:
        mds = MarketDataService()
        mds.configure(ib_client=client, cache_dir='data/cache')

        # Fetch data for a strategy's requirements
        requirements = my_strategy.get_data_requirements()
        all_data = await mds.fetch_data(
            requirements=requirements,
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
            refresh=False
        )

        # Get context for specific date (with lookback window)
        context = mds.get_context_for_date(
            all_data=all_data,
            current_date=datetime(2020, 6, 1),
            lookback_days=252
        )

        # Strategy receives pre-sliced data in context
        weights = my_strategy.calculate_weights(context)
"""

from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Singleton service for all market data access.

    Responsibilities:
    - Fetch and cache price data from Interactive Brokers
    - Manage historical data storage and retrieval
    - Provide properly sliced data contexts to strategies
    - Handle data alignment and validation

    This singleton centralizes data management so strategies don't need to
    know about lookback windows, data fetching, or caching.
    """

    _instance: Optional[MarketDataService] = None

    def __new__(cls):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize singleton (only runs once)."""
        if self._initialized:
            return

        self._cache: Dict[str, pd.DataFrame] = {}
        self._ib_client: Optional['IBClient'] = None
        self._data_cache: Optional['HistoricalDataCache'] = None
        self._initialized = True

        logger.info("MarketDataService singleton initialized")

    def configure(
        self,
        ib_client: 'IBClient',
        cache_dir: str = 'data/cache'
    ):
        """
        Configure the singleton with IB client and cache.

        Must be called once before using fetch_data().

        Args:
            ib_client: IBClient instance for fetching from Interactive Brokers
            cache_dir: Directory for parquet cache (created if doesn't exist)

        Raises:
            ImportError: If HistoricalDataCache cannot be imported
        """
        from data.cache import HistoricalDataCache

        self._ib_client = ib_client
        self._data_cache = HistoricalDataCache(cache_dir)

        logger.info(f"MarketDataService configured with cache at {cache_dir}")

    async def fetch_data(
        self,
        requirements: 'DataRequirements',
        start_date: datetime,
        end_date: datetime,
        refresh: bool = False
    ) -> pd.DataFrame:
        """
        Fetch and align price data for strategy requirements.

        Automatically includes lookback period before start_date. Data is
        cached and reused across multiple strategies.

        Args:
            requirements: DataRequirements from strategy (symbols, lookback, etc.)
            start_date: Start date for backtest period
            end_date: End date for backtest period
            refresh: If True, skip cache and fetch fresh from IB

        Returns:
            DataFrame with columns=symbols, index=dates, values=prices.
            Data includes lookback_days before start_date.

        Raises:
            ValueError: If no data could be fetched
            ConnectionError: If IB connection fails and no cache available
        """
        if not self._ib_client or not self._data_cache:
            raise RuntimeError(
                "MarketDataService not configured. Call configure(ib_client, cache_dir) first."
            )

        # Calculate actual fetch range (include lookback before start_date)
        actual_start = start_date - timedelta(days=requirements.lookback_days)

        # Generate cache key
        cache_key = self._make_cache_key(requirements, actual_start, end_date)

        # Check in-memory cache
        if not refresh and cache_key in self._cache:
            logger.info(f"Using in-memory cached data for {cache_key}")
            return self._cache[cache_key]

        # Fetch from IB (or disk cache)
        logger.info(
            f"Fetching data for {len(requirements.symbols)} symbols "
            f"from {actual_start.date()} to {end_date.date()}"
        )

        data_dict = {}
        failed_symbols = []

        for symbol in requirements.symbols:
            try:
                # Try to fetch from disk cache or IB
                df = await self._data_cache.get_or_fetch_data(
                    symbol=symbol,
                    start_date=actual_start,
                    end_date=end_date,
                    market_data_service=self._ib_client.market_data,
                    currency=requirements.currency,
                    exchange=requirements.exchange,
                    sec_type=requirements.sec_type,
                    bar_size=requirements.frequency
                )

                if not df.empty and 'close' in df.columns:
                    data_dict[symbol] = df['close']
                    logger.debug(f"Fetched {len(df)} rows for {symbol}")
                else:
                    failed_symbols.append(symbol)
                    logger.warning(f"No data for {symbol}")

            except Exception as e:
                failed_symbols.append(symbol)
                logger.error(f"Failed to fetch {symbol}: {e}")

        # Validate we got at least some data
        if not data_dict:
            raise ValueError(
                f"Could not fetch any data. Failed symbols: {failed_symbols}"
            )

        # Warn about partial failures
        if failed_symbols:
            logger.warning(
                f"Successfully fetched {len(data_dict)}/{len(requirements.symbols)} symbols. "
                f"Failed: {failed_symbols}"
            )

        # Align data to common dates
        aligned_df = self._align_dataframes(data_dict)

        if aligned_df.empty:
            raise ValueError("No aligned data after merging symbol data")

        # Cache result in memory
        self._cache[cache_key] = aligned_df

        logger.info(
            f"Successfully fetched and aligned {len(aligned_df)} dates "
            f"for {len(aligned_df.columns)} symbols"
        )

        return aligned_df

    def get_context_for_date(
        self,
        all_data: pd.DataFrame,
        current_date: datetime,
        lookback_days: int
    ) -> 'StrategyContext':
        """
        Create StrategyContext for a specific date.

        This is the key method that handles all lookback window calculations.
        Strategies never see full historical data - they always receive
        pre-sliced contexts with proper lookback windows.

        Args:
            all_data: Full DataFrame from fetch_data()
            current_date: Current rebalance date
            lookback_days: How much history to include in window

        Returns:
            StrategyContext with properly sliced prices and dates

        Raises:
            ValueError: If insufficient data before current_date
        """
        from strategies.core import StrategyContext

        # Calculate lookback start date
        lookback_start = current_date - timedelta(days=lookback_days)

        # Slice data: from lookback_start up to and including current_date
        # This prevents lookahead bias (no future data)
        sliced_data = all_data[
            (all_data.index >= lookback_start) &
            (all_data.index <= current_date)
        ]

        # Validate sufficient data
        if sliced_data.empty:
            raise ValueError(
                f"No data available for {current_date.date()} "
                f"with lookback from {lookback_start.date()}. "
                f"Available data range: {all_data.index[0]} to {all_data.index[-1]}"
            )

        # Create context
        context = StrategyContext(
            current_date=current_date,
            lookback_start=lookback_start,
            prices=sliced_data,
            portfolio_values=None,  # Set by overlay strategies if needed
            metadata={}
        )

        logger.debug(
            f"Created context for {current_date.date()} "
            f"with {len(sliced_data)} rows of data"
        )

        return context

    def _align_dataframes(self, data_dict: Dict[str, pd.Series]) -> pd.DataFrame:
        """
        Align multiple symbol price series to a single DataFrame.

        Handles:
        - Converting dict of Series to single DataFrame
        - Finding common date range (intersection)
        - Forward filling short gaps (max 3 days)
        - Removing remaining NaN rows

        Args:
            data_dict: Dict mapping symbol -> pd.Series of prices

        Returns:
            DataFrame with columns=symbols, index=dates
        """
        # Convert to DataFrame
        df = pd.DataFrame(data_dict)

        # Forward fill for up to 3 days (handle short gaps)
        df = df.fillna(method='ffill', limit=3)

        # Drop remaining rows with any NaN
        df = df.dropna()

        # Sort by index
        df = df.sort_index()

        logger.debug(f"Aligned to {len(df)} common dates for {len(df.columns)} symbols")

        return df

    def _make_cache_key(
        self,
        requirements: 'DataRequirements',
        start: datetime,
        end: datetime
    ) -> str:
        """Generate cache key from requirements and dates."""
        symbols_key = '_'.join(sorted(requirements.symbols))
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')
        return f"{symbols_key}_{start_str}_{end_str}"

    @classmethod
    def reset(cls):
        """
        Reset singleton to initial state.

        Useful for testing. Clears all cached data and resets configuration.
        """
        cls._instance = None
        logger.info("MarketDataService singleton reset")


def get_market_data() -> MarketDataService:
    """
    Get the MarketDataService singleton instance.

    Convenience function for accessing the singleton.

    Returns:
        MarketDataService singleton instance
    """
    return MarketDataService()
