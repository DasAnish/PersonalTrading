"""
Core unified strategy interface for PersonalTrading.

This module provides a single, composable interface for all strategies:
- Assets (VUSA, AAPL) - Individual instruments
- Allocations (HRP, TrendFollowing) - Portfolio weight calculations
- Overlays (VolTarget, Constraints) - Weight transformations

Key insight: Everything is a Strategy. Assets can be composed into portfolios,
and portfolios can be composed into meta-portfolios.

Example:
    # Assets as strategies
    vusa = AssetStrategy('VUSA', currency='GBP')
    ssln = AssetStrategy('SSLN', currency='GBP')

    # Portfolio of assets
    hrp = HRPStrategy(underlying=[vusa, ssln], linkage_method='ward')

    # Overlay on portfolio
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)

    # Meta-portfolio: treat strategies as assets
    meta = EqualWeightStrategy(underlying=[hrp, vol_target])

    # Run backtest
    results = await engine.run_backtest(meta, start_date, end_date)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING
import pandas as pd
import logging

if TYPE_CHECKING:
    from backtesting.engine import BacktestResults

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class DataRequirements:
    """Specification of data needs for a strategy.

    Strategies declare what data they need, and the MarketData singleton
    ensures data is fetched and available.

    Attributes:
        symbols: List of symbols to fetch (e.g., ['VUSA', 'SSLN'])
        lookback_days: Minimum days of history needed for weight calculation
        frequency: Bar size ('1 day', '1 hour', '1 min', etc.)
        currency: Quote currency (e.g., 'GBP', 'USD')
        exchange: Trading exchange (e.g., 'SMART')
        sec_type: Security type (e.g., 'STK', 'FUT', 'OPT')
        underlying_requirements: For nested strategies, requirements of underlying
    """

    symbols: List[str]
    lookback_days: int
    frequency: str = '1 day'
    currency: str = 'USD'
    exchange: str = 'SMART'
    sec_type: str = 'STK'
    underlying_requirements: Optional[List[DataRequirements]] = None

    def aggregate_with(self, other: DataRequirements) -> DataRequirements:
        """Aggregate requirements from multiple sources."""
        return DataRequirements(
            symbols=list(set(self.symbols + other.symbols)),
            lookback_days=max(self.lookback_days, other.lookback_days),
            frequency=self.frequency,  # Assume same frequency
            currency=self.currency,    # Assume same currency
            exchange=self.exchange,
            sec_type=self.sec_type,
            underlying_requirements=None
        )


@dataclass
class StrategyContext:
    """Context provided to strategies during execution.

    Replaces manual lookback window calculations. Strategies receive
    pre-sliced data without needing to know about lookback complexity.

    Attributes:
        current_date: Current rebalance date
        lookback_start: Start of lookback window (set by MarketData singleton)
        prices: DataFrame with columns=symbols, index=dates, values=prices
               Already sliced to lookback window
        portfolio_values: (Optional) Historical portfolio values for overlays
        metadata: Dictionary for extensibility
    """

    current_date: datetime
    lookback_start: datetime
    prices: pd.DataFrame
    portfolio_values: Optional[pd.Series] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Core Strategy Interface
# ============================================================================


class Strategy(ABC):
    """
    Abstract base class for all strategies (assets, allocations, overlays).

    Every strategy implements:
    1. calculate_weights() - Returns portfolio allocation
    2. get_price_timeseries() - Returns strategy's portfolio value over time
    3. get_data_requirements() - Specifies required data
    4. get_symbols() - Returns list of underlying symbols

    This single interface enables deep composability:
    - Assets (VUSA) return weight=1.0 to themselves
    - Portfolios (HRP) allocate across underlying strategies
    - Meta-portfolios (EqualWeight of portfolios) treat strategies as assets
    - Overlays (VolTarget) transform underlying weights
    """

    def __init__(self, name: Optional[str] = None):
        """Initialize strategy.

        Args:
            name: Human-readable name. Defaults to class name.
        """
        self.name = name or self.__class__.__name__
        self._cache: Dict[str, Any] = {}

    @abstractmethod
    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate portfolio weights from context.

        Args:
            context: StrategyContext with prices, dates, and metadata.
                    All necessary data is pre-sliced and provided by singleton.

        Returns:
            pd.Series with index=symbols, values=weights.
            Weights must sum to 1.0 (or <=1.0 for overlays with cash).
            All weights must be non-negative (long-only).

        Raises:
            ValueError: If unable to calculate weights (insufficient data, etc)
        """
        pass

    @abstractmethod
    def get_price_timeseries(self, context: StrategyContext) -> pd.Series:
        """
        Get price timeseries for this strategy.

        This is the key method enabling deep composability. By returning
        portfolio value timeseries, any strategy can be treated as an asset
        in a higher-level portfolio.

        For assets: Returns price of the underlying symbol.
        For portfolios: Returns weighted sum of underlying strategy values.
        For overlays: Returns transformed portfolio value.

        Args:
            context: StrategyContext with price data.

        Returns:
            pd.Series with index=dates, values=portfolio prices.
            Must cover all dates in context.prices.

        Example:
            # For VUSA asset: return context.prices['VUSA']
            # For HRP portfolio: return sum(weights * underlying_prices) at each date
            # For VolTarget overlay: return portfolio_value scaled by vol factor
        """
        pass

    @abstractmethod
    def get_data_requirements(self) -> DataRequirements:
        """
        Specify what data this strategy needs.

        MarketData singleton uses this to determine what to fetch.
        For nested strategies, must aggregate underlying requirements.

        Returns:
            DataRequirements specifying symbols, lookback, frequency, currency.

        Example:
            # Asset: return DataRequirements(['VUSA'], lookback_days=1)
            # HRP([VUSA, SSLN]): return DataRequirements(['VUSA', 'SSLN'], 252)
            # VolTarget(HRP(...)): aggregate underlying + own lookback
        """
        pass

    def get_symbols(self) -> List[str]:
        """
        Get list of underlying symbols this strategy trades.

        Default implementation delegates to data requirements.
        Can be overridden for efficiency.

        Returns:
            List of symbol strings (e.g., ['VUSA', 'SSLN', 'SGLN'])
        """
        return self.get_data_requirements().symbols

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


