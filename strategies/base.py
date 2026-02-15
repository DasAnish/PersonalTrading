"""
Base strategy class for portfolio optimization strategies.

This module provides the abstract base class that all strategies must inherit from.
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract base class for portfolio optimization strategies.

    All strategies must implement the calculate_weights method which takes
    historical price data and returns optimal portfolio weights.
    """

    def __init__(self, name: str = None):
        """
        Initialize strategy.

        Args:
            name: Strategy name (optional, defaults to class name)
        """
        self.name = name or self.__class__.__name__

    @abstractmethod
    def calculate_weights(self, prices: pd.DataFrame) -> pd.Series:
        """
        Calculate optimal portfolio weights based on historical prices.

        Args:
            prices: DataFrame with columns=symbols, index=dates, values=prices
                   Each column represents a different asset's price history
                   Index should be datetime/date

        Returns:
            Series with index=symbols, values=weights
            Weights must sum to 1.0
            All weights must be non-negative (long-only portfolio)

        Raises:
            ValueError: If insufficient data or invalid input
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
