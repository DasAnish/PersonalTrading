"""
Historical data caching utilities.

This module provides caching functionality to avoid repeatedly fetching
the same historical data from Interactive Brokers, which helps avoid
rate limit issues during development and testing.
"""

import json
import os
import re
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

PRICE_UNITS_PATH = Path("config") / "price_units.json"

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
        tolerance_days: int = 0,
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
            tolerance_days: Slack (days) allowed on both ends of the fuzzy
                coverage check. The requested range rolls forward daily
                (END_DATE = yesterday), so a file cached a couple of days ago
                never covers it exactly; a small tolerance keeps those files
                usable without an IB round-trip.

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
                slack = timedelta(days=tolerance_days)
                if (
                    candidate_start <= start_date + slack
                    and candidate_end >= end_date - slack
                ):
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

    def load_best_cached_data(self, symbol: str) -> pd.DataFrame:
        """
        Last-resort offline fallback: load the cached file with the latest
        end date for ``symbol``, ignoring requested range and file age.

        Intended for when IB is unreachable and stale data beats no data
        (e.g. overnight analysis runs). Callers should surface the staleness
        to the user — a lagging symbol truncates the aligned panel in
        ``align_dataframes``.

        Returns:
            DataFrame from the newest-ending cache file, or empty DataFrame
            if no parseable cache file exists for the symbol.
        """
        candidates = []
        for path in self.cache_dir.glob(f"{symbol}_*.parquet"):
            parsed = self._parse_cache_filename(path)
            if parsed is not None:
                candidates.append((parsed[1], path))
        if not candidates:
            return pd.DataFrame()

        end, best = max(candidates, key=lambda c: c[0])
        try:
            df = pd.read_parquet(best)
        except Exception as e:
            logger.error(f"Failed to load cache {best.name}: {e}")
            return pd.DataFrame()

        lag = (datetime.now() - end).days
        logger.warning(
            f"STALE cache fallback for {symbol}: {best.name} "
            f"(data ends {end.date()}, {lag} days behind today)"
        )
        return df

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


def latest_cached_close(symbol: str, cache_dir: str = "data/cache"):
    """Latest cached close price for a symbol, or None if unavailable.

    Reads the most recently modified ``<symbol>_*.parquet`` file and returns
    the last finite, positive close. Used to backfill position values when IB
    returns a zero/NaN market price (e.g. no live market-data subscription).
    """
    directory = Path(cache_dir)
    candidates = sorted(
        directory.glob(f"{symbol}_*.parquet"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if df.empty:
            continue
        col = "close" if "close" in df.columns else df.columns[-1]
        value = df[col].iloc[-1]
        if pd.notna(value) and value > 0:
            return float(value)
    return None


def load_price_units(path: Path = PRICE_UNITS_PATH) -> dict:
    """Load the per-symbol price-unit / FX config (empty if absent/invalid)."""
    if not Path(path).exists():
        return {"scale_to_base": {}, "manual_close": {}}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read price units %s: %s", path, exc)
        return {"scale_to_base": {}, "manual_close": {}}
    data.setdefault("scale_to_base", {})
    data.setdefault("manual_close", {})
    return data


def close_price_base(symbol: str, units: dict = None, cache_dir: str = "data/cache"):
    """Per-share close in the base currency, or None if unavailable.

    Uses ``manual_close[symbol]`` if set, else the latest cached close, then
    multiplies by ``scale_to_base[symbol]`` (default 1.0) to convert the raw
    quote unit (e.g. LSE pence, or a non-GBP currency) into the base currency.
    """
    if units is None:
        units = load_price_units()
    scale = float(units.get("scale_to_base", {}).get(symbol, 1.0))
    manual = units.get("manual_close", {}).get(symbol)
    if manual is not None:
        return float(manual) * scale
    raw = latest_cached_close(symbol, cache_dir=cache_dir)
    return None if raw is None else raw * scale
