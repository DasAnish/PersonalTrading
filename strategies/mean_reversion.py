"""
Mean Reversion strategy.

Exploits short-term price reversal: assets that have underperformed recently
tend to outperform over the next rebalance period.  This is the conceptual
opposite of momentum — instead of chasing winners, we lean into losers.

Implementation
--------------
1. Compute each asset's return over a short lookback (default 20 trading days).
2. Rank assets in ascending order (worst performers first).
3. Assign inverse-rank weights so the worst-recent-performer gets the most weight.
4. Scale weights by inverse volatility to avoid vol concentration.
5. Normalise to sum to 1.  Long-only throughout.

Parameters
----------
lookback_days : int
    Short-term window for reversal signal (default 20 ≈ 1 month).
vol_lookback_days : int
    Longer window for volatility estimation (default 63 ≈ 3 months).
min_volatility : float
    Floor on asset vol to avoid division by zero (default 0.001).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MeanReversionStrategy(AllocationStrategy):
    """
    Short-term mean-reversion (contrarian) allocation strategy.

    Assets that have fallen the most over the short lookback get overweighted;
    recent outperformers get underweighted.  Weights are further scaled by
    inverse volatility to avoid concentrating in high-vol laggards.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 20,
        vol_lookback_days: int = 63,
        min_volatility: float = 0.001,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Mean Reversion ({lookback_days}d)",
        )
        self.lookback_days = lookback_days
        self.vol_lookback_days = vol_lookback_days
        self.min_volatility = min_volatility

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(self.lookback_days, self.vol_lookback_days) + 5
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < self.lookback_days + 5:
            return self._equal_weight(prices)

        # Short-term trailing returns (reversal signal)
        recent_prices = prices.iloc[-self.lookback_days:]
        trailing_returns = recent_prices.iloc[-1] / recent_prices.iloc[0] - 1

        # Rank ascending: rank 1 = worst performer (highest reversion weight)
        # scipy/pandas rank: 1 = smallest value
        ranks = trailing_returns.rank(ascending=True)  # 1 = worst performer

        # Inverse-volatility scaling
        vol_prices = prices.iloc[-self.vol_lookback_days:]
        vols = vol_prices.pct_change().dropna().std() * np.sqrt(252)
        vols = vols.clip(lower=self.min_volatility)

        # Score = rank * (1/vol)  — higher score = bigger contrarian overweight
        scores = ranks / vols
        weights = scores / scores.sum()

        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name

        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(weights.values, index=index)

    def get_strategy_lookback(self) -> int:
        return max(self.lookback_days, self.vol_lookback_days)

    # ------------------------------------------------------------------

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
