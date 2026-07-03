"""
Round-trip tests for backtesting/results_io.py + backtesting/results_schema.py.

Builds a minimal BacktestResults, serializes it, saves it to a tmp_path
results directory (with and without a stress report), and reloads it via
the results_schema loaders to check the write/read contract stays intact.
"""

import json

import pandas as pd
import pytest

from backtesting.engine import BacktestResults
from backtesting.transaction import Transaction
from backtesting.results_io import save_strategy_results, serialize_backtest_results
from backtesting.results_schema import (
    INDEX_FILE,
    STRATEGY_FILES,
    STRESS_TEST_FILE,
    load_portfolio_values,
    load_strategy_payload,
    strategy_dir,
)


def _make_backtest_results() -> BacktestResults:
    """Build a tiny two-rebalance BacktestResults for a single symbol."""
    dates = pd.date_range("2021-01-04", periods=2, freq="MS")

    portfolio_history = pd.DataFrame(
        {
            "cash": [0.0, 0.0],
            "total_value": [10_000.0, 10_500.0],
            "VUSA": [10_000.0, 10_500.0],
        },
        index=pd.Index(dates, name="timestamp"),
    )

    weights_history = pd.DataFrame(
        {"VUSA": [1.0, 1.0]},
        index=pd.Index(dates, name="timestamp"),
    )

    transactions = [
        Transaction(
            timestamp=dates[0],
            symbol="VUSA",
            quantity=100.0,
            price=100.0,
            cost_bps=7.5,
            total_cost=10_007.5,
        )
    ]

    return BacktestResults(
        strategy_name="test_strategy",
        portfolio_history=portfolio_history,
        weights_history=weights_history,
        transactions=transactions,
        initial_capital=10_000.0,
        final_value=10_500.0,
        failed_rebalances=[],
    )


def _strategy_info() -> dict:
    return {
        "key": "test_strategy",
        "type": "allocation",
        "class": "TestStrategy",
        "description": "unit test strategy",
        "parameters": {},
    }


def _run_config() -> dict:
    return {
        "symbols": ["VUSA"],
        "currency": "GBP",
        "initial_capital": 10_000.0,
        "transaction_cost_bps": 7.5,
        "rebalance_frequency": "monthly",
        "lookback_days": 252,
    }


def test_serialize_backtest_results_shape():
    """serialize_backtest_results() returns the keys save_strategy_results expects."""
    results = _make_backtest_results()
    serialized = serialize_backtest_results(results, "test_strategy", _strategy_info())

    for logical_name in STRATEGY_FILES:
        assert logical_name in serialized

    assert serialized["metrics"]["final_value"] == pytest.approx(10_500.0)
    assert serialized["metrics"]["rebalances"] == 2
    assert serialized["metrics"]["total_transactions"] == 1
    assert len(serialized["portfolio_history"]) == 2
    assert len(serialized["transactions"]) == 1
    assert len(serialized["weights_history"]) == 2


def test_save_and_reload_without_stress_report(tmp_path):
    """Round-trip save -> reload with no stress report supplied."""
    results = _make_backtest_results()
    serialized = serialize_backtest_results(results, "test_strategy", _strategy_info())

    target_dir = save_strategy_results(
        serialized, "test_strategy", tmp_path, config=_run_config()
    )

    # All five per-strategy files were written.
    assert target_dir == strategy_dir(tmp_path, "test_strategy")
    for filename in STRATEGY_FILES.values():
        assert (target_dir / filename).exists()

    # No stress_test.json when no report is supplied.
    assert not (target_dir / STRESS_TEST_FILE).exists()

    # Values round-trip through the schema loaders.
    payload = load_strategy_payload(tmp_path, "test_strategy")
    assert payload["metrics"]["final_value"] == pytest.approx(10_500.0)
    assert len(payload["portfolio_history"]) == 2
    assert len(payload["transactions"]) == 1

    values = load_portfolio_values(tmp_path, "test_strategy")
    assert isinstance(values, pd.Series)
    assert list(values.values) == pytest.approx([10_000.0, 10_500.0])
    assert values.name == "total_value"

    # Index was created and merged with the config block present.
    index_path = tmp_path / INDEX_FILE
    assert index_path.exists()
    with open(index_path) as f:
        index_data = json.load(f)
    assert "test_strategy" in index_data["strategies"]
    assert index_data["strategies"]["test_strategy"]["metrics"][
        "final_value"
    ] == pytest.approx(10_500.0)
    assert index_data["config"] == _run_config()
    assert index_data["total_strategies"] == 1


def test_save_with_stress_report_writes_stress_file(tmp_path):
    """stress_test.json is written only when a stress_report is supplied."""
    results = _make_backtest_results()
    serialized = serialize_backtest_results(results, "test_strategy", _strategy_info())

    stress_report = {"strategy_name": "test_strategy", "crises": []}
    target_dir = save_strategy_results(
        serialized,
        "test_strategy",
        tmp_path,
        stress_report=stress_report,
        config=_run_config(),
    )

    stress_path = target_dir / STRESS_TEST_FILE
    assert stress_path.exists()
    with open(stress_path) as f:
        assert json.load(f) == stress_report


def test_save_strategy_results_merges_index_across_calls(tmp_path):
    """A second strategy's save merges into the index rather than replacing it."""
    results = _make_backtest_results()
    serialized_a = serialize_backtest_results(results, "strategy_a", _strategy_info())
    serialized_b = serialize_backtest_results(results, "strategy_b", _strategy_info())

    save_strategy_results(serialized_a, "strategy_a", tmp_path, config=_run_config())
    save_strategy_results(serialized_b, "strategy_b", tmp_path, config=_run_config())

    with open(tmp_path / INDEX_FILE) as f:
        index_data = json.load(f)

    assert set(index_data["strategies"].keys()) == {"strategy_a", "strategy_b"}
    assert index_data["total_strategies"] == 2
