"""
Maximum Omega-Ratio portfolio optimization strategy.

Maximizes the Omega ratio (Keating & Shadwick, 2002) — the ratio of
probability-weighted gains to losses relative to a threshold return:

    Omega(tau) = E[max(r - tau, 0)] / E[max(tau - r, 0)]

Unlike mean-variance or CVaR, Omega uses the entire return distribution
(all moments) and rewards upside above the threshold while penalizing
downside below it. Long-only, weights sum to 1. Falls back to equal weight
if optimization fails.
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class OmegaRatioStrategy(AllocationStrategy):
    """
    Maximum Omega-ratio portfolio.

    Parameters:
        lookback_days: Historical window for the return scenario matrix (252).
        threshold: Daily return threshold tau for gains/losses split (0.0).

    Maximizes portfolio Omega over the long-only simplex via SLSQP.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        threshold: float = 0.0,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Maximum Omega Ratio")
        self.lookback_days = lookback_days
        self.threshold = threshold

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Omega requires at least 2 assets, received {len(prices.columns)}."
            )

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for Omega. Need 30+ points, got {len(prices)}."
            )

        returns = prices.pct_change().dropna()
        R = returns.values  # T x N
        T, N = R.shape
        tau = self.threshold

        def neg_omega(w: np.ndarray) -> float:
            port = R @ w
            gains = np.maximum(port - tau, 0.0).mean()
            losses = np.maximum(tau - port, 0.0).mean()
            if losses < 1e-12:
                # No downside in-sample: treat as very high Omega (favourable).
                return -1e6 * (1.0 + gains)
            return -(gains / losses)

        try:
            w0 = np.ones(N) / N
            cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
            bounds = [(0.0, 1.0) for _ in range(N)]
            result = minimize(
                neg_omega,
                w0,
                method="SLSQP",
                bounds=bounds,
                constraints=cons,
                options={"maxiter": 300, "ftol": 1e-8},
            )
            if result.success:
                weights = np.clip(result.x, 0, None)
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum() if weights.sum() > 0 else w0
            else:
                logger.warning(
                    f"Omega optimization did not converge: {result.message}. "
                    "Falling back to equal weight."
                )
                weights = np.ones(N) / N
        except Exception as e:
            logger.warning(f"Omega optimization failed: {e}. Equal weight fallback.")
            weights = np.ones(N) / N

        symbols = list(prices.columns)
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        index = [symbol_to_name.get(s, s) for s in symbols]
        return pd.Series(weights, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
