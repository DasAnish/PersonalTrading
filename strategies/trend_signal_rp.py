"""
Trend-Signal Risk Parity strategy.

A hybrid of trend following and risk parity.  Instead of targeting equal
marginal risk contributions (standard risk parity), this strategy uses
EWMA momentum signals to set *proportional* risk budgets:

    target_risk_contribution_i ∝ max(signal_i, 0)

Assets with stronger positive trend signals get a larger share of the total
portfolio risk.  Assets with zero or negative signals receive a minimal risk
budget (floor), preventing full exclusion while still underweighting them.

This combines:
- **Trend Following**: directional tilt toward trending assets
- **Risk Parity**: cross-asset correlation awareness in weight calculation
- **Risk Budgeting**: principled allocation rather than ad-hoc signal→weight

Parameters
----------
lookback_days : int
    Window for momentum and covariance estimation (default 252 = 1 year).
half_life_days : int
    EWMA half-life for momentum signals (default 60 days).
min_risk_budget : float
    Floor risk budget for any asset, as a fraction of equal budget (1/N).
    E.g. 0.1 means no asset gets less than 10% of the equal-budget share.
    Default 0.1.
signal_threshold : float
    Threshold below which signals are zeroed (default 0.05).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class TrendSignalRPStrategy(AllocationStrategy):
    """
    Risk parity with momentum-signal-proportional risk budgets.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        half_life_days: int = 60,
        min_risk_budget: float = 0.1,
        signal_threshold: float = 0.05,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or "Trend-Signal Risk Parity",
        )
        self.lookback_days = lookback_days
        self.half_life_days = half_life_days
        self.min_risk_budget = min_risk_budget
        self.signal_threshold = signal_threshold

    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if len(prices) < self.lookback_days + 5:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            return self._equal_weight(prices)

        # Compute EWMA signals
        signals = self._compute_signals(prices)
        signals[np.abs(signals) < self.signal_threshold] = 0.0

        # Build risk budgets proportional to positive signals
        n = len(prices.columns)
        equal_budget = 1.0 / n
        floor = self.min_risk_budget * equal_budget

        positive_signals = signals.clip(lower=0.0)
        total_signal = positive_signals.sum()

        if total_signal > 0:
            raw_budgets = positive_signals / total_signal
        else:
            raw_budgets = pd.Series(equal_budget, index=signals.index)

        # Apply floor and renormalise
        budgets = raw_budgets.clip(lower=floor)
        budgets /= budgets.sum()

        logger.debug(f"TrendSignalRP budgets: {dict(budgets.round(4))}")

        # Solve risk-budgeting problem: w s.t. w_i*(Cov*w)_i = budget_i * w'*Cov*w
        cov = self._compute_covariance(prices)
        weights_arr = self._risk_budget_solve(budgets.values, cov.values, n)

        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name

        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(weights_arr, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------

    def _compute_signals(self, prices: pd.DataFrame) -> pd.Series:
        recent = prices.iloc[-self.lookback_days:]
        returns = recent.pct_change().dropna()

        decay = 0.5 ** (1.0 / self.half_life_days)
        n = len(returns)
        w = np.array([decay ** (n - i - 1) for i in range(n)])
        w /= w.sum()

        mu = returns.values.T @ w * 252
        vols = returns.std().values.clip(min=0.001) * np.sqrt(252)
        return pd.Series(mu / vols, index=prices.columns)

    def _compute_covariance(self, prices: pd.DataFrame) -> pd.DataFrame:
        recent = prices.iloc[-self.lookback_days:]
        returns = recent.pct_change().dropna()
        return returns.cov() * 252

    def _risk_budget_solve(
        self, budgets: np.ndarray, cov: np.ndarray, n: int
    ) -> np.ndarray:
        """
        Solve risk-budgeting: min sum_i (w_i*(Cov*w)_i / portfolio_var - budget_i)^2
        s.t. sum(w)=1, w >= 0
        """
        def objective(w):
            port_var = w @ cov @ w
            if port_var < 1e-12:
                return 1e10
            rc = w * (cov @ w)
            rc_frac = rc / port_var
            return np.sum((rc_frac - budgets) ** 2)

        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        bounds = [(0.0, 1.0)] * n
        w0 = np.ones(n) / n

        best_w = w0.copy()
        best_val = float('inf')

        # Multiple restarts for robustness
        for seed in [42, 7, 13]:
            np.random.seed(seed)
            w_init = np.random.dirichlet(np.ones(n))
            try:
                result = minimize(
                    objective,
                    w_init,
                    method='SLSQP',
                    bounds=bounds,
                    constraints=constraints,
                    options={'maxiter': 1000, 'ftol': 1e-14}
                )
                if result.success and result.fun < best_val:
                    best_val = result.fun
                    best_w = result.x
            except Exception:
                pass

        best_w[best_w < 1e-6] = 0.0
        total = best_w.sum()
        return best_w / total if total > 0 else np.ones(n) / n

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
