"""
Risk Parity (Equal Risk Contribution) portfolio optimization strategy.

Each asset contributes equally to total portfolio risk. Unlike HRP which uses
hierarchical clustering, Risk Parity directly optimizes for equal marginal
risk contributions.

Example:
    from strategies.core import AssetStrategy
    from strategies.risk_parity import RiskParityStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    rp = RiskParityStrategy(underlying=assets)
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class RiskParityStrategy(AllocationStrategy):
    """
    Risk Parity (Equal Risk Contribution) portfolio optimization.

    Finds weights such that each asset's marginal risk contribution equals 1/N
    of total portfolio risk:
        w_i * (Cov * w)_i / (w' * Cov * w) = 1/N  for all i

    Falls back to inverse-volatility weighting if optimization fails.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        name: str = None
    ):
        super().__init__(underlying, name=name or "Risk Parity")

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Risk Parity requires at least 2 assets, received {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data. Need 30+ data points, got {len(prices)}."
            )

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        returns = prices.pct_change().dropna()
        cov = returns.cov().values
        n = len(prices.columns)

        # Target: equal risk contribution (1/N each)
        target_risk = np.ones(n) / n

        def risk_contribution_error(w):
            """Sum of squared differences from target risk contribution."""
            w = np.maximum(w, 1e-10)
            port_var = w @ cov @ w
            if port_var == 0:
                return 1e10
            # Marginal risk contribution: w_i * (Cov @ w)_i / port_var
            marginal = w * (cov @ w) / port_var
            return np.sum((marginal - target_risk) ** 2)

        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        bounds = tuple((1e-6, 1.0) for _ in range(n))

        # Start from inverse-volatility weights (good initial guess)
        vols = np.sqrt(np.diag(cov))
        vols[vols == 0] = 1e-10
        w0 = (1.0 / vols)
        w0 = w0 / w0.sum()

        try:
            result = minimize(
                risk_contribution_error,
                w0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-14}
            )

            if result.success and result.fun < 1e-6:
                weights = result.x
                weights[weights < 1e-6] = 0
                if weights.sum() > 0:
                    weights = weights / weights.sum()
                else:
                    weights = w0
            else:
                logger.warning(
                    f"Risk Parity optimization did not converge (err={result.fun:.2e}). "
                    "Using inverse-volatility weights."
                )
                weights = w0

        except Exception as e:
            logger.warning(f"Risk Parity optimization failed: {e}. Using inverse-vol weights.")
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
        return 252
