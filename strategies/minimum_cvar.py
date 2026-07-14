"""
Minimum CVaR (Conditional Value at Risk) portfolio optimization strategy.

Minimizes the expected loss beyond the Value at Risk threshold using the
Rockafellar-Uryasev (2000) linear programming formulation. CVaR is the mean of
the worst alpha% of returns, providing tail-risk protection.

Example:
    from strategies.core import AssetStrategy
    from strategies.minimum_cvar import MinimumCVaRStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    min_cvar = MinimumCVaRStrategy(underlying=assets)
"""

import pandas as pd
import numpy as np
from scipy.optimize import linprog
from typing import List, Optional
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MinimumCVaRStrategy(AllocationStrategy):
    """
    Minimum CVaR portfolio optimization via Rockafellar-Uryasev LP.

    Finds weights that minimize Conditional Value at Risk (expected loss beyond
    the alpha-th percentile) using the reformulated LP:
        min  VaR + (1/((1-alpha)*T)) * sum(u_t)
    subject to:
        u_t >= -R_t.w - VaR  for all t
        u_t >= 0  for all t
        sum(w) = 1
        w >= 0 (long-only)

    Parameters:
        lookback_days: Historical window for scenario matrix (default 252)
        alpha: Confidence level for CVaR (default 0.95 = 95th percentile)

    Falls back to equal weight if optimization fails.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        alpha: float = 0.95,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Minimum CVaR")
        self.lookback_days = lookback_days
        self.alpha = alpha

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MinCVaR requires at least 2 assets, received {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for MinCVaR. Need 30+ data points, got {len(prices)}."
            )

        # Handle NaN values
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        returns = prices.pct_change().dropna()
        R = returns.values  # T x N scenario matrix
        T, N = R.shape

        # Rockafellar-Uryasev LP formulation:
        # Variables: [w (N), VaR (1), u (T)]
        # Total: N + 1 + T variables

        # Objective: minimize VaR + (1/((1-alpha)*T)) * sum(u_t)
        # c = [0, ..., 0,  1,      1/((1-alpha)*T), ..., 1/((1-alpha)*T)]
        #      <-- N -->   ^VaR     <------ T ------>
        tau = 1.0 / ((1.0 - self.alpha) * T)
        c = np.concatenate([np.zeros(N), [1.0], tau * np.ones(T)])

        # Inequality constraints: -u_t + R_t.w + VaR <= 0 for all t
        # Rewritten as: [R_t, 1, -1 in position t, 0 elsewhere] w_vars <= 0
        A_ub_list = []
        for t in range(T):
            row = np.zeros(N + 1 + T)
            row[:N] = R[t, :]  # Coefficients for w
            row[N] = 1.0  # Coefficient for VaR
            row[N + 1 + t] = -1.0  # Coefficient for u_t
            A_ub_list.append(row)

        A_ub = np.array(A_ub_list)
        b_ub = np.zeros(T)

        # Equality constraint: sum(w) = 1
        A_eq = np.zeros((1, N + 1 + T))
        A_eq[0, :N] = 1.0
        b_eq = np.array([1.0])

        # Bounds: w >= 0, VaR unbounded, u >= 0
        bounds = (
            [(0.0, 1.0) for _ in range(N)]
            + [(None, None)]
            + [(0.0, None) for _ in range(T)]
        )

        try:
            result = linprog(
                c,
                A_ub=A_ub,
                b_ub=b_ub,
                A_eq=A_eq,
                b_eq=b_eq,
                bounds=bounds,
                method="highs",
            )

            if result.success:
                weights = result.x[:N]
                # Clean up near-zero weights
                weights[weights < 1e-6] = 0
                if weights.sum() > 0:
                    weights = weights / weights.sum()
                else:
                    logger.warning("CVaR weights summed to zero; using equal weight.")
                    weights = np.ones(N) / N
            else:
                logger.warning(
                    f"MinCVaR optimization did not converge: {result.message}. "
                    "Falling back to equal weight."
                )
                weights = np.ones(N) / N

        except Exception as e:
            logger.warning(
                f"MinCVaR optimization failed: {e}. Falling back to equal weight."
            )
            weights = np.ones(N) / N

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
