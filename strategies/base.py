"""
Base strategy classes for portfolio optimization strategies.

This module provides:
- BaseStrategy: Legacy interface for weight calculation
- ExecutableStrategy: New composable interface with run() method
- MarketStrategy: Defines asset universe (symbols, currency, exchange)
- AllocationStrategy: Calculates portfolio weights
- OverlayStrategy: Applies transformations to weights (overlays)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
from datetime import datetime
import pandas as pd

from strategies.models import Instrument, MarketDefinition, OverlayContext

if TYPE_CHECKING:
    from backtesting.engine import BacktestEngine, BacktestResults
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


# ============================================================================
# NEW COMPOSABLE STRATEGY SYSTEM
# ============================================================================
# These classes enable strategy composition: VolTarget(HRP(UKETFs()))
# The old BaseStrategy is kept for backward compatibility.
# ============================================================================


class ExecutableStrategy(ABC):
    """
    Base class for all composable strategies.

    All strategies must implement run() which executes the strategy and
    returns results with portfolio value timeseries.
    """

    def __init__(self, name: str = None):
        """Initialize strategy."""
        self.name = name or self.__class__.__name__
        self._results_cache: Optional['BacktestResults'] = None

    @abstractmethod
    async def run(self, engine: 'BacktestEngine', start_date: datetime, end_date: datetime) -> 'BacktestResults':
        """
        Execute strategy over time period.

        Args:
            engine: BacktestEngine to run simulation
            start_date: Start date for backtest
            end_date: End date for backtest

        Returns:
            BacktestResults with portfolio values, weights, transactions, and metrics
        """
        pass

    @abstractmethod
    def get_market_definition(self) -> MarketDefinition:
        """
        Get market definition for this strategy.

        For MarketStrategy: returns the defined market
        For AllocationStrategy/OverlayStrategy: delegates to underlying
        """
        pass

    def get_results(self) -> Optional['BacktestResults']:
        """Get cached results from last run."""
        return self._results_cache

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class MarketStrategy(ExecutableStrategy):
    """
    Strategy that defines an asset universe.

    Examples:
    - UKETFsMarket: VUSA, SSLN, SGLN, IWRD (GBP)
    - USEquitiesMarket: AAPL, MSFT, GOOGL (USD)

    MarketStrategy cannot be run directly. It must be wrapped by an
    AllocationStrategy (HRP, EqualWeight, etc.).
    """

    def __init__(self, market_def: MarketDefinition, name: str = None):
        """Initialize with market definition."""
        super().__init__(name=name)
        self.market_def = market_def

    def get_market_definition(self) -> MarketDefinition:
        """Return the market definition."""
        return self.market_def

    async def run(self, engine: 'BacktestEngine', start_date: datetime, end_date: datetime) -> 'BacktestResults':
        """
        MarketStrategy cannot be run directly.

        Raises:
            NotImplementedError: Always. Wrap in AllocationStrategy first.
        """
        raise NotImplementedError(
            f"MarketStrategy '{self.name}' cannot be run directly. "
            f"Wrap it in an AllocationStrategy (e.g., HRPStrategy, EqualWeightStrategy)"
        )


class AllocationStrategy(ExecutableStrategy):
    """
    Strategy that calculates portfolio weights.

    Examples:
    - HRPStrategy: Hierarchical Risk Parity
    - EqualWeightStrategy: 1/N allocation

    AllocationStrategy wraps a MarketStrategy or another AllocationStrategy
    and implements weight calculation logic.
    """

    def __init__(self, underlying: ExecutableStrategy, name: str = None):
        """Initialize with underlying strategy."""
        super().__init__(name=name)
        self.underlying = underlying

    @abstractmethod
    def calculate_weights(self, prices: pd.DataFrame) -> pd.Series:
        """
        Calculate portfolio weights from price history.

        Args:
            prices: DataFrame with columns=symbols, index=dates, values=prices

        Returns:
            Series with index=symbols, values=weights (sum to 1.0)
        """
        pass

    def get_market_definition(self) -> MarketDefinition:
        """Delegate to underlying strategy."""
        return self.underlying.get_market_definition()

    async def run(self, engine: 'BacktestEngine', start_date: datetime, end_date: datetime) -> 'BacktestResults':
        """
        Execute allocation strategy.

        This is a placeholder for async execution. Currently, allocation strategies
        are typically used through the traditional approach:

        Example (Current approach):
            strategy = HRPStrategy(underlying=market)
            results = engine.run_backtest(strategy, historical_data, start_date, end_date)

        Future async approach (when data fetching is integrated):
            strategy = HRPStrategy(underlying=market)
            results = await strategy.run(engine, start_date, end_date)

        Raises:
            NotImplementedError: This is a placeholder for future enhancement.
        """
        raise NotImplementedError(
            "Async execution of AllocationStrategy is not yet implemented. "
            "Use the traditional approach: engine.run_backtest(strategy, data, start, end)"
        )


class OverlayStrategy(ExecutableStrategy):
    """
    Strategy that applies transformations to underlying strategy weights.

    Examples:
    - VolatilityTargetOverlay: Scale weights to achieve target volatility
    - ConstraintOverlay: Apply min/max weight constraints
    - LeverageOverlay: Apply leverage limits

    OverlayStrategy wraps any ExecutableStrategy and modifies its weights
    at each rebalance. It needs access to the underlying strategy's results
    to calculate transformations (e.g., realized volatility).
    """

    def __init__(self, underlying: ExecutableStrategy, name: str = None):
        """Initialize with underlying strategy."""
        super().__init__(name=name)
        self.underlying = underlying

    @abstractmethod
    def transform_weights(self, weights: pd.Series, context: OverlayContext) -> pd.Series:
        """
        Transform weights from underlying strategy.

        Args:
            weights: Original weights from underlying strategy
            context: OverlayContext with prices, portfolio values, dates

        Returns:
            Transformed weights (must sum to 1.0)
        """
        pass

    def get_market_definition(self) -> MarketDefinition:
        """Delegate to underlying strategy."""
        return self.underlying.get_market_definition()

    async def run(self, engine: 'BacktestEngine', start_date: datetime, end_date: datetime, historical_data: Optional['pd.DataFrame'] = None) -> 'BacktestResults':
        """
        Execute overlay strategy with transformations applied.

        This method:
        1. Runs the underlying strategy to get base allocation
        2. Runs backtest with overlay transformations applied at each rebalance
        3. Transforms underlying weights using this overlay's logic

        Args:
            engine: BacktestEngine instance
            start_date: Backtest start date
            end_date: Backtest end date
            historical_data: Historical price data (required for overlay execution)

        Returns:
            BacktestResults with overlay-transformed portfolio history

        Raises:
            ValueError: If historical_data is not provided
        """
        if historical_data is None:
            raise ValueError(
                "historical_data must be provided to run OverlayStrategy. "
                "Pass DataFrame with columns=symbols, index=dates, values=prices"
            )

        # Run underlying strategy first (with same data)
        # Need to get underlying results to use in overlay context
        underlying_results = engine.run_backtest(
            strategy=self.underlying,
            historical_data=historical_data,
            start_date=start_date,
            end_date=end_date
        )

        # Run backtest with overlay transformations
        results = engine.run_backtest_with_overlay(
            underlying_strategy=self.underlying,
            overlay_strategy=self,
            historical_data=historical_data,
            start_date=start_date,
            end_date=end_date,
            underlying_results=underlying_results
        )

        # Cache results
        self._results_cache = results

        return results