# ============================================================================
# Asset Strategy (Individual Instruments)
# ============================================================================


class AssetStrategy(Strategy):
    """
    Strategy representing a single asset (stock, ETF, bond, etc.).

    Assets always return 100% weight to themselves and provide their
    price timeseries directly. They can be used standalone or composed
    into higher-level portfolios.

    Example:
        vusa = AssetStrategy('VUSA', currency='GBP')
        ssln = AssetStrategy('SSLN', currency='GBP')

        # Use in portfolio
        hrp = HRPStrategy(underlying=[vusa, ssln])

        # Use in overlay
        vol_target = VolatilityTargetStrategy(underlying=vusa, target_vol=0.12)

        # Use in meta-portfolio
        portfolio = EqualWeightStrategy(underlying=[vusa, ssln])
    """

    def __init__(
        self,
        symbol: str,
        currency: str = 'USD',
        exchange: str = 'SMART',
        sec_type: str = 'STK',
        name: Optional[str] = None
    ):
        """Initialize asset strategy.

        Args:
            symbol: Ticker symbol (e.g., 'VUSA')
            currency: Quote currency (default 'USD')
            exchange: Trading exchange (default 'SMART')
            sec_type: Security type (default 'STK')
            name: Display name (defaults to symbol)
        """
        super().__init__(name=name or symbol)
        self.symbol = symbol
        self.currency = currency
        self.exchange = exchange
        self.sec_type = sec_type

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """Return 100% weight to this asset."""
        return pd.Series([1.0], index=[self.symbol])

    def get_price_timeseries(self, context: StrategyContext) -> pd.Series:
        """Return price column for this symbol."""
        if self.symbol not in context.prices.columns:
            raise ValueError(f"Symbol {self.symbol} not in price data. Available: {list(context.prices.columns)}")
        return context.prices[self.symbol]

    def get_data_requirements(self) -> DataRequirements:
        """Single symbol, minimal lookback."""
        return DataRequirements(
            symbols=[self.symbol],
            lookback_days=1,  # Only need current price
            currency=self.currency,
            exchange=self.exchange,
            sec_type=self.sec_type
        )


