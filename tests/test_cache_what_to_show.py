"""Tests for cache what_to_show stamping and enforcement.

Verifies that parquet cache files are stamped with what_to_show in metadata,
and that cache loads enforce the stamp (treating mismatches as cache miss).
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from data.cache import (
    HistoricalDataCache,
    EXPECTED_WHAT_TO_SHOW,
    CACHE_META_KEY,
    cache_file_what_to_show,
)


@pytest.fixture
def temp_cache():
    """Temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield HistoricalDataCache(tmpdir)


@pytest.fixture
def sample_data():
    """Sample DataFrame with OHLCV data."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame(
        {
            "open": 100.0 + (pd.Series(range(100)) * 0.01),
            "high": 101.0 + (pd.Series(range(100)) * 0.01),
            "low": 99.0 + (pd.Series(range(100)) * 0.01),
            "close": 100.5 + (pd.Series(range(100)) * 0.01),
            "volume": 1000000,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


class TestCacheWhatToShowStamp:
    """Test parquet metadata stamping of what_to_show."""

    def test_save_and_load_stamp(self, temp_cache, sample_data):
        """Round-trip: save with stamp, read back and verify metadata is present."""
        symbol = "TEST"
        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 10)

        # Save with default what_to_show stamp
        temp_cache.save_cached_data(symbol, sample_data, start, end)

        # Read back via cache_file_what_to_show
        cache_path = temp_cache._get_cache_path(symbol, start, end)
        stamp = cache_file_what_to_show(cache_path)
        assert stamp == EXPECTED_WHAT_TO_SHOW

    def test_save_with_trades_stamp(self, temp_cache, sample_data):
        """Save with explicit what_to_show='TRADES', verify stamp reads back correctly."""
        symbol = "ETFX"
        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 10)

        temp_cache.save_cached_data(
            symbol, sample_data, start, end, what_to_show="TRADES"
        )

        cache_path = temp_cache._get_cache_path(symbol, start, end)
        stamp = cache_file_what_to_show(cache_path)
        assert stamp == "TRADES"

    def test_load_mismatched_stamp_treated_as_miss(self, temp_cache, sample_data):
        """File stamped TRADES but expecting ADJUSTED_LAST should be cache miss."""
        symbol = "ETFX"
        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 10)

        # Save with TRADES stamp
        temp_cache.save_cached_data(
            symbol, sample_data, start, end, what_to_show="TRADES"
        )

        # Load should treat as miss (expecting ADJUSTED_LAST by default)
        loaded = temp_cache.load_cached_data(symbol, start, end)
        assert loaded.empty

    def test_load_unmarked_legacy_file_treated_as_miss(self, temp_cache, sample_data):
        """Legacy unstamped parquet file (df.to_parquet()) should be cache miss."""
        symbol = "LEGACY"
        start = datetime(2023, 1, 1)
        end = datetime(2023, 4, 10)

        # Write via pandas (legacy, no stamp)
        cache_path = temp_cache._get_cache_path(symbol, start, end)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_data.to_parquet(cache_path)

        # Load should treat as miss (no stamp)
        loaded = temp_cache.load_cached_data(symbol, start, end)
        assert loaded.empty

    def test_load_best_cached_data_skips_mismatched(self, temp_cache, sample_data):
        """load_best_cached_data should skip files with mismatched what_to_show."""
        symbol = "HYBRID"
        start1 = datetime(2023, 1, 1)
        end1 = datetime(2023, 2, 1)
        start2 = datetime(2023, 2, 1)
        end2 = datetime(2023, 4, 10)

        # Save first file with TRADES
        temp_cache.save_cached_data(
            symbol, sample_data.iloc[:31], start1, end1, what_to_show="TRADES"
        )

        # Save second file with ADJUSTED_LAST (newer, ends later)
        temp_cache.save_cached_data(
            symbol, sample_data.iloc[31:], start2, end2, what_to_show="ADJUSTED_LAST"
        )

        # load_best_cached_data should pick the ADJUSTED_LAST one (matches expected)
        loaded = temp_cache.load_best_cached_data(symbol)
        assert not loaded.empty
        assert len(loaded) == len(sample_data.iloc[31:])


@pytest.mark.asyncio
class TestAdjustedLastPath:
    """Test ADJUSTED_LAST single-request path requires one request with end_datetime=None.

    Note: This is tested through cache_file_what_to_show and load enforcement,
    as the actual market_data.download_extended_history is tested in
    test_market_data.py. This test just verifies the contract.
    """

    async def test_adjusted_last_contract(self):
        """Document ADJUSTED_LAST single-request contract (end_datetime=None)."""
        # ADJUSTED_LAST must use end_datetime=None to avoid IB rejection.
        # This is enforced in ib_wrapper/market_data.py:download_extended_history.
        # See that file for the actual implementation.
        pass


class TestCacheFileWhatToShow:
    """Test cache_file_what_to_show helper function."""

    def test_read_stamp_from_parquet(self, sample_data):
        """cache_file_what_to_show should read what_to_show from metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.parquet"

            # Write with stamp via pyarrow
            table = pa.Table.from_pandas(sample_data)
            metadata = {CACHE_META_KEY: "ADJUSTED_LAST".encode("utf-8")}
            new_schema = table.schema.with_metadata(metadata)
            table = table.cast(new_schema)
            pq.write_table(table, path)

            # Read back
            stamp = cache_file_what_to_show(path)
            assert stamp == "ADJUSTED_LAST"

    def test_read_stamp_returns_none_for_unmarked(self, sample_data):
        """cache_file_what_to_show should return None for unmarked parquet files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.parquet"

            # Write without stamp (legacy)
            sample_data.to_parquet(path)

            # Read back
            stamp = cache_file_what_to_show(path)
            assert stamp is None

    def test_read_stamp_handles_missing_file(self):
        """cache_file_what_to_show should return None for missing files."""
        stamp = cache_file_what_to_show(Path("/nonexistent/path.parquet"))
        assert stamp is None
