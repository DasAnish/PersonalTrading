"""
Equal weight portfolio allocation strategy.

Allocates equal weight to all underlying strategies or assets.
Simple baseline benchmark for more sophisticated strategies.

Example:
    # Equal weight across individual assets
    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    strategy = EqualWeightStrategy(underlying=assets)

    # Equal weight portfolio of strategies (meta-portfolio)
    strategies = [
        TrendFollowingStrategy(underlying=assets),
        HRPStrategy(underlying=assets),
    ]
    meta = EqualWeightStrategy(underlying=strategies)
"""

import pandas as pd
from typing import List

from strategies.core import AllocationStrategy, Strategy, StrategyContext


class EqualWeightStrategy(AllocationStrategy):
    """
    Equal weight portfolio allocation strategy.

    Allocates 1/N weight to each of N underlying strategies (or assets),
    regardless of historical performance, volatility, or correlations.

    Serves as a simple baseline benchmark for more sophisticated strategies.

    Example:
        assets = [AssetStrategy('VUSA'), AssetStrategy('SSLN')]
        eq = EqualWeightStrategy(underlying=assets)
        weights = eq.calculate_weights(context)  # Returns [0.5, 0.5]
    """

    def __init__(self, underlying: List[Strategy], name: str = None):
        """
        Initialize equal weight strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios) to allocate across
            name: Display name (default: "Equal Weight")
        """
        super().__init__(underlying, name=name or "Equal Weight")

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate equal weights for all underlying strategies.

        Args:
            context: StrategyContext with prices and metadata

        Returns:
            pd.Series with index=strategy names, values=equal weights (1/N each)

        Raises:
            ValueError: If no underlying strategies
        """
        if not self.underlying or len(self.underlying) == 0:
            raise ValueError("Cannot calculate weights: no underlying strategies")

        n_strategies = len(self.underlying)
        equal_weight = 1.0 / n_strategies

        # Create weights series with strategy names as index
        weights = pd.Series(
            [equal_weight] * n_strategies,
            index=[s.name for s in self.underlying]
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        EqualWeight requires no historical data for calculation.

        Returns:
            0 (no lookback needed)
        """
        return 0
