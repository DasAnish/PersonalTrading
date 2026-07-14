"""
CVaR Risk Parity (equal component-CVaR contribution) portfolio.

Allocates so each asset contributes equally to portfolio Conditional
Value-at-Risk, using the historical decomposition of CVaR into per-asset
component contributions (Boudt, Peterson & Croux, 2008, "Estimation and
Decomposition of Downside Risk for Portfolios with Non-Normal Returns", Journal
of Risk 11(2)). Component CVaR_i = -w_i * E[r_i | portfolio return in its worst
(1-alpha) tail]; the objective equalizes these across assets.

Distinct from MinimumCVaRStrategy (which minimizes total CVaR), from
RiskParityStrategy (equalizes volatility contributions) and from
DownsideRiskParityStrategy (semicovariance-based). Long-only, weights sum to 1.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class CVaRRiskParityStrategy(AllocationStrategy):
    """
    Equal component-CVaR contribution portfolio.

    Parameters:
        lookback_days: window for the scenario matrix (default 252).
        alpha: CVaR confidence level (default 0.95 -> worst 5% of days).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        alpha: float = 0.95,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "CVaR Risk Parity")
        self.lookback_days = lookback_days
        self.alpha = alpha

    def _component_cvar(self, w: np.ndarray, R: np.ndarray) -> np.ndarray:
        port = R @ w
        T = len(port)
        k = max(1, int(round((1.0 - self.alpha) * T)))
        tail_idx = np.argsort(port)[:k]  # worst k days
        # Component CVaR_i = -w_i * mean over tail of r_i (losses positive).
        comp = -w * R[tail_idx, :].mean(axis=0)
        return comp

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"CVaRRiskParity requires 2+ assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Insufficient data for CVaRRiskParity (need 30+).")

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        R = returns.values
        n = R.shape[1]
        target = np.ones(n) / n

        def rc_error(w):
            w = np.maximum(w, 1e-10)
            comp = self._component_cvar(w, R)
            total = comp.sum()
            if total <= 0:
                return 1e10
            return np.sum((comp / total - target) ** 2)

        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = tuple((1e-6, 1.0) for _ in range(n))
        # Start from inverse-downside-vol.
        downside = np.sqrt((np.minimum(R, 0.0) ** 2).mean(axis=0))
        downside[downside == 0] = 1e-10
        w0 = (1.0 / downside)
        w0 = w0 / w0.sum()

        try:
            result = minimize(
                rc_error, w0, method="SLSQP", bounds=bounds,
                constraints=constraints, options={"maxiter": 1000, "ftol": 1e-12},
            )
            if result.success and result.fun < 1e-4:
                weights = result.x
                weights[weights < 1e-6] = 0
                weights = weights / weights.sum() if weights.sum() > 0 else w0
            else:
                logger.warning(
                    f"CVaRRiskParity did not fully converge (err={result.fun:.2e}). "
                    "Using best/inverse-downside-vol weights."
                )
                weights = result.x if result.success else w0
                weights = np.clip(weights, 0, None)
                weights = weights / weights.sum() if weights.sum() > 0 else w0
        except Exception as e:
            logger.warning(f"CVaRRiskParity failed: {e}. Inverse-downside-vol.")
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
