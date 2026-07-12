"""
Maximum Diversification Portfolio optimization strategy.

Maximises the diversification ratio: (weighted avg constituent volatility) / portfolio volatility.
Rewards low pairwise correlation rather than minimising variance directly.

Example:
    from strategies.core import AssetStrategy
    from strategies.maximum_diversification import MaximumDiversificationStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    max_div = MaximumDiversificationStrategy(underlying=assets, cov_lookback_days=252)
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import List, Optional
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MaximumDiversificationStrategy(AllocationStrategy):
    """
    Maximum Diversification Portfolio optimization.

    Maximises the diversification ratio: DR(w) = (w · sigma) / sqrt(w' Σ w)
    where sigma is the vector of individual asset volatilities and Σ is the
    covariance matrix.

    Subject to: sum(w) = 1, 0 <= w_i <= max_weight_cap
    Falls back to inverse-volatility weighting if optimization fails.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        cov_lookback_days: int = 252,
        max_weight_cap: Optional[float] = None,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            cov_lookback_days: Lookback for covariance calculation (default 252)
            max_weight_cap: Maximum weight per asset (default None = no cap, i.e. 1.0)
            name: Display name
        """
        super().__init__(underlying, name=name or "Maximum Diversification")
        self.cov_lookback_days = cov_lookback_days
        self.max_weight_cap = max_weight_cap if max_weight_cap is not None else 1.0

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MaxDiv requires at least 2 assets, received {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for MaxDiv. Need 30+ data points, got {len(prices)}."
            )

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        lookback_prices = prices.iloc[-self.cov_lookback_days :]
        returns = lookback_prices.pct_change().dropna()
        cov = returns.cov().values
        sigmas = returns.std().values
        n = len(prices.columns)

        # Guard against ill-conditioned covariance matrices
        cond_number = np.linalg.cond(cov)
        if cond_number > 1e8:
            ridge_coefficient = 1e-6
            logger.warning(
                f"Covariance matrix ill-conditioned (cond={cond_number:.2e}). "
                "Applying ridge regularization."
            )
            base_cov = cov
            cov = base_cov + ridge_coefficient * np.trace(base_cov) / n * np.eye(n)
            cond_number = np.linalg.cond(cov)
            if cond_number > 1e8:
                ridge_coefficient *= 100
                logger.warning(
                    f"Covariance matrix still ill-conditioned after ridge "
                    f"(cond={cond_number:.2e}). Escalating ridge coefficient "
                    f"to {ridge_coefficient:.2e}."
                )
                cov = base_cov + ridge_coefficient * np.trace(base_cov) / n * np.eye(n)

        # Objective: minimize -DR(w) = -(w · sigma) / sqrt(w' Σ w)
        def neg_diversification_ratio(w):
            """Negative diversification ratio (for minimization)."""
            numerator = np.dot(w, sigmas)
            if numerator == 0:
                return 1e10
            denominator = np.sqrt(w @ cov @ w)
            if denominator == 0:
                return 1e10
            return -numerator / denominator

        # Constraints: weights sum to 1
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

        # Bounds: long-only with optional cap
        bounds = tuple((0.0, self.max_weight_cap) for _ in range(n))

        # Initial guess: inverse-volatility weights (good starting point)
        sigmas_safe = sigmas.copy()
        sigmas_safe[sigmas_safe == 0] = 1e-10
        w0 = 1.0 / sigmas_safe
        w0 = w0 / w0.sum()

        try:
            result = minimize(
                neg_diversification_ratio,
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
                    f"MaxDiv optimization did not converge: {result.message}. "
                    "Falling back to inverse-volatility weights."
                )
                weights = w0

        except Exception as e:
            logger.warning(
                f"MaxDiv optimization failed: {e}. Falling back to inverse-volatility weights."
            )
            weights = w0

        # Map to strategy names
        symbols = list(prices.columns)
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name

        index = [symbol_to_name.get(s, s) for s in symbols]
        return pd.Series(weights, index=index)

    def get_strategy_lookback(self) -> int:
        return self.cov_lookback_days
