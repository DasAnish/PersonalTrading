"""
Historical data caching utilities.

This module provides caching functionality to avoid repeatedly fetching
the same historical data from Interactive Brokers, which helps avoid
rate limit issues during development and testing.
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class HistoricalDataCache:
    """
    Cache for historical market data.

    Stores data in parquet format for fast loading and efficient storage.
    Files are named: {symbol}_{start_date}_{end_date}.parquet
    """

    def __init__(self, cache_dir: str = 'data/cache'):
        """
        Initialize cache.

        Args:
            cache_dir: Directory to store cached data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> Path:
        """
        Get cache file path for given symbol and date range.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date

        Returns:
            Path to cache file
        """
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        filename = f"{symbol}_{start_str}_{end_str}.parquet"
        return self.cache_dir / filename

    def load_cached_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        max_age_days: int = 7
    ) -> pd.DataFrame:
        """
        Load data from cache if available and recent enough.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date
            max_age_days: Maximum age of cache file in days (default 7)

        Returns:
            DataFrame if cache hit, empty DataFrame if cache miss
        """
        cache_path = self._get_cache_path(symbol, start_date, end_date)

        if not cache_path.exists():
            logger.debug(f"Cache miss: {cache_path.name}")
            return pd.DataFrame()

        # Check cache age
        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if cache_age > timedelta(days=max_age_days):
            logger.debug(f"Cache expired: {cache_path.name} (age: {cache_age.days} days)")
            return pd.DataFrame()

        # Load cached data
        try:
            df = pd.read_parquet(cache_path)
            logger.info(f"Cache hit: {cache_path.name} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.error(f"Failed to load cache {cache_path.name}: {e}")
            return pd.DataFrame()

    def save_cached_data(
        self,
        symbol: str,
        data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime
    ):
        """
        Save data to cache.

        Args:
            symbol: Ticker symbol
            data: DataFrame to cache
            start_date: Start date of data
            end_date: End date of data
        """
        if data.empty:
            logger.warning(f"Not caching empty DataFrame for {symbol}")
            return

        cache_path = self._get_cache_path(symbol, start_date, end_date)

        try:
            data.to_parquet(cache_path)
            logger.info(f"Cached {len(data)} rows to {cache_path.name}")
        except Exception as e:
            logger.error(f"Failed to save cache {cache_path.name}: {e}")

    async def get_or_fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        market_data_service,
        **kwargs
    ) -> pd.DataFrame:
        """
        Get data from cache or fetch if not available.

        This is the main method to use for getting historical data with caching.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date
            market_data_service: MarketDataService instance for fetching
            **kwargs: Additional arguments to pass to download_extended_history

        Returns:
            DataFrame with historical data

        Example:
            >>> cache = HistoricalDataCache()
            >>> data = await cache.get_or_fetch_data(
            ...     'VUSA',
            ...     datetime(2020, 1, 1),
            ...     datetime(2024, 1, 1),
            ...     market_data_service,
            ...     currency='GBP',
            ...     bar_size='1 day'
            ... )
        """
        # Try cache first
        cached = self.load_cached_data(symbol, start_date, end_date)

        if not cached.empty:
            return cached

        # Cache miss - fetch from IB
        logger.info(f"Fetching {symbol} from {start_date.date()} to {end_date.date()}")

        try:
            data = await market_data_service.download_extended_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                **kwargs
            )

            # Save to cache
            if not data.empty:
                self.save_cached_data(symbol, data, start_date, end_date)

            return data

        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
            return pd.DataFrame()

    def clear_cache(self, symbol: str = None):
        """
        Clear cache files.

        Args:
            symbol: If provided, clear only this symbol's cache.
                   If None, clear all cache files.
        """
        if symbol:
            pattern = f"{symbol}_*.parquet"
        else:
            pattern = "*.parquet"

        removed = 0
        for cache_file in self.cache_dir.glob(pattern):
            try:
                cache_file.unlink()
                removed += 1
            except Exception as e:
                logger.error(f"Failed to remove {cache_file.name}: {e}")

        logger.info(f"Removed {removed} cache files")
