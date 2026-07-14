"""
Minimum CDaR (Conditional Drawdown-at-Risk) portfolio optimization.

Minimizes the Conditional Drawdown-at-Risk (Chekhlov, Uryasev & Zabarankin,
2005, "Drawdown Measure in Portfolio Optimization", International Journal of
Theoretical and Applied Finance 8(1)) — the average of the worst (1 - alpha)
fraction of drawdowns along the portfolio's cumulative return path. Unlike
variance, CVaR or semivariance (all point-in-time measures), CDaR is
path-dependent and directly targets sustained peak-to-trough losses.

Long-only, weights sum to 1. Minimized via SLSQP from an equal-weight start;
being a risk-minimization objective it diversifies rather than concentrates.
Falls back to equal weight on failure.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MinimumCDaRStrategy(AllocationStrategy):
    """
    Minimum Conditional Drawdown-at-Risk portfolio.

    Parameters:
        lookback_days: window for the return path (default 252).
        alpha: confidence level; CDaR averages the worst (1-alpha) drawdowns
            (default 0.95 -> worst 5% of drawdown observations).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        alpha: float = 0.95,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Minimum CDaR")
        self.lookback_days = lookback_days
        self.alpha = alpha

    def _cdar(self, w: np.ndarray, R: np.ndarray) -> float:
        port = R @ w
        cum = np.cumsum(port)
        running_max = np.maximum.accumulate(cum)
        drawdowns = running_max - cum  # >= 0
        k = max(1, int(round((1.0 - self.alpha) * len(drawdowns))))
        worst = np.sort(drawdowns)[-k:]
        return float(worst.mean())

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"MinCDaR requires at least 2 assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for MinCDaR. Need 30+, got {len(prices)}."
            )

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        R = returns.values
        N = R.shape[1]

        try:
            w0 = np.ones(N) / N
            cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
            bounds = [(0.0, 1.0) for _ in range(N)]
            result = minimize(
                self._cdar,
                w0,
                args=(R,),
                method="SLSQP",
                bounds=bounds,
                constraints=cons,
                options={"maxiter": 300, "ftol": 1e-9},
            )
            if result.success:
                weights = np.clip(result.x, 0, None)
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum() if weights.sum() > 0 else w0
            else:
                logger.warning(
                    f"MinCDaR did not converge: {result.message}. Equal weight."
                )
                weights = np.ones(N) / N
        except Exception as e:
            logger.warning(f"MinCDaR optimization failed: {e}. Equal weight.")
            weights = np.ones(N) / N

        symbols = list(prices.columns)
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        index = [symbol_to_name.get(s, s) for s in symbols]
        return pd.Series(weights, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
