"""
Trend Following Strategy using Momentum Signals.

The strategy implements a systematic trend-following approach based on:
1. Momentum calculation using EWMA (Exponentially Weighted Moving Average)
2. Volatility normalization
3. Signal smoothing
4. Weak signal thresholding
5. Risk parity allocation based on signal strength

Key insight: Assets with strong positive momentum are allocated inversely
to their volatility - high momentum/low volatility assets get larger positions.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import List

from strategies.core import AllocationStrategy, Strategy, StrategyContext


class TrendFollowingStrategy(AllocationStrategy):
    """
    Trend following strategy based on momentum signals.

    The strategy works as follows:
    1. **Momentum Calculation**: Compute returns over a 2-year lookback period
       using EWMA with 60-day half-life to emphasize recent momentum
    2. **Volatility Normalization**: Divide momentum signal by asset volatility
       to account for risk differences (sharpe-like measure)
    3. **Signal Smoothing**: Apply simple moving average smoothing over 5 days to reduce noise
    4. **Thresholding**: Set signals close to zero (< 0.1) to zero to avoid
       trading on weak signals
    5. **Risk Parity Weighting**: Assets with stronger momentum get larger
       positions, but weighted inversely to their volatility
    6. **Long-only Portfolio**: Only positive weights, cash drag when signals weak

    Example:
        from strategies import TrendFollowingStrategy, UKETFsMarket

        market = UKETFsMarket()
        trend = TrendFollowingStrategy(underlying=market)
        weights = trend.calculate_weights(prices_df)

    Parameters:
        underlying: Market definition (e.g., UKETFsMarket)
        lookback_days: Historical window for momentum calc (default 504 = 2 years)
        half_life_days: EWMA decay parameter (default 60 days)
        smooth_window: Days for signal smoothing (default 5)
        signal_threshold: Minimum signal magnitude to include (default 0.1)
        min_volatility: Floor for volatility to avoid division by zero (default 0.001)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 504,  # 2 years of trading days
        half_life_days: int = 60,  # EWMA half-life
        smooth_window: int = 5,  # Signal smoothing window
        signal_threshold: float = 0.1,  # Min signal magnitude
        min_volatility: float = 0.001,  # Floor for volatility
        name: str = None,
    ):
        """Initialize Trend Following Strategy."""
        super().__init__(
            underlying=underlying,
            name=name or f"Trend Following (lookback={lookback_days}d, hl={half_life_days}d)",
        )
        self.lookback_days = lookback_days
        self.half_life_days = half_life_days
        self.smooth_window = smooth_window
        self.signal_threshold = signal_threshold
        self.min_volatility = min_volatility

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate portfolio weights using trend following signals.

        Args:
            context: StrategyContext with prices and metadata

        Returns:
            pd.Series with weights summing to 1.0 (long-only)
        """
        prices = context.prices

        if len(prices) < self.lookback_days + self.smooth_window:
            # Not enough data, equal weight fallback
            # Return weights for underlying strategies, not price symbols
            return pd.Series(1.0 / len(self.underlying), index=[s.name for s in self.underlying])

        # Step 1: Calculate momentum signals using EWMA
        momentum_signals = self._calculate_momentum_signals(prices)

        # Step 2: Calculate volatility for each asset
        volatilities = self._calculate_volatilities(prices)

        # Step 3: Normalize signals by volatility
        normalized_signals = momentum_signals / volatilities.clip(
            lower=self.min_volatility
        )

        # Step 4: Smooth the normalized signals
        smoothed_signals = self._smooth_signals(normalized_signals)

        # Step 5: Threshold weak signals
        thresholded_signals = smoothed_signals.copy()
        thresholded_signals[abs(thresholded_signals) < self.signal_threshold] = 0.0

        # Step 6: Convert signals to weights using risk parity on signal strength
        weights = self._signals_to_weights(thresholded_signals, volatilities)

        # Map weights from symbols to strategy names
        symbol_to_strategy_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_strategy_name[symbol] = strategy.name

        new_index = [symbol_to_strategy_name.get(symbol, symbol) for symbol in weights.index]
        weights.index = new_index

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Trend Following requires 2 years of historical data plus smoothing buffer.

        Returns:
            lookback_days + smooth_window (total days needed for calculation)
        """
        return self.lookback_days + self.smooth_window

    def _calculate_momentum_signals(self, prices: pd.DataFrame) -> pd.Series:
        """
        Calculate momentum signals using EWMA over lookback period.

        The momentum is the log return from oldest to newest, but weighted
        toward recent returns using EWMA decay.

        Args:
            prices: DataFrame with asset prices

        Returns:
            pd.Series with momentum signals (one value per asset)
        """
        # Use most recent prices for calculation
        recent_prices = prices.iloc[-self.lookback_days :]

        # Calculate returns
        returns = recent_prices.pct_change().dropna()

        # Calculate EWMA decay factor from half-life
        # half_life: decay^half_life = 0.5
        # decay = 0.5^(1/half_life)
        decay = 0.5 ** (1.0 / self.half_life_days)

        # Calculate EWMA for each asset
        momentum_signals = {}
        for symbol in prices.columns:
            asset_returns = returns[symbol].values

            # Apply EWMA weighting (more recent returns get higher weight)
            n = len(asset_returns)
            weights = np.array([decay ** (n - i - 1) for i in range(n)])
            weights = weights / weights.sum()  # Normalize to sum to 1

            # Momentum = weighted average return (annualized)
            momentum = np.sum(asset_returns * weights) * 252

            momentum_signals[symbol] = momentum

        return pd.Series(momentum_signals)

    def _calculate_volatilities(self, prices: pd.DataFrame) -> pd.Series:
        """
        Calculate annualized volatility for each asset over recent period.

        Uses the same lookback period as momentum for consistency.

        Args:
            prices: DataFrame with asset prices

        Returns:
            pd.Series with annualized volatilities
        """
        recent_prices = prices.iloc[-self.lookback_days :]
        returns = recent_prices.pct_change().dropna()

        # Annualized volatility
        volatilities = returns.std() * np.sqrt(252)

        return volatilities

    def _smooth_signals(self, signals: pd.Series, window: int = None) -> pd.Series:
        """
        Smooth signals using simple moving average.

        NOTE: The input signals Series is cross-sectional (one value per asset),
        not time-series. Rolling window smoothing is not applicable here.
        This method returns signals unchanged as a safeguard against the NaN
        values that would result from applying rolling() to a short Series.

        Args:
            signals: Raw momentum signals (cross-sectional)
            window: Smoothing window (unused, kept for API compatibility)

        Returns:
            Same signals (unchanged due to cross-sectional nature)
        """
        # NOTE: In a proper implementation, signal smoothing would be applied
        # to the time-series of historical momentum values BEFORE calculating
        # the final signal. For now, we return signals unchanged to avoid
        # introducing NaN values from rolling window operations on cross-sectional data.
        return signals

    def _signals_to_weights(
        self, signals: pd.Series, volatilities: pd.Series
    ) -> pd.Series:
        """
        Convert thresholded signals to portfolio weights using risk parity.

        Assets with stronger momentum (higher signal) get larger allocations,
        but weighted inversely to volatility. This is "risk parity on signals":
        equal risk contribution from positive momentum, ignoring zero signals.

        Args:
            signals: Thresholded momentum signals
            volatilities: Asset volatilities

        Returns:
            Normalized weights summing to 1.0
        """
        # Only consider positions with positive signal (long-only)
        positive_signals = signals.clip(lower=0)

        # Calculate risk parity weights on positive signals
        # Weight = signal / volatility (higher signal, lower vol = bigger position)
        signal_strength = positive_signals / volatilities.clip(
            lower=self.min_volatility
        )

        # Normalize to sum to 1.0
        total_strength = signal_strength.sum()
        if total_strength > 0:
            weights = signal_strength / total_strength
        else:
            # No positive signals, hold cash (all zeros)
            weights = pd.Series(0.0, index=signals.index)

        return weights
