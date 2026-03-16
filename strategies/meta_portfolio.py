"""
Meta-Portfolio Strategy.

Blends multiple underlying allocation strategies into a single set of
asset weights.  Each sub-strategy receives equal weight (1/N) and produces
its own asset weight vector; the final portfolio weights are the weighted
average across all sub-strategies.

This makes meta-portfolios directly back-testable via the standard engine,
which expects weights indexed by asset symbols (VUSA, SSLN, etc.), not by
sub-strategy names.

Example (JSON definition):
    {
        "type": "portfolio",
        "class": "MetaPortfolioStrategy",
        "name": "Meta: All-Season",
        "description": "...",
        "parameters": {},
        "underlying": [
            "allocations/momentum_top2",
            "allocations/risk_parity",
            "composed/min_var_with_constraints"
        ]
    }
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MetaPortfolioStrategy(AllocationStrategy):
    """
    Equal-weight meta-portfolio that blends multiple sub-strategies.

    For each rebalance:
    1. Each sub-strategy computes its own asset weights.
    2. Final weights = mean of all sub-strategy weight vectors.

    If a sub-strategy fails to compute weights, it is skipped and the
    remaining strategies are re-normalised to sum to 1.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or "Meta Portfolio",
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        all_symbols = sorted(set(
            sym
            for strat in self.underlying
            for sym in strat.get_symbols()
        ))

        blended = pd.Series(0.0, index=all_symbols)
        n_ok = 0

        for sub_strategy in self.underlying:
            try:
                sub_weights = sub_strategy.calculate_weights(context)
                # sub_weights may be indexed by strategy names or asset symbols;
                # normalise to asset symbols using get_symbols() mapping
                asset_weights = self._resolve_to_symbols(sub_weights, sub_strategy, all_symbols)
                blended += asset_weights
                n_ok += 1
            except Exception as e:
                logger.warning(
                    f"MetaPortfolio: sub-strategy {sub_strategy.name} failed: {e}, skipping"
                )

        if n_ok == 0:
            # All sub-strategies failed — equal weight fallback
            logger.warning("MetaPortfolio: all sub-strategies failed, using equal weight")
            return pd.Series(1.0 / len(all_symbols), index=all_symbols)

        blended /= n_ok

        # Normalise (floating-point safety)
        total = blended.sum()
        if total > 0:
            blended /= total

        return blended

    def get_strategy_lookback(self) -> int:
        """Use the maximum lookback across all sub-strategies."""
        lookbacks = []
        for strat in self.underlying:
            try:
                lookbacks.append(strat.get_data_requirements().lookback_days or 252)
            except Exception:
                lookbacks.append(252)
        return max(lookbacks) if lookbacks else 252

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_to_symbols(
        self,
        weights: pd.Series,
        sub_strategy: Strategy,
        all_symbols: List[str],
    ) -> pd.Series:
        """
        Convert a weight Series indexed by asset symbols or strategy names
        into one that is always indexed by asset symbols.

        Priority:
        1. If the weight index already contains asset symbols, use directly.
        2. Otherwise attempt name → symbol mapping via sub-strategy leaves.
        """
        result = pd.Series(0.0, index=all_symbols)

        # Fast path: all weight labels are already asset symbols
        if all(label in all_symbols for label in weights.index):
            for sym, w in weights.items():
                result[sym] = w
            total = result.sum()
            if total > 0:
                result /= total
            return result

        # Slow path: build name → symbol mapping by traversing underlying leaves
        name_to_symbols: dict[str, List[str]] = {}

        def _collect_leaves(strat: Strategy) -> None:
            underlying = getattr(strat, 'underlying', None)
            if underlying is None:
                # Leaf node (AssetStrategy)
                for sym in strat.get_symbols():
                    name_to_symbols.setdefault(strat.name, []).append(sym)
            elif isinstance(underlying, list):
                for child in underlying:
                    _collect_leaves(child)
            else:
                _collect_leaves(underlying)

        _collect_leaves(sub_strategy)

        for idx_label, w in weights.items():
            if idx_label in all_symbols:
                result[idx_label] += w
            elif idx_label in name_to_symbols:
                syms = name_to_symbols[idx_label]
                for sym in syms:
                    if sym in result.index:
                        result[sym] += w / len(syms)

        total = result.sum()
        if total > 0:
            result /= total

        return result
