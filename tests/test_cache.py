"""
Tests for data/cache.py:
- Fuzzy cache fallback (accept only when covering the requested range, warn)
- allow_fuzzy=False disables the fallback entirely
- Atomic writes (no .tmp left behind on success, old file intact on failure)
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import pytest

from data.cache import HistoricalDataCache


def _make_df(n=10):
    return pd.DataFrame(
        {"close": range(n)},
        index=pd.bdate_range("2020-01-01", periods=n),
    )


@pytest.fixture
def cache(tmp_path):
    return HistoricalDataCache(cache_dir=str(tmp_path))


class TestFuzzyFallback:
    def test_fuzzy_match_used_when_covering_and_logs_warning(self, cache, caplog):
        """A wider cached file that covers the requested range is used, with a WARNING log."""
        wide_start = datetime(2020, 1, 1)
        wide_end = datetime(2020, 12, 31)
        cache.save_cached_data("VUSA", _make_df(200), wide_start, wide_end)

        requested_start = datetime(2020, 3, 1)
        requested_end = datetime(2020, 6, 1)

        with caplog.at_level(logging.WARNING):
            result = cache.load_cached_data("VUSA", requested_start, requested_end)

        assert not result.empty
        assert any(
            "fuzzy hit" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )

    def test_fuzzy_match_rejected_when_not_covering(self, cache):
        """A cached file whose range does not cover the request is not used."""
        narrow_start = datetime(2020, 6, 1)
        narrow_end = datetime(2020, 6, 30)
        cache.save_cached_data("VUSA", _make_df(20), narrow_start, narrow_end)

        # Request a range that extends beyond what's cached
        requested_start = datetime(2020, 1, 1)
        requested_end = datetime(2020, 12, 31)

        result = cache.load_cached_data("VUSA", requested_start, requested_end)
        assert result.empty

    def test_allow_fuzzy_false_disables_fallback(self, cache):
        """With allow_fuzzy=False, even a covering file is not used unless exact match."""
        wide_start = datetime(2020, 1, 1)
        wide_end = datetime(2020, 12, 31)
        cache.save_cached_data("VUSA", _make_df(200), wide_start, wide_end)

        requested_start = datetime(2020, 3, 1)
        requested_end = datetime(2020, 6, 1)

        result = cache.load_cached_data(
            "VUSA", requested_start, requested_end, allow_fuzzy=False
        )
        assert result.empty

    def test_exact_match_does_not_require_fuzzy(self, cache):
        """An exact filename match is used regardless of allow_fuzzy."""
        start = datetime(2020, 1, 1)
        end = datetime(2020, 1, 31)
        cache.save_cached_data("VUSA", _make_df(20), start, end)

        result = cache.load_cached_data("VUSA", start, end, allow_fuzzy=False)
        assert not result.empty


class TestAtomicWrite:
    def test_no_tmp_file_left_on_success(self, cache):
        start = datetime(2020, 1, 1)
        end = datetime(2020, 1, 31)
        cache.save_cached_data("VUSA", _make_df(20), start, end)

        tmp_files = list(cache.cache_dir.glob("*.tmp"))
        assert tmp_files == []

        final_path = cache._get_cache_path("VUSA", start, end)
        assert final_path.exists()

    def test_failed_write_leaves_previous_file_intact(self, cache, monkeypatch):
        start = datetime(2020, 1, 1)
        end = datetime(2020, 1, 31)

        # Write a good file first
        good_df = _make_df(20)
        cache.save_cached_data("VUSA", good_df, start, end)
        final_path = cache._get_cache_path("VUSA", start, end)
        original_bytes = final_path.read_bytes()

        # Now simulate a failing write to the same cache key
        def failing_to_parquet(self, *args, **kwargs):
            raise IOError("simulated disk failure")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", failing_to_parquet)

        bad_df = _make_df(5)
        cache.save_cached_data("VUSA", bad_df, start, end)

        # Original file must be untouched, no leftover tmp file
        assert final_path.read_bytes() == original_bytes
        tmp_files = list(cache.cache_dir.glob("*.tmp"))
        assert tmp_files == []
