"""Test metrics_version stamping in results serialization and index rebuild."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backtesting.results_io import serialize_backtest_results
from backtesting.results_schema import METRICS_SCHEMA_VERSION, STRATEGY_FILES


class MockTransaction:
    """Mock transaction for testing."""

    def __init__(self, symbol: str = "TEST", quantity: float = 1.0):
        self.symbol = symbol
        self.quantity = quantity
        self.price = 100.0
        self.timestamp = "2026-01-01"
        self.total_cost = 100.0


class MockResults:
    """Mock BacktestResults for testing."""

    def __init__(self):
        import pandas as pd

        # Create minimal valid portfolio history (must have at least 2 points)
        self.portfolio_history = pd.DataFrame(
            {
                "total_value": [10000.0, 11000.0],
            },
            index=pd.DatetimeIndex(["2026-01-01", "2026-02-01"]),
        )
        self.transactions = [MockTransaction()]
        self.weights_history = None
        self.final_value = 11000.0


def test_serialize_stamps_metrics_version():
    """Test that serialize_backtest_results stamps metrics_version."""
    results = MockResults()
    strategy_info = {"name": "test_strategy"}

    serialized = serialize_backtest_results(results, "test_key", strategy_info)

    assert "metrics" in serialized
    assert "metrics_version" in serialized["metrics"]
    assert serialized["metrics"]["metrics_version"] == METRICS_SCHEMA_VERSION


def test_rebuild_index_detects_mixed_versions():
    """Test that rebuild_index detects mixed metrics_version versions."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.rebuild_index import rebuild  # noqa: E402

    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir)
        strategies_dir = results_dir / "strategies"

        # Create strategy with version 2 (stamped)
        strategy1_dir = strategies_dir / "strategy_v2"
        strategy1_dir.mkdir(parents=True, exist_ok=True)
        metrics_v2 = {
            "sharpe_ratio": 1.5,
            "total_return": 0.25,
            "max_drawdown": -0.10,
            "data_end": "2026-01-31",
            "periods_per_year": 12,
            "metrics_version": 2,
        }
        with open(strategy1_dir / STRATEGY_FILES["metrics"], "w") as f:
            json.dump(metrics_v2, f)
        info1 = {"name": "strategy_v2"}
        with open(strategy1_dir / STRATEGY_FILES["info"], "w") as f:
            json.dump(info1, f)

        # Create strategy with version 1 (unstamped, default)
        strategy2_dir = strategies_dir / "strategy_v1"
        strategy2_dir.mkdir(parents=True, exist_ok=True)
        metrics_v1 = {
            "sharpe_ratio": 1.2,
            "total_return": 0.20,
            "max_drawdown": -0.12,
            "data_end": "2026-01-31",
            "periods_per_year": 12,
            # No metrics_version key (defaults to 1)
        }
        with open(strategy2_dir / STRATEGY_FILES["metrics"], "w") as f:
            json.dump(metrics_v1, f)
        info2 = {"name": "strategy_v1"}
        with open(strategy2_dir / STRATEGY_FILES["info"], "w") as f:
            json.dump(info2, f)

        # Rebuild index
        index = rebuild(results_dir)

        # Verify metrics_schema tracking
        assert "metrics_schema" in index
        assert index["metrics_schema"]["current"] == METRICS_SCHEMA_VERSION
        assert sorted(index["metrics_schema"]["versions_present"]) == [1, 2]
        assert index["metrics_schema"]["mixed"] is True


def test_rebuild_index_unmixed_versions():
    """Test that rebuild_index correctly detects unmixed versions."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.rebuild_index import rebuild  # noqa: E402

    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir)
        strategies_dir = results_dir / "strategies"

        # Create two strategies with the same version
        for i in range(2):
            strategy_dir = strategies_dir / f"strategy_{i}"
            strategy_dir.mkdir(parents=True, exist_ok=True)
            metrics = {
                "sharpe_ratio": 1.5,
                "total_return": 0.25,
                "max_drawdown": -0.10,
                "data_end": "2026-01-31",
                "periods_per_year": 12,
                "metrics_version": 2,
            }
            with open(strategy_dir / STRATEGY_FILES["metrics"], "w") as f:
                json.dump(metrics, f)
            info = {"name": f"strategy_{i}"}
            with open(strategy_dir / STRATEGY_FILES["info"], "w") as f:
                json.dump(info, f)

        # Rebuild index
        index = rebuild(results_dir)

        # Verify metrics_schema shows unmixed
        assert "metrics_schema" in index
        assert index["metrics_schema"]["current"] == METRICS_SCHEMA_VERSION
        assert index["metrics_schema"]["versions_present"] == [2]
        assert index["metrics_schema"]["mixed"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
