"""Data loading functions for the dashboard server."""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "results"

def load_strategies_index() -> dict | None:
    """
    Load the strategies index from all-strategies run.

    Returns dict with available strategies and their paths.
    Falls back to legacy metadata.json if index doesn't exist.
    Reads fresh from disk each call so new backtest runs are picked up immediately.
    """
    index_path = RESULTS_DIR / "strategies_index.json"

    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"   [!] Error loading strategies_index.json: {e}")

    # Fallback to legacy metadata.json for backward compatibility
    metadata_path = RESULTS_DIR / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
                return {
                    "run_date": datetime.now().isoformat(),
                    "total_strategies": 2,
                    "strategies": {},
                    "config": metadata.get("config", {}),
                }
        except Exception as e:
            print(f"   [!] Error loading metadata.json: {e}")

    return None


def list_strategy_keys() -> list[str]:
    """Return sorted list of available strategy keys."""
    index = load_strategies_index()
    if index and "strategies" in index:
        return sorted(index["strategies"].keys())

    # Fallback: scan strategy folders
    strategies_dir = RESULTS_DIR / "strategies"
    if strategies_dir.exists():
        return sorted(d.name for d in strategies_dir.iterdir() if d.is_dir())

    return []


def load_strategy_data(strategy_key: str) -> dict | None:
    """
    Load all data for a specific strategy from its folder.

    Args:
        strategy_key: Strategy identifier (e.g., 'hrp_single')

    Returns:
        Dict with portfolio_history, transactions, weights_history, metrics, info
    """
    strategy_dir = RESULTS_DIR / "strategies" / strategy_key

    if not strategy_dir.exists():
        return None

    data = {
        "key": strategy_key,
        "portfolio_history": [],
        "transactions": [],
        "weights_history": [],
        "metrics": {},
        "info": {},
    }

    for field, filename in [
        ("portfolio_history", "portfolio_history.json"),
        ("transactions", "transactions.json"),
        ("weights_history", "weights_history.json"),
        ("metrics", "metrics.json"),
        ("info", "info.json"),
    ]:
        path = strategy_dir / filename
        if path.exists():
            with open(path, "r") as f:
                data[field] = json.load(f)

    return data


def get_portfolio_value_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract portfolio value time series from strategy data."""
    if not strategy_data or not strategy_data.get("portfolio_history"):
        return {}

    name = strategy_name or strategy_data.get("key", "Strategy")
    return {
        name: {
            "dates": [
                entry.get("date", entry.get("timestamp", ""))
                for entry in strategy_data["portfolio_history"]
            ],
            "values": [
                entry.get("total_value", 0)
                for entry in strategy_data["portfolio_history"]
            ],
        }
    }


def get_drawdown_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Calculate drawdown from portfolio history."""
    if not strategy_data or not strategy_data.get("portfolio_history"):
        return {}

    name = strategy_name or strategy_data.get("key", "Strategy")
    portfolio = strategy_data["portfolio_history"]

    if not portfolio:
        return {}

    values = [entry.get("total_value", 0) for entry in portfolio]
    dates = [entry.get("date", entry.get("timestamp", "")) for entry in portfolio]

    if not values:
        return {}

    values_array = np.array(values)
    running_max = np.maximum.accumulate(values_array)
    drawdown = ((values_array - running_max) / running_max) * 100

    return {name: {"dates": dates, "drawdown": drawdown.tolist()}}


def get_weights_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract portfolio weights over time."""
    if not strategy_data or not strategy_data.get("weights_history"):
        return {}

    name = strategy_name or strategy_data.get("key", "Strategy")
    weights_list = strategy_data["weights_history"]

    if not weights_list:
        return {}

    weights_data = {
        "dates": [
            entry.get("date", entry.get("timestamp", "")) for entry in weights_list
        ]
    }

    first_entry = weights_list[0] if weights_list else {}
    symbols = [k for k in first_entry.keys() if k not in ["date", "timestamp"]]

    for symbol in symbols:
        weights_data[symbol] = [entry.get(symbol, 0) for entry in weights_list]

    return {name: weights_data}


def get_transactions_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract transaction data."""
    if not strategy_data or not strategy_data.get("transactions"):
        return {}

    name = strategy_name or strategy_data.get("key", "Strategy")
    return {name: strategy_data["transactions"]}


def load_overfitting_analysis(strategy_key: str) -> dict | None:
    """
    Load overfitting_analysis.json for a strategy.

    Returns the parsed dict if the file exists, None otherwise.
    A None result means the strategy has not yet been analysed.
    """
    path = RESULTS_DIR / "strategies" / strategy_key / "overfitting_analysis.json"
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Error loading overfitting_analysis.json for {strategy_key}: {e}")
        return None
