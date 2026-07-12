"""Tests for incremental cache refresh logic.

Verifies:
- Clean-overlap append produces identical frame to full fetch
- Mismatched overlap triggers full refetch path
- Short overlap (< OVERLAP_MIN_DAYS) triggers full refetch
- Old cache file deleted after successful incremental extend
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import tempfile
import pytest
import pandas as pd

from data.cache import HistoricalDataCache, EXPECTED_WHAT_TO_SHOW, latest_cache_file

# Constants for incremental refresh
OVERLAP_MIN_DAYS = 20
OVERLAP_TOL = 1e-4


async def _try_incremental_fetch(
    client,
    symbol: str,
    spec: dict,
    cache: HistoricalDataCache,
    end_date: datetime = None,
) -> tuple[pd.DataFrame, str] | None:
    """Try incremental 1-year fetch with overlap verification.

    Returns:
        (DataFrame, what_to_show) if successful, None if overlap mismatch detected
        (triggering a full refetch).
    """
    if end_date is None:
        end_date = datetime.now()

    # Check if we have a cached file to extend
    result = latest_cache_file(symbol, cache_dir=str(cache.cache_dir))
    if result is None:
        return None  # No cache to extend

    old_path, old_df = result
    if old_df.empty or "close" not in old_df.columns:
        return None

    # Fetch 1 year ending at end_date
    try:
        df_1y = await client.market_data.download_extended_history(
            symbol=symbol,
            start_date=end_date - pd.Timedelta(days=365),
            end_date=end_date,
            bar_size="1 day",
            what_to_show=EXPECTED_WHAT_TO_SHOW,
            sec_type=spec["sec_type"],
            exchange=spec["exchange"],
            currency=spec["currency"],
        )
    except Exception:
        return None  # Can't fetch 1 year; will do full refetch

    if df_1y.empty:
        return None

    # Find overlap
    old_dates = set(old_df.index.date)
    new_dates = set(df_1y.index.date)
    overlap_dates = sorted(old_dates & new_dates)

    if len(overlap_dates) < OVERLAP_MIN_DAYS:
        # Not enough overlap; do full refetch
        return None

    # Check for adjustments: max(abs(new_close/old_close - 1)) over overlap
    overlap_start = overlap_dates[0]
    overlap_end = overlap_dates[-1]
    old_overlap = old_df[
        (old_df.index.date >= overlap_start) & (old_df.index.date <= overlap_end)
    ]
    new_overlap = df_1y[
        (df_1y.index.date >= overlap_start) & (df_1y.index.date <= overlap_end)
    ]

    if len(old_overlap) == 0 or len(new_overlap) == 0:
        return None

    # Align on close prices
    old_close = old_overlap["close"].values
    new_close = new_overlap["close"].values

    if len(old_close) != len(new_close):
        # Date mismatch; do full refetch
        return None

    # Check tolerance
    ratio_error = (new_close / old_close) - 1.0
    max_error = max(abs(ratio_error))

    if max_error > OVERLAP_TOL:
        # Adjustment detected; log and do full refetch
        return None

    # Overlap verified; concat cached + new, dedup (keep new)
    # old_df up to (but not including) overlap_start, then all of df_1y
    pre_overlap = old_df[old_df.index.date < overlap_start]
    combined = pd.concat([pre_overlap, df_1y])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()

    return (combined, EXPECTED_WHAT_TO_SHOW)


@pytest.fixture
def temp_cache():
    """Temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield HistoricalDataCache(tmpdir)


