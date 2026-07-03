"""
Group PBO for composed/overlay strategy families.

Composed strategies (e.g. vol-target overlay variants of the same base
allocation strategy, like ``hrp_15vol`` / ``hrp_30vol``) never get a PBO
from a single ``ParameterSweep`` — each variant is backtested independently
via ``scripts/run_backtest.py``, so there is no shared return matrix. This
module groups such strategies by their shared base allocation strategy and
overlay class, reassembles a return matrix from their existing results via
``analytics.family_matrix.build_family_return_matrix``, and runs CSCV
(``analytics.overfitting.calculate_pbo``, via ``run_overfitting_analysis``)
on any group with enough usable members.

Split out of ``scripts/run_all_overfitting.py`` (Phase 6) to keep that
script under the project's 600-line-per-file guideline.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from analytics.family_matrix import build_family_return_matrix
from analytics.overfitting import run_overfitting_analysis
from analytics.overfitting_results import OverfittingAnalysis
from strategies.strategy_loader import StrategyLoader

logger = logging.getLogger(__name__)


def group_composed_strategies(strategy_keys: List[str]) -> Dict[Tuple, List[str]]:
    """
    Group composed/overlay strategy keys sharing the same base allocation
    strategy (class + parameters) and the same overlay class, e.g. the
    "hrp_15vol" / "hrp_30vol" family (same underlying HRP(ward), different
    ``target_vol``). Non-composed or unreadable definitions are skipped.
    """
    loader = StrategyLoader()
    groups: Dict[Tuple, List[str]] = defaultdict(list)
    for key in strategy_keys:
        try:
            definition = loader.load_definition(key)
        except Exception:
            continue
        if definition.get("type") != "composed":
            continue
        underlying = definition.get("underlying") or {}
        group_key = (
            definition.get("class"),
            underlying.get("class"),
            tuple(sorted((underlying.get("parameters") or {}).items())),
        )
        groups[group_key].append(key)
    return groups


def run_composed_pbo_groups(
    strategy_keys: List[str],
    results_dir: Path,
    n_folds: int,
    save_fn: Callable[[OverfittingAnalysis, str], None],
) -> List[dict]:
    """
    Group PBO for composed/overlay strategy families with >= 4 usable
    members. ``results_dir`` is the top-level results directory (parent of
    ``results/strategies/``). ``save_fn(analysis, key)`` persists each
    group's ``OverfittingAnalysis`` (e.g. ``scripts/run_all_overfitting.py
    ::save_analysis``) — kept as a callback so this module has no
    dependency on the script's on-disk layout choices.
    """
    rows: List[dict] = []
    for group_key, members in group_composed_strategies(strategy_keys).items():
        if len(members) < 4:
            continue

        matrix = build_family_return_matrix(results_dir, sorted(members))
        if matrix.shape[1] < 4:
            logger.warning(
                "Composed PBO group %s: only %d/%d siblings have usable "
                "portfolio_history — skipping (<4).",
                group_key,
                matrix.shape[1],
                len(members),
            )
            continue

        t_total = matrix.shape[0]
        s_subsets = 16 if t_total >= 32 else 8
        if t_total < s_subsets:
            logger.warning(
                "Composed PBO group %s: T=%d too short for s_subsets=%d — " "skipping.",
                group_key,
                t_total,
                s_subsets,
            )
            continue
        if s_subsets == 8:
            logger.info(
                "Composed PBO group %s: T=%d < 32, falling back to "
                "s_subsets=8 (paper default is 16).",
                group_key,
                t_total,
            )

        group_label = f"{sorted(matrix.columns)[0]}_group__composed_pbo_sweep"
        best_col = matrix.mean().idxmax()
        best_returns = matrix[best_col]

        analysis = run_overfitting_analysis(
            strategy_key=group_label,
            strategy_returns=best_returns,
            return_matrix=matrix,
            param_grid={"members": sorted(matrix.columns)},
            periods_per_year=12,
            s_subsets=s_subsets,
            n_folds=n_folds,
        )
        save_fn(analysis, group_label)

        rows.append(
            {
                "group": group_label,
                "members": matrix.shape[1],
                "s_subsets": s_subsets,
                "pbo": f"{analysis.pbo.pbo:.4f}" if analysis.pbo else "N/A",
                "pbo_verdict": analysis.pbo.verdict if analysis.pbo else "N/A",
            }
        )

    return rows
