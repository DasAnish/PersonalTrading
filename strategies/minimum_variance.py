"""
Minimum Variance portfolio optimization strategy.

Finds the portfolio with the lowest possible volatility using quadratic
optimization. This is the leftmost point on the efficient frontier.

Example:
    from strategies.core import AssetStrategy
    from strategies.minimum_variance import MinimumVarianceStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    min_var = MinimumVarianceStrategy(underlying=assets)
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MinimumVarianceStrategy(AllocationStrategy):
    """
    Minimum Variance portfolio optimization.

    Finds weights that minimize portfolio variance: min w'Cov*w
    subject to: sum(w) = 1, w >= 0 (long-only)

    Falls back to equal weight if optimization fails.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        name: str = None
    ):
        super().__init__(underlying, name=name or "Minimum Variance")

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MinVar requires at least 2 assets, received {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for MinVar. Need 30+ data points, got {len(prices)}."
            )

        # Handle NaN values
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        returns = prices.pct_change().dropna()
        cov = returns.cov().values
        n = len(prices.columns)

        # Objective: minimize portfolio variance w'Cov*w
        def portfolio_variance(w):
            return w @ cov @ w

        # Constraints: weights sum to 1
        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}

        # Bounds: long-only (0 to 1)
        bounds = tuple((0.0, 1.0) for _ in range(n))

        # Initial guess: equal weight
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
                weights = result.x
                # Clean up near-zero weights
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum()
            else:
                logger.warning(
                    f"MinVar optimization did not converge: {result.message}. "
                    "Falling back to equal weight."
                )
                weights = np.ones(n) / n

        except Exception as e:
            logger.warning(f"MinVar optimization failed: {e}. Falling back to equal weight.")
            weights = np.ones(n) / n

        # Map to strategy names
        symbols = list(prices.columns)
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name

        index = [symbol_to_name.get(s, s) for s in symbols]
        return pd.Series(weights, index=index)

    def get_strategy_lookback(self) -> int:
        return 252
