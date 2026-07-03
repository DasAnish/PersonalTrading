"""
Assemble return matrices from existing sibling backtest results.

Split out from ``analytics/overfitting.py`` (Phase 6, to help keep that file
under the 600-line limit) — used to run PBO on composed/overlay strategy
families that were never run through a single ``ParameterSweep`` (and so
never got a ``return_matrix`` from ``ParameterSweep.get_return_matrix``),
by reassembling one from each sibling's already-computed
``portfolio_history.json``.
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from backtesting.results_schema import PathLike, load_portfolio_values

logger = logging.getLogger(__name__)


def build_family_return_matrix(
    results_dir: PathLike, family_keys: List[str]
) -> pd.DataFrame:
    """
    Assemble a (T, N) return matrix from existing sibling strategy results.

    Loads each sibling's ``portfolio_history.json`` via
    ``backtesting.results_schema.load_portfolio_values``, converts to
    percentage returns (``pct_change``), and inner-joins on date so every
    column shares exactly the same time index — required for CSCV/PBO
    (``analytics.overfitting.calculate_pbo``), which assumes a shared time
    axis across configurations.

    Parameters
    ----------
    results_dir : str or Path
        Top-level results directory (e.g. ``"results"``) — same argument as
        ``results_schema.strategy_dir``'s ``results_dir``.
    family_keys : list of str
        Strategy result keys forming one PBO group (e.g. a composed
        strategy family's vol-target variants sharing the same base
        allocation strategy).

    Returns
    -------
    pd.DataFrame
        Shape ``(T, N)`` with ``N <= len(family_keys)``. Siblings whose
        ``portfolio_history.json`` is missing or empty are silently
        skipped (logged at INFO) rather than raising — callers should gate
        on ``N >= 4`` (or whatever minimum CSCV needs) themselves, since a
        family with too few *usable* siblings should be reported, not
        crash the batch run. Returns an empty DataFrame if no sibling has
        usable data.
    """
    series_by_key: dict = {}
    for key in family_keys:
        values = load_portfolio_values(results_dir, key)
        if values.empty:
            logger.info(
                "build_family_return_matrix: no portfolio_history.json (or "
                "empty) for %s — skipping.",
                key,
            )
            continue
        returns = values.pct_change().dropna()
        if returns.empty:
            logger.info(
                "build_family_return_matrix: %s has no return observations "
                "after pct_change — skipping.",
                key,
            )
            continue
        series_by_key[key] = returns

    if not series_by_key:
        return pd.DataFrame()

    # pd.DataFrame(dict-of-Series) outer-joins on the union of indices,
    # filling gaps with NaN; dropna(how="any") then reduces that to the
    # inner join — only dates present (and non-null) across every column.
    matrix = pd.DataFrame(series_by_key).dropna(how="any")
    return matrix
