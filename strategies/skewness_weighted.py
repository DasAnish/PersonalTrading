"""
Skewness-Weighted allocation strategy.

Starts from equal weights then tilts allocations based on return skewness.
Assets with more negative skewness (left-tail / crash risk) receive lower
weights; assets with positive or neutral skewness receive higher weights.

Intuition: skewness is a proxy for tail risk.  A negatively-skewed asset
can have the same mean and variance as a positively-skewed one, yet carry
much higher probability of large drawdowns.  This strategy penalises that.

Implementation
--------------
1. Compute return skewness for each asset over the lookback window.
2. Shift skewness values up so the minimum = 0 (no negative scores).
3. If all assets have identical skewness, fall back to equal weight.
4. Normalise shifted scores to sum to 1.
5. Blend with equal weight via `skew_tilt` parameter to control aggressiveness.

Parameters
----------
lookback_days : int
    Window for skewness estimation (default 252 ≈ 1 year).
skew_tilt : float
    Weight given to the skewness-based allocation vs equal weight.
    0.0 = pure equal weight, 1.0 = pure skewness-weighted. Default 0.5.
min_weight : float
    Floor weight per asset after blending (default 0.05 = 5%).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.stats import skew as scipy_skew

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class SkewnessWeightedStrategy(AllocationStrategy):
    """
    Allocation strategy that tilts away from negatively-skewed assets.

    A 50/50 blend (default) between equal weight and a pure skewness-score
    allocation provides moderate defensive tilt without full concentration.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        skew_tilt: float = 0.5,
        min_weight: float = 0.05,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Skewness-Weighted (tilt={skew_tilt})",
        )
        self.lookback_days = lookback_days
        self.skew_tilt = float(np.clip(skew_tilt, 0.0, 1.0))
        self.min_weight = float(min_weight)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if len(prices) < self.lookback_days + 5:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            return self._equal_weight(prices)

        recent = prices.iloc[-self.lookback_days:]
        returns = recent.pct_change().dropna()

        # Compute skewness per asset
        skewness = returns.apply(lambda col: scipy_skew(col.dropna()))

        logger.debug(f"SkewnessWeighted skewness: {dict(skewness.round(3))}")

        # Shift so minimum skewness = 0, then add small epsilon so no asset = 0
        shifted = skewness - skewness.min() + 1e-6
        skew_weights = shifted / shifted.sum()

        # Blend with equal weight
        n = len(prices.columns)
        eq_weights = pd.Series(1.0 / n, index=skew_weights.index)
        blended = (1.0 - self.skew_tilt) * eq_weights + self.skew_tilt * skew_weights

        # Apply floor then renormalise
        blended = blended.clip(lower=self.min_weight)
        blended /= blended.sum()

        # Map symbols → strategy names
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name

        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(blended.values, index=index)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
