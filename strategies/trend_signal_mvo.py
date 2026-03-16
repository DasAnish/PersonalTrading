"""
Trend-Signal Mean-Variance Optimisation Strategy.

Uses EWMA momentum signals as expected return estimates (mu) fed into a
Mean-Variance Optimiser. Instead of weighting directly by signal/vol, we
solve the full MVO problem:

    maximise  mu' w - lambda * w' Cov w
    subject to  sum(w) = 1,  w >= 0

This produces a more "efficient" allocation than raw trend-following because
it accounts for cross-asset covariance, not just individual volatilities.

Key difference from TrendFollowingStrategy:
  - TrendFollowing: weight ∝ signal / vol  (per-asset heuristic)
  - TrendSignalMVO: argmax mu'w - λ w'Cov w  (joint optimisation)
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class TrendSignalMVOStrategy(AllocationStrategy):
    """
    Mean-Variance Optimisation driven by EWMA trend signals.

    Steps:
    1. Compute per-asset EWMA momentum signal (same as TrendFollowingStrategy)
    2. Use signals as expected returns (mu)
    3. Estimate covariance matrix from recent returns
    4. Solve MVO: max mu'w - risk_aversion * w'Cov*w  s.t. sum(w)=1, w>=0
    5. Fall back to equal weight if no positive signals or optimisation fails

    Parameters
    ----------
    lookback_days : int
        Window for momentum and covariance estimation (default 252 = 1 year).
    half_life_days : int
        EWMA decay half-life for momentum signals (default 60 days).
    risk_aversion : float
        Lambda in the MVO objective. Higher = more defensive. Default 1.0.
    signal_threshold : float
        Zero out signals below this magnitude before optimisation (default 0.05).
    min_volatility : float
        Floor on individual asset vol to avoid division by zero (default 0.001).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        half_life_days: int = 60,
        risk_aversion: float = 1.0,
        signal_threshold: float = 0.05,
        min_volatility: float = 0.001,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Trend-Signal MVO (λ={risk_aversion})",
        )
        self.lookback_days = lookback_days
        self.half_life_days = half_life_days
        self.risk_aversion = risk_aversion
        self.signal_threshold = signal_threshold
        self.min_volatility = min_volatility

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = self.lookback_days + 5
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            return self._equal_weight(prices)

        mu = self._compute_signals(prices)
        cov = self._compute_covariance(prices)

        # Threshold weak signals
        mu[np.abs(mu) < self.signal_threshold] = 0.0

        # If no positive signal at all, fall back to equal weight
        if (mu <= 0).all():
            logger.debug("TrendSignalMVO: no positive signals, using equal weight")
            return self._equal_weight(prices)

        weights_arr = self._optimise(mu.values, cov.values, len(prices.columns))

        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name

        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(weights_arr, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_signals(self, prices: pd.DataFrame) -> pd.Series:
        """EWMA-weighted annualised momentum signal per asset."""
        recent = prices.iloc[-self.lookback_days:]
        returns = recent.pct_change().dropna()

        decay = 0.5 ** (1.0 / self.half_life_days)
        n = len(returns)
        w = np.array([decay ** (n - i - 1) for i in range(n)])
        w /= w.sum()

        # Annualised weighted-average return
        mu = returns.values.T @ w * 252
        vols = returns.std().values.clip(min=self.min_volatility) * np.sqrt(252)
        # Sharpe-like: scale by vol so signals are comparable across assets
        return pd.Series(mu / vols, index=prices.columns)

    def _compute_covariance(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Annualised covariance matrix from recent returns."""
        recent = prices.iloc[-self.lookback_days:]
        returns = recent.pct_change().dropna()
        return returns.cov() * 252

    def _optimise(self, mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
        """
        Solve: max mu'w - lambda * w'Cov*w
               s.t. sum(w)=1, w in [0,1]
        """
        def neg_utility(w):
            return -(mu @ w - self.risk_aversion * w @ cov @ w)

        constraints = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
        bounds = [(0.0, 1.0)] * n
        w0 = np.ones(n) / n

        try:
            result = minimize(
                neg_utility,
                w0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 1000, "ftol": 1e-12},
            )
            if result.success:
                w = result.x
                w[w < 1e-6] = 0.0
                total = w.sum()
                if total > 0:
                    return w / total
            logger.warning(f"TrendSignalMVO optimisation failed: {result.message}")
        except Exception as e:
            logger.warning(f"TrendSignalMVO optimisation error: {e}")

        return np.ones(n) / n

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
