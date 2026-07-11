"""
Tests for the nightly-pipeline helper scripts (scripts/validate_cache.py,
scripts/extend_history.py) — the parts that run without IB.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("scripts").resolve()))

from extend_history import splice  # noqa: E402
from validate_cache import check_symbol  # noqa: E402


def _write_cache(tmp_path, symbol: str, dates: pd.DatetimeIndex, close=None):
    close = (
        pd.Series(close, index=dates)
        if close is not None
        else pd.Series(100.0 + np.arange(len(dates)) * 0.1, index=dates)
    )
    df = pd.DataFrame({"open": close, "close": close, "volume": 1.0}, index=dates)
    start = dates[0].strftime("%Y%m%d")
    end = dates[-1].strftime("%Y%m%d")
    df.to_parquet(tmp_path / f"{symbol}_{start}_{end}.parquet")
    return df


class TestValidateCache:
    def test_missing_symbol(self, tmp_path):
        entry = check_symbol(tmp_path, "NOPE", max_stale_days=7)
        assert entry["status"] == "missing"

    def test_fresh_clean_series_ok(self, tmp_path):
        dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=300)
        _write_cache(tmp_path, "GOOD", dates)
        entry = check_symbol(tmp_path, "GOOD", max_stale_days=7)
        assert entry["status"] == "ok"
        assert entry["errors"] == [] and entry["warnings"] == []

    def test_weekends_do_not_trip_gap_check(self, tmp_path):
        dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=300)
        _write_cache(tmp_path, "WKND", dates)
        entry = check_symbol(tmp_path, "WKND", max_stale_days=7)
        assert not any("weekday" in w for w in entry["warnings"])

    def test_long_hole_flagged_in_business_days(self, tmp_path):
        end = pd.Timestamp.now().normalize()
        recent = pd.bdate_range(end=end, periods=100)
        older = pd.bdate_range(end=recent[0] - pd.Timedelta(days=40), periods=100)
        dates = older.append(recent)
        _write_cache(tmp_path, "HOLE", dates)
        entry = check_symbol(tmp_path, "HOLE", max_stale_days=7)
        assert any("missing weekdays" in w for w in entry["warnings"])

    def test_stale_series_flagged(self, tmp_path):
        dates = pd.bdate_range(
            end=pd.Timestamp.now() - pd.Timedelta(days=100), periods=200
        )
        _write_cache(tmp_path, "OLD", dates)
        entry = check_symbol(tmp_path, "OLD", max_stale_days=7)
        assert entry["status"] == "stale"

    def test_bad_prices_flagged(self, tmp_path):
        dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=50)
        close = np.full(len(dates), 100.0)
        close[10] = -5.0
        _write_cache(tmp_path, "BAD", dates, close)
        entry = check_symbol(tmp_path, "BAD", max_stale_days=7)
        assert entry["status"] == "corrupt"
        assert any("non-positive" in e for e in entry["errors"])


class TestSplice:
    def _frames(self):
        rng = np.random.default_rng(1)
        dates = pd.bdate_range("2005-01-03", "2026-06-30")
        proxy_close = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(dates)))), index=dates
        )
        proxy = pd.DataFrame(
            {"open": proxy_close, "close": proxy_close, "volume": 1.0}, index=dates
        )
        etf_dates = dates[dates >= "2018-01-02"]
        etf_close = 0.5 * proxy_close.loc[etf_dates]
        etf = pd.DataFrame(
            {"open": etf_close, "close": etf_close, "volume": 2.0}, index=etf_dates
        )
        return etf, proxy

    def test_extends_history(self):
        etf, proxy = self._frames()
        extended, stats = splice(etf, proxy, min_overlap=250, min_corr=0.85)
        assert extended is not None
        assert extended.index[0] == proxy.index[0]
        assert stats["years_gained"] > 10
        # ETF rows come through verbatim
        assert extended.loc[etf.index, "close"].equals(etf["close"])

    def test_one_bad_print_at_join_does_not_distort_scale(self):
        # A 10% bad print on the first shared day: small enough to pass the
        # correlation gate, big enough that the old single-day scaling
        # would shift every pre-history level by 10%.
        etf, proxy = self._frames()
        etf_bad = etf.copy()
        etf_bad.iloc[0, etf_bad.columns.get_loc("close")] *= 1.10
        good, _ = splice(etf, proxy, min_overlap=250, min_corr=0.85)
        bad, _ = splice(etf_bad, proxy, min_overlap=250, min_corr=0.85)
        assert bad is not None
        ratio = bad["close"].iloc[0] / good["close"].iloc[0]
        assert 0.98 < ratio < 1.02

    def test_grossly_bad_join_print_trips_correlation_gate(self):
        # A 3x print creates a monster return that wrecks the overlap
        # correlation — the splice must refuse rather than absorb it.
        etf, proxy = self._frames()
        etf_bad = etf.copy()
        etf_bad.iloc[0, etf_bad.columns.get_loc("close")] *= 3.0
        extended, stats = splice(etf_bad, proxy, min_overlap=250, min_corr=0.85)
        assert extended is None

    def test_uncorrelated_proxy_refused(self):
        etf, proxy = self._frames()
        flat = proxy.copy()
        flat["close"] = np.linspace(100, 101, len(flat))
        extended, stats = splice(etf, flat, min_overlap=250, min_corr=0.85)
        assert extended is None
        assert "correlation" in stats.get("error", "")