# ============================================================================
# Allocation Strategy (Portfolio Weight Calculation)
# ============================================================================


class AllocationStrategy(Strategy):
    """
    Strategy that calculates optimal portfolio weights.

    Allocation strategies take a collection of underlying strategies
    (which can be assets or other portfolios) and calculate weights for them.
    They implement the core algorithm (HRP, TrendFollowing, EqualWeight, etc.).

    The key innovation: underlying strategies are called get_price_timeseries()
    to get their portfolio values, enabling deep composition.

    Example:
        # Multi-asset allocation
        assets = [
            AssetStrategy('VUSA', currency='GBP'),
            AssetStrategy('SSLN', currency='GBP'),
        ]
        hrp = HRPStrategy(underlying=assets)

        # Portfolio of strategies (meta-portfolio)
        strategies = [
            TrendFollowingStrategy(underlying=assets),
            HRPStrategy(underlying=assets),
        ]
        meta = EqualWeightStrategy(underlying=strategies)
    """

    def __init__(self, underlying: List[Strategy], name: Optional[str] = None):
        """Initialize allocation strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            name: Display name
        """
        super().__init__(name=name)
        self.underlying = underlying if isinstance(underlying, list) else [underlying]

    def get_price_timeseries(self, context: StrategyContext) -> pd.Series:
        """
        Calculate portfolio value timeseries by weighting underlying strategies.

        For each historical date:
        1. Get weights from calculate_weights() at that date
        2. Get price of each underlying strategy at that date
        3. Sum: portfolio_value = sum(weight_i * price_i)

        This enables treating portfolios as assets in higher-level portfolios.

        Returns:
            pd.Series with index=dates, values=portfolio value
        """
        # Build portfolio value from weighted underlying strategies
        portfolio_value = pd.Series(0.0, index=context.prices.index)

        # For each underlying strategy, get its prices and weight them
        for strategy in self.underlying:
            try:
                strategy_prices = strategy.get_price_timeseries(context)

                # Get weight for this strategy at current date
                # Use last calculated weights for all dates (lazy approach)
                weights = self.calculate_weights(context)

                if strategy.name in weights.index:
                    weight = weights[strategy.name]
                    portfolio_value += weight * strategy_prices
                else:
                    # If strategy not in weights, weight is zero
                    pass

            except Exception as e:
                logger.warning(f"Could not get prices for {strategy.name}: {e}")

        return portfolio_value

    def get_data_requirements(self) -> DataRequirements:
        """Aggregate requirements from all underlying strategies."""
        if not self.underlying:
            return DataRequirements(
                symbols=[],
                lookback_days=0
            )

        # Start with first underlying
        aggregated = self.underlying[0].get_data_requirements()

        # Aggregate with remaining
        for strategy in self.underlying[1:]:
            req = strategy.get_data_requirements()
            aggregated = aggregated.aggregate_with(req)

        # Add this strategy's own lookback requirement
        strategy_lookback = self.get_strategy_lookback()
        aggregated.lookback_days = max(aggregated.lookback_days, strategy_lookback)

        return aggregated

    @abstractmethod
    def get_strategy_lookback(self) -> int:
        """
        Return minimum days of history this strategy needs.

        Should be implemented by subclasses:
        - HRPStrategy: 252 (for correlation calculation)
        - EqualWeightStrategy: 0 (no history needed)
        - TrendFollowingStrategy: 504 + smooth_window

        Returns:
            Number of lookback days required
        """
        pass


