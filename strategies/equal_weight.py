"""
Equal weight portfolio strategy.

Simple benchmark strategy that allocates equal weight to all assets.
"""

import pandas as pd
from .base import BaseStrategy


class EqualWeightStrategy(BaseStrategy):
    """
    Equal weight portfolio strategy.

    Allocates 1/N weight to each of N assets, regardless of their
    historical performance, volatility, or correlations.

    This serves as a simple baseline benchmark for more sophisticated
    strategies like HRP.
    """

    def __init__(self):
        """Initialize equal weight strategy."""
        super().__init__(name="Equal Weight")

    def calculate_weights(self, prices: pd.DataFrame) -> pd.Series:
        """
        Calculate equal weights for all assets.

        Args:
            prices: DataFrame with columns=symbols, index=dates, values=prices

        Returns:
            Series with index=symbols, values=weights (all equal to 1/N)

        Raises:
            ValueError: If prices DataFrame is empty
        """
        if prices.empty or len(prices.columns) == 0:
            raise ValueError("Cannot calculate weights for empty price data")

        n_assets = len(prices.columns)
        equal_weight = 1.0 / n_assets

        weights = pd.Series(equal_weight, index=prices.columns)

        return weights
