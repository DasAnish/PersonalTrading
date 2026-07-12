"""Tests for the strategy watchlist / trackers module (analytics/trackers.py)."""

import pandas as pd
import pytest

import analytics.trackers as T


@pytest.fixture
def path(tmp_path):
    return tmp_path / "trackers.json"


def test_add_remove_round_trip(path):
    entry = T.add_tracker("gold_autumn_seasonality", note="like it", path=path)
    assert entry["strategy"] == "gold_autumn_seasonality"
    assert entry["added_on"]  # today's ISO date
    assert len(T.load_trackers(path)["trackers"]) == 1

    assert T.remove_tracker("gold_autumn_seasonality", path=path) is True
    assert T.load_trackers(path)["trackers"] == []
    # removing again is a no-op
    assert T.remove_tracker("gold_autumn_seasonality", path=path) is False


def test_duplicate_raises(path):
    T.add_tracker("s", path=path)
    with pytest.raises(ValueError, match="already tracked"):
        T.add_tracker("s", path=path)


def test_since_added_truncation_and_normalization(monkeypatch):
    idx = pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"])
    values = pd.Series([10000.0, 10500.0, 11000.0, 12000.0], index=idx)
    monkeypatch.setattr(T, "load_portfolio_values", lambda rd, k: values)

    perf = T.since_added_performance("s", "2026-02-01")
    assert perf["n_points"] == 3  # truncated at 2026-02-01 onward
    assert perf["series"][0]["value"] == pytest.approx(100.0)  # normalized base
    assert perf["series"][-1]["value"] == pytest.approx(12000.0 / 10500.0 * 100.0)
    assert perf["total_return"] == pytest.approx(12000.0 / 10500.0 - 1.0)


def test_since_added_missing_history_is_empty(monkeypatch):
    monkeypatch.setattr(
        T, "load_portfolio_values", lambda rd, k: pd.Series(dtype=float)
    )
    perf = T.since_added_performance("s", "2026-02-01")
    assert perf == {
        "series": [],
        "total_return": None,
        "sharpe": None,
        "max_drawdown": None,
        "n_points": 0,
    }
