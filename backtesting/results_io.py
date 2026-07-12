"""
Write-side of the on-disk backtest results contract.

``save_strategy_results`` is the single write path for
``results/strategies/<key>/*.json``; filenames come from
``backtesting.results_schema``, metrics come from
``analytics.metrics.summarize_performance`` (annualization inferred from
the series' actual spacing — never hard-coded 252).

Index semantics: ``save_strategy_results`` always **merges** its one entry
into ``strategies_index.json``. A caller that wants a run-scoped index
(``run_backtest.py --all``) deletes the index before its save loop; the
authoritative rebuild-from-disk is ``scripts/rebuild_index.py``. A supplied
``config`` block always overwrites the index's config; ``config=None``
leaves it untouched. ``stress_report`` (optional) writes
``stress_test.json`` alongside the other files.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from analytics.metrics import summarize_performance

from .engine import BacktestResults
from .results_schema import (
    INDEX_FILE,
    METRICS_SCHEMA_VERSION,
    STRATEGY_FILES,
    STRESS_TEST_FILE,
    strategy_dir,
)

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


def clean_value(val):
    """Convert NaN/inf floats to None so ``json.dump`` can serialize them."""
    if isinstance(val, float):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    return val


def serialize_backtest_results(
    results: BacktestResults, strategy_key: str, strategy_info: dict
) -> dict:
    """
    Serialize backtest results to JSON-compatible format.

    Args:
        results: BacktestResults object
        strategy_key: Strategy identifier
        strategy_info: Strategy metadata

    Returns:
        Dictionary with all results data
    """
    # Convert portfolio history to list of dicts
    portfolio_history = []
    if hasattr(results.portfolio_history, "to_dict"):
        for idx, row in results.portfolio_history.iterrows():
            entry = row.to_dict() if hasattr(row, "to_dict") else dict(row)
            entry["date"] = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
            # Clean NaN values
            entry = {k: clean_value(v) for k, v in entry.items()}
            portfolio_history.append(entry)

    # Convert transactions to list of dicts
    transactions = []
    for t in results.transactions:
        transactions.append(
            {
                "date": (
                    t.timestamp.isoformat()
                    if hasattr(t.timestamp, "isoformat")
                    else str(t.timestamp)
                ),
                "symbol": t.symbol,
                "quantity": float(t.quantity),
                "price": float(t.price),
                "cost": float(t.total_cost),
            }
        )

    # Extract weights history if available
    weights_history = []
    if hasattr(results, "weights_history") and results.weights_history is not None:
        for idx, row in results.weights_history.iterrows():
            entry = row.to_dict() if hasattr(row, "to_dict") else dict(row)
            entry["date"] = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
            # Clean NaN values
            entry = {k: clean_value(v) for k, v in entry.items()}
            weights_history.append(entry)

    # Metrics via the canonical implementation (analytics.metrics): the
    # portfolio history is a rebalance-period series, NOT daily — the
    # annualization factor must be inferred from its actual spacing.
    values = pd.Series(
        results.portfolio_history["total_value"].astype(float),
        index=pd.DatetimeIndex(results.portfolio_history.index),
    )
    metrics = {k: clean_value(v) for k, v in summarize_performance(values).items()}
    metrics["metrics_version"] = METRICS_SCHEMA_VERSION
    metrics.update(
        {
            "final_value": clean_value(float(results.final_value)),
            "total_transactions": len(results.transactions),
            "rebalances": len(results.portfolio_history),
        }
    )

    return {
        "key": strategy_key,
        "info": strategy_info,
        "metrics": metrics,
        "portfolio_history": portfolio_history,
        "transactions": transactions,
        "weights_history": weights_history,
    }


def save_strategy_results(
    result_data: dict,
    strategy_key: str,
    results_dir: PathLike,
    stress_report: Optional[dict] = None,
    config: Optional[dict] = None,
) -> Path:
    """
    Save a single strategy's backtest results to
    ``<results_dir>/strategies/<strategy_key>/`` and merge it into
    ``strategies_index.json``.

    Supersedes the three pre-refactor writers in ``scripts/run_backtest.py``
    (the standalone function at :235, the ``--all`` inline block at
    ~774-858, and the legacy single/benchmark save at ~1043-1062). See the
    module docstring for exactly how their differing semantics were
    reconciled.

    Args:
        result_data: Dict as produced by ``serialize_backtest_results``
            (must contain the keys named in ``STRATEGY_FILES``: |
            ``portfolio_history``, ``transactions``, ``weights_history``,
            ``metrics``, ``info``).
        strategy_key: Strategy identifier (used as the directory name and
            index key).
        results_dir: Top-level results directory (e.g. ``Path("results")``).
        stress_report: Optional JSON-serialisable stress-test report
            (typically ``StressTestReport.to_dict()``). When provided,
            written to ``stress_test.json``; when omitted, no stress-test
            file is written or touched.
        config: Optional run config block (symbols, currency, capital,
            transaction costs, rebalance frequency, lookback days, ...).
            When provided, always overwrites ``strategies_index.json``'s
            ``config`` block; when omitted, any existing config block is
            left untouched.

    Returns:
        The per-strategy directory that was written to.
    """
    results_dir = Path(results_dir)
    target_dir = strategy_dir(results_dir, strategy_key)
    target_dir.mkdir(parents=True, exist_ok=True)

    for logical_name, filename in STRATEGY_FILES.items():
        with open(target_dir / filename, "w") as f:
            json.dump(result_data[logical_name], f, indent=2)

    logger.info(f"✓ Saved results for {strategy_key} to {target_dir}")

    if stress_report is not None:
        with open(target_dir / STRESS_TEST_FILE, "w") as f:
            json.dump(stress_report, f, indent=2)
        logger.info(f"  ✓ Stress test saved for {strategy_key}")

    # Merge into strategies_index.json (preserves the historical :235
    # merge semantics -- see module docstring for the reconciliation with
    # the --all inline block's full-rebuild behaviour).
    index_path = results_dir / INDEX_FILE
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                index_data = json.load(f)
        except Exception:
            index_data = {"strategies": {}, "config": {}}
    else:
        index_data = {"strategies": {}, "config": {}}

    index_data.setdefault("strategies", {})
    index_data["strategies"][strategy_key] = {
        "path": str(target_dir.relative_to(results_dir)),
        "metrics": result_data["metrics"],
        "info": result_data["info"],
    }
    index_data["run_date"] = datetime.now().isoformat()
    index_data["total_strategies"] = len(index_data["strategies"])
    if config is not None:
        # Always overwrite (union with the --all block's always-fresh
        # semantics; see module docstring point 2).
        index_data["config"] = config
    else:
        index_data.setdefault("config", {})

    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2)
    logger.info(
        f"✓ strategies_index.json updated ({index_data['total_strategies']} strategies)"
    )

    return target_dir
