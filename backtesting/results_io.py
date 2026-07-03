"""
Write-side of the on-disk backtest results contract.

Moved from ``scripts/run_backtest.py`` (Phase 3 refactor):
    ``clean_value``                (nested helper inside ``serialize_backtest_results``, :312)
    ``serialize_backtest_results`` (:297)
    ``save_strategy_results``      (:235) -- reconciled with the two other
        ad-hoc save code paths that existed inline in ``run_backtest.py``:
        the ``--all`` per-strategy loop (~774-858) and the legacy
        single-vs-benchmark save (~1043-1062).

All three call sites now go through the single ``save_strategy_results``
below. Filenames are never hard-coded here -- everything comes from
``backtesting.results_schema``.

Reconciliation of the three historical save paths
---------------------------------------------------
The three pre-refactor writers agreed on *what* to write (the five
``STRATEGY_FILES``) but disagreed on two things:

1. **Index update: merge vs. rebuild.**
   The function at :235 read the existing ``strategies_index.json`` (if
   any) and merged in just the one strategy's entry. The ``--all`` inline
   block instead built a brand-new ``strategy_index`` dict from scratch in
   memory across its whole loop and wrote it out once at the end -- so a
   stale entry for a strategy that no longer exists in the current
   ``--all`` run would be dropped.

   This module's ``save_strategy_results`` **always merges** (preserves
   the :235 semantics) -- it is a single-strategy save primitive and has
   no visibility into "every strategy in this run" to decide what to drop.
   The caller that wants full-rebuild behaviour (``run_backtest.py``'s
   ``--all`` mode) now gets it explicitly by deleting
   ``strategies_index.json`` once *before* its per-strategy save loop
   starts; each subsequent call then merges into a growing, run-scoped
   index, which nets out to the same "current run only" content the old
   inline rebuild produced. The legacy single/benchmark path does **not**
   reset the index first, so it preserves entries from unrelated prior
   runs -- matching the old :235 function's behaviour.

2. **Config block: setdefault vs. always-write.**
   The :235 function only wrote ``index_data["config"]`` if the key was
   *absent* (``dict.setdefault``), so a stale config from a much older run
   could survive indefinitely. The ``--all`` inline block always
   overwrote ``config`` with the current run's values.

   This module **always writes** the supplied ``config`` block when the
   caller passes one (matching the ``--all`` block's fresher behaviour).
   Passing ``config=None`` leaves any existing config block untouched,
   which callers that don't have a config handy (e.g. tests) can rely on.

Stress-test results are optional and orthogonal to both of the above: pass
a JSON-serialisable ``stress_report`` dict (typically
``StressTestReport.to_dict()``) and ``stress_test.json`` is written
alongside the other per-strategy files; omit it (default ``None``) and no
stress-test file is written or touched.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import numpy as np

from .engine import BacktestResults
from .results_schema import INDEX_FILE, STRATEGY_FILES, STRESS_TEST_FILE, strategy_dir

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

    # Calculate metrics
    portfolio_values = results.portfolio_history["total_value"].values
    returns = np.diff(portfolio_values) / portfolio_values[:-1]

    total_return = (portfolio_values[-1] - portfolio_values[0]) / portfolio_values[0]
    volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
    sharpe_ratio = (np.mean(returns) * 252) / volatility if volatility > 0 else 0

    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

    return {
        "key": strategy_key,
        "info": strategy_info,
        "metrics": {
            "total_return": clean_value(float(total_return)),
            "volatility": clean_value(float(volatility)),
            "sharpe_ratio": clean_value(float(sharpe_ratio)),
            "max_drawdown": clean_value(float(max_drawdown)),
            "final_value": clean_value(float(results.final_value)),
            "total_transactions": len(results.transactions),
            "rebalances": len(results.portfolio_history),
        },
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
