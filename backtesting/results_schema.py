"""
Single source of truth for the on-disk backtest results contract.

Every script that writes or reads ``results/strategies/<key>/*.json`` should
import filenames and loaders from this module rather than hard-coding
filenames — this is what previously caused the writer paths in
``scripts/run_backtest.py`` to drift from each other (see
``backtesting/results_io.py`` for the write-side reconciliation) and let the
readers in ``scripts/server/data.py``, ``scripts/run_overfitting.py`` and
``scripts/run_all_overfitting.py`` diverge subtly.

Directory layout (relative to a top-level ``results_dir``, e.g. ``results/``):

    <results_dir>/strategies_index.json
    <results_dir>/strategies/<key>/portfolio_history.json
    <results_dir>/strategies/<key>/transactions.json
    <results_dir>/strategies/<key>/weights_history.json
    <results_dir>/strategies/<key>/metrics.json
    <results_dir>/strategies/<key>/info.json
    <results_dir>/strategies/<key>/stress_test.json          (optional)
    <results_dir>/strategies/<key>/overfitting_analysis.json (optional)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import pandas as pd

# Metrics schema version: 1 = pre-stamp (implicit), 2 = ADJUSTED_LAST era + stamped
METRICS_SCHEMA_VERSION = 2

# Logical name -> filename, for the always-present per-strategy result files.
STRATEGY_FILES: dict = {
    "portfolio_history": "portfolio_history.json",
    "transactions": "transactions.json",
    "weights_history": "weights_history.json",
    "metrics": "metrics.json",
    "info": "info.json",
}

STRESS_TEST_FILE = "stress_test.json"
OVERFITTING_FILE = "overfitting_analysis.json"
VALIDATION_FILE = "validation.json"
INDEX_FILE = "strategies_index.json"

PathLike = Union[str, Path]


def strategy_dir(results_dir: PathLike, key: str) -> Path:
    """Return the per-strategy results directory: <results_dir>/strategies/<key>."""
    return Path(results_dir) / "strategies" / key


def load_strategy_payload(results_dir: PathLike, key: str) -> dict:
    """
    Read the per-strategy result files that exist into a dict keyed by
    logical name (the keys of ``STRATEGY_FILES``).

    Files that don't exist on disk are simply omitted from the returned
    dict (mirrors ``scripts/server/data.py:load_strategy_data``, which
    leaves the corresponding field at its default when a file is missing —
    callers that need a guaranteed key should use ``.get(name, default)``).
    """
    target_dir = strategy_dir(results_dir, key)
    payload: dict = {}
    for logical_name, filename in STRATEGY_FILES.items():
        path = target_dir / filename
        if path.exists():
            with open(path, "r") as f:
                payload[logical_name] = json.load(f)
    return payload


def load_portfolio_values(results_dir: PathLike, key: str) -> pd.Series:
    """
    Load ``portfolio_history.json`` into a date-indexed ``pd.Series`` of
    ``total_value``, named ``"total_value"``.

    Matches the construction used by ``scripts/run_overfitting.py`` and
    ``scripts/run_all_overfitting.py`` (``pd.Timestamp(row["date"])`` per
    entry), extended with the "date" or "timestamp" field fallback used by
    ``scripts/server/data.py``'s portfolio-history readers. Returns an empty
    float Series if the file is missing or empty.
    """
    path = strategy_dir(results_dir, key) / STRATEGY_FILES["portfolio_history"]
    if not path.exists():
        return pd.Series(dtype=float)

    with open(path, "r") as f:
        data = json.load(f)

    if not data:
        return pd.Series(dtype=float)

    dates = [pd.Timestamp(row.get("date", row.get("timestamp"))) for row in data]
    values = [float(row["total_value"]) for row in data]
    return pd.Series(values, index=dates, name="total_value")
