"""
Adaptive Asset Allocation strategy (Keller & Keuning, 2012).

Two-step approach:
1. **Momentum Screening**: Rank all assets by trailing return over a
   medium-term lookback (e.g. 6 months).  Select the top N assets.
2. **Minimum-Variance Optimisation**: Among the selected assets, solve for
   the minimum-variance portfolio weights rather than using simple inverse-
   volatility heuristics.

The insight: momentum picks the universe of "good" assets; min-var then
efficiently allocates within that universe, accounting for correlations.
This beats pure momentum (better diversification) and pure min-var (better
asset selection) in many regime studies.

Parameters
----------
top_n : int
    Number of top-momentum assets to include (default 2).
lookback_days : int
    Return lookback for momentum ranking (default 126 = 6 months).
min_weight : float
    Lower bound per asset in the min-var optimisation (default 0.05).
max_weight : float
    Upper bound per asset (default 0.60).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class AdaptiveAssetAllocationStrategy(AllocationStrategy):
    """
    Adaptive Asset Allocation: momentum screen + minimum-variance allocation.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 2,
        lookback_days: int = 126,
        min_weight: float = 0.05,
        max_weight: float = 0.60,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Adaptive Asset Allocation (top_{top_n})",
        )
        self.top_n = min(top_n, len(underlying))
        self.lookback_days = lookback_days
        self.min_weight = min_weight
        self.max_weight = max_weight

    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(self.lookback_days + 10, 40)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        symbol_to_name = self._build_name_map()
        all_index = [symbol_to_name.get(s, s) for s in prices.columns]

        # Step 1: Momentum ranking
        lookback_prices = prices.iloc[-self.lookback_days:]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1
        ranked = trailing_returns.sort_values(ascending=False)
        selected = ranked.index[:self.top_n].tolist()

        logger.debug(
            f"AAA momentum rankings: {dict(ranked.round(4))}. Selected: {selected}"
        )

        if len(selected) < 2:
            # Fall back to equal weight across all assets
            return self._equal_weight(prices)

        # Step 2: Minimum-variance on selected assets
        selected_prices = prices[selected]
        returns = selected_prices.pct_change().dropna()
        cov = returns.cov().values
        n = len(selected)

        def portfolio_variance(w):
            return w @ cov @ w

        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        bounds = [(self.min_weight, self.max_weight)] * n
        w0 = np.ones(n) / n

        try:
            result = minimize(
                portfolio_variance,
                w0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-12}
            )
            if result.success:
                sel_weights = result.x
                sel_weights[sel_weights < 1e-6] = 0.0
                sel_weights /= sel_weights.sum()
            else:
                logger.warning(f"AAA min-var failed: {result.message}, using inv-vol")
                vols = returns.std().clip(lower=1e-10)
                sel_weights = (1.0 / vols).values
                sel_weights /= sel_weights.sum()
        except Exception as e:
            logger.warning(f"AAA min-var error: {e}, using inv-vol")
            vols = returns.std().clip(lower=1e-10)
            sel_weights = (1.0 / vols).values
            sel_weights /= sel_weights.sum()

        # Build full weight vector (zeros for non-selected)
        weights = pd.Series(0.0, index=all_index)
        for i, sym in enumerate(selected):
            name = symbol_to_name.get(sym, sym)
            weights[name] = sel_weights[i]

        return weights

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
