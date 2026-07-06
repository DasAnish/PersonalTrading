"""Data loading functions for the dashboard server."""

import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting.results_schema import (
    INDEX_FILE,
    STRESS_TEST_FILE,
    OVERFITTING_FILE,
    VALIDATION_FILE,
    load_strategy_payload,
)
from backtesting.results_schema import strategy_dir as schema_strategy_dir

BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "results"
STRATEGY_DEFS_DIR = BASE_DIR / "strategy_definitions"

_STRATEGY_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def is_valid_strategy_key(key: str) -> bool:
    """
    Validate a strategy key before it is used to build a filesystem path.

    Only alphanumeric characters, underscores, and hyphens are allowed.
    This prevents path traversal (e.g. "../../etc/passwd") since the key
    is joined directly onto RESULTS_DIR / "strategies" / <key>.

    Args:
        key: Candidate strategy key

    Returns:
        True if the key is safe to use as a single path segment
    """
    if not key or not isinstance(key, str):
        return False
    return bool(_STRATEGY_KEY_RE.match(key))


def load_strategy_tags(strategy_key: str) -> list[str]:
    """Load tags from a strategy definition JSON file.

    Searches composed/ and portfolios/ subdirectories for <key>.json.
    Returns an empty list if the file is not found or has no tags.
    """
    for subdir in ("composed", "portfolios", "allocations"):
        path = STRATEGY_DEFS_DIR / subdir / f"{strategy_key}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("tags", [])
            except Exception:
                return []
    return []


def load_strategies_index() -> dict | None:
    """
    Load the strategies index from all-strategies run.

    Returns dict with available strategies and their paths.
    Falls back to legacy metadata.json if index doesn't exist.
    Reads fresh from disk each call so new backtest runs are picked up immediately.
    """
    index_path = RESULTS_DIR / INDEX_FILE

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
        None if the strategy is not found or strategy_key is invalid
    """
    if not is_valid_strategy_key(strategy_key):
        return None

    target_dir = schema_strategy_dir(RESULTS_DIR, strategy_key)

    if not target_dir.exists():
        return None

    data = {
        "key": strategy_key,
        "portfolio_history": [],
        "transactions": [],
        "weights_history": [],
        "metrics": {},
        "info": {},
    }
    data.update(load_strategy_payload(RESULTS_DIR, strategy_key))

    return data


def history_to_series(portfolio_history: list) -> pd.Series:
    """
    Convert an already-loaded ``portfolio_history`` list of dicts into a
    date-indexed ``pd.Series`` of ``total_value``.

    Mirrors ``backtesting.results_schema.load_portfolio_values``, but
    operates on data already loaded into memory (e.g. via
    ``load_strategy_data``) rather than reading a JSON file from disk.
    Each entry's date is read from the "date" field, falling back to
    "timestamp" if absent, matching the field-fallback used elsewhere in
    this module.

    Args:
        portfolio_history: List of dicts with "date"/"timestamp" and
            "total_value" keys.

    Returns:
        pd.Series of total_value indexed by date, named "total_value".
        Empty float Series if portfolio_history is empty.
    """
    if not portfolio_history:
        return pd.Series(dtype=float)

    dates = pd.to_datetime(
        [entry.get("date", entry.get("timestamp")) for entry in portfolio_history]
    )
    values = [float(entry["total_value"]) for entry in portfolio_history]
    return pd.Series(values, index=dates, name="total_value")


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
    None is also returned if strategy_key is invalid.
    """
    if not is_valid_strategy_key(strategy_key):
        return None
    path = schema_strategy_dir(RESULTS_DIR, strategy_key) / OVERFITTING_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Error loading overfitting_analysis.json for {strategy_key}: {e}")
        return None


def _test_by_name(validation: dict, name: str) -> dict:
    """Return the test dict with the given name from a validation.json, or {}."""
    for t in validation.get("tests", []) or []:
        if t.get("name") == name:
            return t
    return {}


def build_validation_summary() -> dict:
    """
    Assemble the library-wide validation/overfitting summary for the dashboard.

    Returns {"spa": <spa_analysis.json or None>, "strategies": [row, ...]} where
    each row flattens the per-strategy battery (validation.json) plus its SPA
    rank stub (from overfitting_analysis.json). Strategies without a
    validation.json are still listed with overall="—" so the page shows coverage.
    """
    rows = []
    for key in list_strategy_keys():
        val = load_validation(key)
        over = load_overfitting_analysis(key) or {}
        spa_stub = over.get("spa", {}) if isinstance(over, dict) else {}
        if val is None:
            rows.append({"key": key, "overall": None, "spa_rank": spa_stub.get("rank")})
            continue
        dsr = _test_by_name(val, "dsr")
        minbtl = _test_by_name(val, "minbtl")
        cpcv = _test_by_name(val, "cpcv")
        boot = _test_by_name(val, "bootstrap")
        rows.append(
            {
                "key": key,
                "overall": val.get("overall"),
                "dsr": (dsr.get("values") or {}).get("dsr"),
                "dsr_verdict": dsr.get("verdict"),
                "minbtl_verdict": minbtl.get("verdict"),
                "cpcv_prob": (cpcv.get("values") or {}).get("prob_oos_sharpe_positive"),
                "boot_p5": (boot.get("values") or {}).get("sharpe_pct5"),
                "spa_rank": spa_stub.get("rank"),
            }
        )
    return {"spa": load_spa_analysis(), "strategies": rows}


def load_spa_analysis() -> dict | None:
    """
    Load the library-wide results/spa_analysis.json (White's Reality Check /
    Hansen's SPA across all strategies vs the equal_weight benchmark).

    Returns the parsed dict if present, None otherwise. A None result means the
    SPA step has not been run yet (scripts/run_all_overfitting.py --spa, or
    scripts/run_full_analysis.py). This is a single library-wide file, not
    per-strategy, so it takes no strategy_key.
    """
    path = RESULTS_DIR / "spa_analysis.json"
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Error loading spa_analysis.json: {e}")
        return None


def load_stress_test(strategy_key: str) -> dict | None:
    """
    Load stress_test.json for a strategy.

    Returns the parsed dict if the file exists, None otherwise.
    A None result means the strategy has not yet been stress-tested
    (run with --stress-test flag). None is also returned if strategy_key
    is invalid.
    """
    if not is_valid_strategy_key(strategy_key):
        return None
    path = schema_strategy_dir(RESULTS_DIR, strategy_key) / STRESS_TEST_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Error loading stress_test.json for {strategy_key}: {e}")
        return None


def load_validation(strategy_key: str) -> dict | None:
    """
    Load validation.json for a strategy.

    Returns the parsed dict if the file exists, None otherwise.
    A None result means the strategy has not yet been validated
    (run with scripts/validate_strategy.py). None is also returned if
    strategy_key is invalid.
    """
    if not is_valid_strategy_key(strategy_key):
        return None
    path = schema_strategy_dir(RESULTS_DIR, strategy_key) / VALIDATION_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Error loading validation.json for {strategy_key}: {e}")
        return None
