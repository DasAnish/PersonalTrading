"""
Downside Risk Parity portfolio.

Equalizes each asset's contribution to portfolio *downside* risk, using the
semicovariance matrix (co-movements of below-target returns) in place of the
full covariance matrix used by the standard equal-risk-contribution risk parity
(Maillard, Roncalli & Teiletche). Risk budgeting with alternative (downside)
risk measures is discussed in Roncalli (2013), "Introduction to Risk Parity and
Budgeting", Chapman & Hall/CRC. This equalizes downside-risk contributions
rather than full-volatility contributions (RiskParityStrategy) and rather than
minimizing downside variance (MinimumSemivarianceStrategy).

Long-only, weights sum to 1. Falls back to inverse-downside-vol weights.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class DownsideRiskParityStrategy(AllocationStrategy):
    """
    Equal downside-risk-contribution portfolio.

    Parameters:
        lookback_days: window for the semicovariance estimate (default 252).
        target_return: daily threshold below which returns count as downside
            (default 0.0).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        target_return: float = 0.0,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Downside Risk Parity")
        self.lookback_days = lookback_days
        self.target_return = target_return

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"DownsideRiskParity requires 2+ assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Insufficient data for DownsideRiskParity (need 30+).")

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        dev = np.minimum(returns.values - self.target_return, 0.0)  # T x N, <= 0
        T = dev.shape[0]
        semicov = (dev.T @ dev) / T  # N x N semicovariance
        n = returns.shape[1]
        target_risk = np.ones(n) / n

        def rc_error(w):
            w = np.maximum(w, 1e-10)
            port = w @ semicov @ w
            if port <= 0:
                return 1e10
            marginal = w * (semicov @ w) / port
            return np.sum((marginal - target_risk) ** 2)

        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = tuple((1e-6, 1.0) for _ in range(n))
        dvols = np.sqrt(np.diag(semicov))
        dvols[dvols == 0] = 1e-10
        w0 = 1.0 / dvols
        w0 = w0 / w0.sum()

        try:
            result = minimize(
                rc_error, w0, method="SLSQP", bounds=bounds,
                constraints=constraints, options={"maxiter": 1000, "ftol": 1e-14},
            )
            if result.success and result.fun < 1e-6:
                weights = result.x
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum() if weights.sum() > 0 else w0
            else:
                logger.warning(
                    f"DownsideRiskParity did not converge (err={result.fun:.2e}). "
                    "Using inverse-downside-vol weights."
                )
                weights = w0
        except Exception as e:
            logger.warning(f"DownsideRiskParity failed: {e}. Inverse-downside-vol.")
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
