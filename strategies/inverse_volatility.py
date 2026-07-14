"""
Inverse-Volatility (Naive Risk Parity) portfolio.

Weights each asset proportionally to the inverse of its trailing volatility —
the simplest risk-based allocation, requiring no covariance estimation or
optimization. Studied alongside ERC, minimum-variance and maximum-diversification
by Leote de Carvalho, Lu & Moulin (2012), "Demystifying Equity Risk-Based
Strategies: A Simple Alpha plus Beta Description", Financial Analysts Journal
68(3), and a robust benchmark in the "optimal versus naive diversification"
literature (DeMiguel, Garlappi & Uppal, 2009). Distinct from RiskParityStrategy,
which solves for full equal-risk-contribution using the covariance matrix.

Long-only, weights sum to 1.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class InverseVolatilityStrategy(AllocationStrategy):
    """
    Inverse-volatility weighting.

    Parameters:
        lookback_days: window for trailing volatility (default 126).
    """

    def __init__(self, underlying: List[Strategy], lookback_days: int = 126, name: str = None):
        super().__init__(underlying, name=name or "Inverse Volatility")
        self.lookback_days = lookback_days

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"InverseVolatility requires 2+ assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        symbols = list(prices.columns)
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        names = [symbol_to_name.get(s, s) for s in symbols]

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        if len(returns) < 20:
            return pd.Series(1.0 / len(symbols), index=names)

        vol = np.asarray(returns.std().values, dtype=float).copy()
        vol[vol <= 0] = np.nan
        inv = 1.0 / vol
        if np.all(np.isnan(inv)):
            return pd.Series(1.0 / len(symbols), index=names)
        inv = np.nan_to_num(inv, nan=0.0)
        weights = inv / inv.sum() if inv.sum() > 0 else np.ones(len(symbols)) / len(symbols)
        return pd.Series(weights, index=names)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
