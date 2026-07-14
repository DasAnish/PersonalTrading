"""
Minimum Semivariance portfolio optimization strategy.

Minimizes downside risk (deviations below a target return) using semicovariance
matrix. Unlike minimum variance which penalizes all deviations equally, semivariance
focuses only on negative deviations (downside).

Example:
    from strategies.core import AssetStrategy
    from strategies.minimum_semivariance import MinimumSemivarianceStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    min_semi = MinimumSemivarianceStrategy(underlying=assets)
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import List, Optional
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MinimumSemivarianceStrategy(AllocationStrategy):
    """
    Minimum Semivariance portfolio optimization.

    Finds weights that minimize portfolio downside risk using the semicovariance
    matrix: min w'S*w where S is semicovariance below a target return,
    subject to: sum(w) = 1, w >= 0 (long-only).

    Parameters:
        lookback_days: Historical window for semivariance calculation (default 252)
        target_return: Threshold return for downside calculation (default 0.0)
        min_weight: Minimum weight per asset (optional)
        max_weight: Maximum weight per asset (optional)

    Falls back to equal weight if optimization fails.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        target_return: float = 0.0,
        min_weight: Optional[float] = None,
        max_weight: Optional[float] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Minimum Semivariance")
        self.lookback_days = lookback_days
        self.target_return = target_return
        self.min_weight = min_weight or 0.0
        self.max_weight = max_weight or 1.0

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MinSemi requires at least 2 assets, received {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for MinSemi. Need 30+ data points, got {len(prices)}."
            )

        # Handle NaN values
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        returns = prices.pct_change().dropna()
        n = len(prices.columns)

        # Compute downside deviations: d = min(r - target, 0)
        downside = np.minimum(returns.values - self.target_return, 0)

        # Build semicovariance matrix: S[i,j] = mean(d_i * d_j)
        semi_cov = (downside.T @ downside) / len(downside)

        # Guard against ill-conditioned matrices
        cond_number = np.linalg.cond(semi_cov)
        if cond_number > 1e8:
            ridge_coefficient = 1e-6
            logger.warning(
                f"Semicovariance matrix ill-conditioned (cond={cond_number:.2e}). "
                "Applying ridge regularization."
            )
            base_cov = semi_cov
            semi_cov = (
                base_cov
                + ridge_coefficient * np.trace(base_cov) / n * np.eye(n)
            )
            cond_number = np.linalg.cond(semi_cov)
            if cond_number > 1e8:
                ridge_coefficient *= 100
                logger.warning(
                    f"Semicovariance matrix still ill-conditioned after ridge "
                    f"(cond={cond_number:.2e}). Escalating ridge coefficient."
                )
                semi_cov = (
                    base_cov
                    + ridge_coefficient * np.trace(base_cov) / n * np.eye(n)
                )

        # Objective: minimize portfolio semivariance w'S*w
        def portfolio_semivariance(w):
            return w @ semi_cov @ w

        # Constraints: weights sum to 1
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

        # Bounds: long-only with optional min/max caps
        bounds = tuple((self.min_weight, self.max_weight) for _ in range(n))

        # Initial guess: equal weight
        w0 = np.ones(n) / n

        try:
            result = minimize(
                portfolio_semivariance,
                w0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 1000, "ftol": 1e-12},
            )

            if result.success:
                weights = result.x
                # Clean up near-zero weights
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum()
            else:
                logger.warning(
                    f"MinSemi optimization did not converge: {result.message}. "
                    "Falling back to equal weight."
                )
                weights = np.ones(n) / n

        except Exception as e:
            logger.warning(
                f"MinSemi optimization failed: {e}. Falling back to equal weight."
            )
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
        return self.lookback_days