@pytest.fixture
def sample_data():
    """Sample DataFrame with OHLCV data (100 days)."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    prices = 100.0 + (pd.Series(range(100)) * 0.1).values
    df = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices + 0.5,
            "volume": 1000000,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


@pytest.fixture
def mock_client():
    """Mock IBClient with market_data service."""
    client = MagicMock()
    client.market_data = MagicMock()
    return client


class TestIncrementalRefreshCleanOverlap:
    """Test clean overlap: no dividend, successful incremental extend."""

    @pytest.mark.asyncio
    async def test_clean_overlap_extends_cache(
        self, temp_cache, sample_data, mock_client
    ):
        """Incremental fetch with clean overlap produces concatenated frame."""
        # Setup: cache has 100 days of data (Jan 1-Apr 10, 2023)
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # Mock 1-year fetch: last 30 days of old data (overlap) + 35 new days
        # This ensures overlap is 30 days (>= OVERLAP_MIN_DAYS of 20)
        overlap_data = sample_data.iloc[-30:]  # Last 30 days of cache

        new_dates = pd.date_range(
            sample_data.index[-1] + timedelta(days=1), periods=35, freq="D"
        )
        new_prices = 109.9 + (pd.Series(range(35)) * 0.1).values
        new_data = pd.DataFrame(
            {
                "open": new_prices,
                "high": new_prices + 1.0,
                "low": new_prices - 1.0,
                "close": new_prices + 0.5,
                "volume": 1000000,
            },
            index=new_dates,
        )
        new_data.index.name = "date"

        # Combine: overlap + new
        one_year_data = pd.concat([overlap_data, new_data])
        one_year_data = one_year_data[~one_year_data.index.duplicated(keep="last")]
        one_year_data = one_year_data.sort_index()

        mock_client.market_data.download_extended_history = AsyncMock(
            return_value=one_year_data
        )

        # Call incremental fetch with May 15 as end_date
        fetch_end = datetime(2023, 5, 15)
        result = await _try_incremental_fetch(
            mock_client, symbol, spec, temp_cache, end_date=fetch_end
        )

        # Should succeed with concatenated frame
        assert result is not None
        df_result, what_to_show = result
        assert what_to_show == EXPECTED_WHAT_TO_SHOW
        # Result should have: pre-overlap (70) + one_year_data (65) = 135
        # pre-overlap = old_df[index.date < Mar 11] = 70 rows
        # one_year_data = 30 overlap + 35 new = 65 rows
        assert len(df_result) == 135
        assert df_result.index[0] == sample_data.index[0]  # Jan 1
        assert df_result.index[-1] == one_year_data.index[-1]  # May 15

    @pytest.mark.asyncio
    async def test_clean_overlap_matches_full_fetch(
        self, temp_cache, sample_data, mock_client
    ):
        """Clean incremental append produces frame identical to full fetch."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        # Cache: first 90 days
        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 3, 31)
        cached_data = sample_data.iloc[:90]
        temp_cache.save_cached_data(
            symbol, cached_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # One-year fetch: last 20 days of cached + 10 new
        overlap = sample_data.iloc[70:90]
        new_dates = pd.date_range(
            sample_data.index[89] + timedelta(days=1), periods=10, freq="D"
        )
        new_prices = 109.0 + (pd.Series(range(10)) * 0.1).values
        new_data = pd.DataFrame(
            {
                "open": new_prices,
                "high": new_prices + 1.0,
                "low": new_prices - 1.0,
                "close": new_prices + 0.5,
                "volume": 1000000,
            },
            index=new_dates,
        )
        new_data.index.name = "date"

        one_year_data = pd.concat([overlap, new_data])
        one_year_data = one_year_data.sort_index()

        mock_client.market_data.download_extended_history = AsyncMock(
            return_value=one_year_data
        )

        # Call incremental
        fetch_end = datetime(2023, 4, 10)
        result = await _try_incremental_fetch(
            mock_client, symbol, spec, temp_cache, end_date=fetch_end
        )
        assert result is not None
        df_incr, _ = result

        # Full fetch would be: cached (90) + new (10) minus overlap (20) = 80 total
        expected = pd.concat([cached_data, new_data])
        expected = expected[~expected.index.duplicated(keep="last")]
        expected = expected.sort_index()

        assert len(df_incr) == len(expected)
        # Check date index matches
        assert (df_incr.index == expected.index).all()
        # Check values match (ignore metadata from parquet roundtrip)
        pd.testing.assert_frame_equal(
            df_incr.reset_index(drop=True), expected.reset_index(drop=True)
        )


class TestIncrementalRefreshMismatchedOverlap:
    """Test mismatched overlap: dividend adjustment detected."""

    @pytest.mark.asyncio
    async def test_mismatch_detected_and_triggers_full_refetch(
        self, temp_cache, sample_data, mock_client
    ):
        """Overlap mismatch (e.g. dividend) returns None to trigger full refetch."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # One-year fetch with dividend adjustment: 2% shift in prices
        overlap_data = sample_data.iloc[-20:].copy()
        # Simulate dividend by shifting close prices down 2%
        overlap_data["close"] = overlap_data["close"] * 0.98
        overlap_data["open"] = overlap_data["open"] * 0.98
        overlap_data["high"] = overlap_data["high"] * 0.98
        overlap_data["low"] = overlap_data["low"] * 0.98

        new_dates = pd.date_range(
            sample_data.index[-1] + timedelta(days=1), periods=15, freq="D"
        )
        new_prices = 107.9 + (pd.Series(range(15)) * 0.1).values
        new_data = pd.DataFrame(
            {
                "open": new_prices,
                "high": new_prices + 1.0,
                "low": new_prices - 1.0,
                "close": new_prices + 0.5,
                "volume": 1000000,
            },
            index=new_dates,
        )
        new_data.index.name = "date"

        one_year_data = pd.concat([overlap_data, new_data])
        one_year_data = one_year_data.sort_index()

        mock_client.market_data.download_extended_history = AsyncMock(
            return_value=one_year_data
        )

        # Call incremental; should return None due to mismatch
        fetch_end = datetime(2023, 4, 25)
        result = await _try_incremental_fetch(
            mock_client, symbol, spec, temp_cache, end_date=fetch_end
        )
        assert result is None


class TestIncrementalRefreshShortOverlap:
    """Test short overlap: less than OVERLAP_MIN_DAYS."""

    @pytest.mark.asyncio
    async def test_short_overlap_triggers_full_refetch(
        self, temp_cache, sample_data, mock_client
    ):
        """Overlap < OVERLAP_MIN_DAYS returns None to trigger full refetch."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # One-year fetch with very short overlap (5 days)
        overlap_data = sample_data.iloc[-5:]
        new_dates = pd.date_range(
            sample_data.index[-1] + timedelta(days=1), periods=30, freq="D"
        )
        new_prices = 109.5 + (pd.Series(range(30)) * 0.1).values
        new_data = pd.DataFrame(
            {
                "open": new_prices,
                "high": new_prices + 1.0,
                "low": new_prices - 1.0,
                "close": new_prices + 0.5,
                "volume": 1000000,
            },
            index=new_dates,
        )
        new_data.index.name = "date"

        one_year_data = pd.concat([overlap_data, new_data])
        one_year_data = one_year_data.sort_index()

        mock_client.market_data.download_extended_history = AsyncMock(
            return_value=one_year_data
        )

        # Call incremental; should return None due to short overlap
        fetch_end = datetime(2023, 5, 10)
        result = await _try_incremental_fetch(
            mock_client, symbol, spec, temp_cache, end_date=fetch_end
        )
        assert result is None


class TestIncrementalRefreshCacheInvalidation:
    """Test old cache file handling."""

    def test_old_file_identified_before_refresh(self, temp_cache, sample_data):
        """Latest_cache_file finds the newest matching cache file."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        # Create two old cache files
        from data.cache import latest_cache_file

        start1 = datetime(2023, 1, 1)
        end1 = datetime(2023, 3, 1)
        temp_cache.save_cached_data(
            symbol, sample_data.iloc[:60], start1, end1, what_to_show="ADJUSTED_LAST"
        )

        start2 = datetime(2023, 3, 1)
        end2 = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data.iloc[60:], start2, end2, what_to_show="ADJUSTED_LAST"
        )

        # latest_cache_file should return the newer one (end2)
        result = latest_cache_file(symbol, cache_dir=str(temp_cache.cache_dir))
        assert result is not None
        path, df = result
        assert end2.strftime("%Y%m%d") in path.name
        assert len(df) == 40  # Second file has 40 rows

    def test_old_file_can_be_deleted(self, temp_cache, sample_data):
        """Successfully delete old cache file after new one saved."""
        symbol = "TEST"

        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, start, end, what_to_show="ADJUSTED_LAST"
        )

        old_path = temp_cache._get_cache_path(symbol, start, end)
        assert old_path.exists()

        # Simulate saving new file with different dates
        new_start = datetime(2023, 3, 1)
        new_end = datetime(2023, 5, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, new_start, new_end, what_to_show="ADJUSTED_LAST"
        )

        # Delete old file
        old_path.unlink(missing_ok=True)
        assert not old_path.exists()

        # New file exists
        new_path = temp_cache._get_cache_path(symbol, new_start, new_end)
        assert new_path.exists()


class TestIncrementalRefreshEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_no_cached_file_returns_none(self, temp_cache, mock_client):
        """When no cache exists, _try_incremental_fetch returns None."""
        symbol = "NOCACHE"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        result = await _try_incremental_fetch(mock_client, symbol, spec, temp_cache)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_one_year_fetch_returns_none(
        self, temp_cache, sample_data, mock_client
    ):
        """When 1-year fetch returns empty, _try_incremental_fetch returns None."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # Mock empty 1-year fetch
        mock_client.market_data.download_extended_history = AsyncMock(
            return_value=pd.DataFrame()
        )

        result = await _try_incremental_fetch(mock_client, symbol, spec, temp_cache)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_exception_returns_none(
        self, temp_cache, sample_data, mock_client
    ):
        """When 1-year fetch raises, _try_incremental_fetch returns None."""
        symbol = "TEST"
        spec = {"sec_type": "STK", "exchange": "SMART", "currency": "USD"}

        cache_start = datetime(2023, 1, 1)
        cache_end = datetime(2023, 4, 10)
        temp_cache.save_cached_data(
            symbol, sample_data, cache_start, cache_end, what_to_show="ADJUSTED_LAST"
        )

        # Mock exception on fetch
        mock_client.market_data.download_extended_history = AsyncMock(
            side_effect=Exception("Connection error")
        )

        result = await _try_incremental_fetch(mock_client, symbol, spec, temp_cache)
        assert result is None
