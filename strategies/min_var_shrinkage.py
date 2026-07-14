"""
Shrinkage Minimum-Variance portfolio.

Minimum-variance optimization on a shrunk covariance matrix (Ledoit & Wolf,
2004, "Honey, I Shrunk the Sample Covariance Matrix", Journal of Portfolio
Management 30(4)). The sample covariance is noisy and its smallest eigenvalues
are biased downward, which min-variance optimization exploits and overfits;
shrinking it toward a structured target (here a scaled identity: the average
sample variance on the diagonal, zero off-diagonal) stabilises the optimizer and
improves out-of-sample risk. Distinct from MinimumVarianceStrategy (raw sample
covariance).

Long-only, weights sum to 1.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MinVarShrinkageStrategy(AllocationStrategy):
    """
    Shrinkage minimum-variance portfolio.

    Parameters:
        lookback_days: window for the sample covariance (default 252).
        shrinkage: intensity toward the scaled-identity target in [0, 1]
            (default 0.3). 0 = raw sample covariance, 1 = scaled identity.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        shrinkage: float = 0.3,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Shrinkage Minimum Variance")
        self.lookback_days = lookback_days
        self.shrinkage = float(np.clip(shrinkage, 0.0, 1.0))

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MinVarShrinkage requires 2+ assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Insufficient data for MinVarShrinkage (need 30+).")

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        S = returns.cov().values
        n = S.shape[0]

        # Shrinkage target: scaled identity (mean variance on diagonal).
        mu = np.trace(S) / n
        target = mu * np.eye(n)
        d = self.shrinkage
        cov = (1.0 - d) * S + d * target

        def port_var(w):
            return w @ cov @ w

        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = tuple((0.0, 1.0) for _ in range(n))
        w0 = np.ones(n) / n
        try:
            result = minimize(
                port_var, w0, method="SLSQP", bounds=bounds,
                constraints=constraints, options={"maxiter": 1000, "ftol": 1e-14},
            )
            if result.success:
                weights = np.clip(result.x, 0, None)
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum() if weights.sum() > 0 else w0
            else:
                logger.warning(
                    f"MinVarShrinkage did not converge: {result.message}. Equal weight."
                )
                weights = w0
        except Exception as e:
            logger.warning(f"MinVarShrinkage failed: {e}. Equal weight.")
            weights = w0

        symbols = list(prices.columns)
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        index = [symbol_to_name.get(s, s) for s in symbols]
        return pd.Series(weights, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
