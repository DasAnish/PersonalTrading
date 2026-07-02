"""
Historical data caching utilities.

This module provides caching functionality to avoid repeatedly fetching
the same historical data from Interactive Brokers, which helps avoid
rate limit issues during development and testing.
"""

import os
import re
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_CACHE_FILENAME_RE = re.compile(
    r"^(?P<symbol>.+)_(?P<start>\d{8})_(?P<end>\d{8})\.parquet$"
)


class HistoricalDataCache:
    """
    Cache for historical market data.

    Stores data in parquet format for fast loading and efficient storage.
    Files are named: {symbol}_{start_date}_{end_date}.parquet
    """

    def __init__(self, cache_dir: str = "data/cache"):
        """
        Initialize cache.

        Args:
            cache_dir: Directory to store cached data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(
        self, symbol: str, start_date: datetime, end_date: datetime
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
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        filename = f"{symbol}_{start_str}_{end_str}.parquet"
        return self.cache_dir / filename

    @staticmethod
    def _parse_cache_filename(path: Path):
        """
        Parse the {symbol}_{start_date}_{end_date}.parquet filename scheme.

        Args:
            path: Candidate cache file path

        Returns:
            Tuple of (start_date, end_date) as datetime objects, or None if
            the filename doesn't match the expected scheme.
        """
        match = _CACHE_FILENAME_RE.match(path.name)
        if not match:
            return None
        try:
            candidate_start = datetime.strptime(match.group("start"), "%Y%m%d")
            candidate_end = datetime.strptime(match.group("end"), "%Y%m%d")
        except ValueError:
            return None
        return candidate_start, candidate_end

    def load_cached_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        max_age_days: int = 7,
        allow_fuzzy: bool = True,
    ) -> pd.DataFrame:
        """
        Load data from cache if available and recent enough.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date
            max_age_days: Maximum age of cache file in days (default 7)
            allow_fuzzy: If True (default), fall back to another cached file
                for this symbol when an exact date-range match doesn't exist,
                as long as its date range covers the requested end date. If
                False, only an exact filename match is considered.

        Returns:
            DataFrame if cache hit, empty DataFrame if cache miss
        """
        cache_path = self._get_cache_path(symbol, start_date, end_date)

        if not cache_path.exists():
            if not allow_fuzzy:
                logger.debug(f"Cache miss: {cache_path.name}")
                return pd.DataFrame()

            # Fuzzy fallback: consider other cached files for this symbol,
            # but only accept one whose date range actually covers the
            # requested range (most-recently-modified first).
            candidates = sorted(
                self.cache_dir.glob(f"{symbol}_*.parquet"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            fuzzy_match = None
            for candidate in candidates:
                parsed = self._parse_cache_filename(candidate)
                if parsed is None:
                    continue
                candidate_start, candidate_end = parsed
                if candidate_start <= start_date and candidate_end >= end_date:
                    fuzzy_match = candidate
                    break

            if fuzzy_match is None:
                logger.debug(f"Cache miss: {cache_path.name}")
                return pd.DataFrame()

            requested_range = f"{start_date.date()}..{end_date.date()}"
            actual_start, actual_end = self._parse_cache_filename(fuzzy_match)
            actual_range = f"{actual_start.date()}..{actual_end.date()}"
            logger.warning(
                f"Cache fuzzy hit for {symbol}: using {fuzzy_match.name} "
                f"(requested {requested_range}, file covers {actual_range})"
            )
            cache_path = fuzzy_match

        # Check cache age
        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if cache_age > timedelta(days=max_age_days):
            logger.debug(
                f"Cache expired: {cache_path.name} (age: {cache_age.days} days)"
            )
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
        self, symbol: str, data: pd.DataFrame, start_date: datetime, end_date: datetime
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
        tmp_path = cache_path.with_suffix(".parquet.tmp")

        try:
            data.to_parquet(tmp_path)
            os.replace(tmp_path, cache_path)
            logger.info(f"Cached {len(data)} rows to {cache_path.name}")
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error(f"Failed to save cache {cache_path.name}: {e}")

    async def get_or_fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        market_data_service,
        **kwargs,
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
                symbol=symbol, start_date=start_date, end_date=end_date, **kwargs
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