# ============================================================================
# Overlay Strategy (Weight Transformation)
# ============================================================================


class OverlayStrategy(Strategy):
    """
    Strategy that transforms weights from an underlying strategy.

    Overlay strategies wrap any other strategy and modify its weights
    at each rebalance to enforce constraints, targets, or other rules.

    Common overlays:
    - VolatilityTargetStrategy: Scale weights to achieve target volatility
    - ConstraintStrategy: Apply min/max weight limits
    - LeverageStrategy: Apply gross leverage limits
    - CashTargetStrategy: Manage cash allocation

    Key feature: Overlays can be stacked. Example:
        base = HRPStrategy(underlying=assets)
        vol_target = VolatilityTargetStrategy(underlying=base, target_vol=0.12)
        constrained = ConstraintStrategy(underlying=vol_target, min_weight=0.05)

    Overlays can wrap ANY strategy type:
        # On asset
        VolTarget(AssetStrategy('VUSA'), target_vol=0.12)

        # On portfolio
        VolTarget(HRPStrategy(...), target_vol=0.12)

        # On meta-portfolio
        VolTarget(EqualWeightStrategy([strategy1, strategy2]), target_vol=0.12)
    """

    def __init__(self, underlying: Strategy, name: Optional[str] = None):
        """Initialize overlay strategy.

        Args:
            underlying: Strategy to overlay (asset, allocation, or another overlay)
            name: Display name
        """
        super().__init__(name=name)
        self.underlying = underlying

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """Get underlying weights and transform them."""
        base_weights = self.underlying.calculate_weights(context)
        return self.transform_weights(base_weights, context)

    @abstractmethod
    def transform_weights(self, weights: pd.Series, context: StrategyContext) -> pd.Series:
        """
        Transform weights from underlying strategy.

        Args:
            weights: Original weights from underlying strategy (sum to 1.0)
            context: StrategyContext with prices and metadata

        Returns:
            Transformed weights. Can sum to <1.0 if cash is allowed.

        Example:
            # Vol targeting: scale weights by (target_vol / realized_vol)
            scale = context.metadata.get('vol_scale', 1.0)
            return weights * scale

            # Constraints: clip weights to [min_weight, max_weight]
            return weights.clip(self.min_weight, self.max_weight)
        """
        pass

    def get_price_timeseries(self, context: StrategyContext) -> pd.Series:
        """Calculate portfolio value with transformed weights."""
        # Get underlying price timeseries
        underlying_prices = self.underlying.get_price_timeseries(context)

        # Get transformed weights
        weights = self.calculate_weights(context)

        # For single-asset overlays, scale by weight (leverage/deleveraging)
        if len(weights) == 1 and weights.iloc[0] != 1.0:
            return underlying_prices * weights.iloc[0]

        # For portfolios, weights are already incorporated in underlying_prices
        # (calculated via weighted sum in AllocationStrategy.get_price_timeseries)
        # Transform applies via new weight calculation
        return underlying_prices

    def get_data_requirements(self) -> DataRequirements:
        """Delegate to underlying, potentially adding lookback for overlay logic."""
        base_req = self.underlying.get_data_requirements()
        overlay_lookback = self.get_overlay_lookback()

        if overlay_lookback > base_req.lookback_days:
            base_req.lookback_days = overlay_lookback

        return base_req

    @abstractmethod
    def get_overlay_lookback(self) -> int:
        """
        Return minimum days of history this overlay needs.

        Should be implemented by subclasses:
        - VolatilityTargetStrategy: 252 (for vol calculation)
        - ConstraintStrategy: 0 (no history needed)
        - LeverageStrategy: 0 (no history needed)

        Returns:
            Number of lookback days required
        """
        pass
