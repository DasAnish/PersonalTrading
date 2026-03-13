"""
Overlay strategies for risk management and portfolio transformations.

Overlay strategies apply transformations to weights from underlying allocation
strategies. They enable powerful compositions like:
- VolatilityTargetOverlay(HRPStrategy(UKETFsMarket()))
- ConstraintOverlay(EqualWeightStrategy(USEquitiesMarket()))

All overlays wrap an ExecutableStrategy and modify its weights at each rebalance.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import TYPE_CHECKING

from strategies.core import OverlayStrategy, Strategy, StrategyContext

if TYPE_CHECKING:
    from backtesting.engine import BacktestEngine


class VarianceTargetStrategy(OverlayStrategy):
    """
    Scale portfolio weights to achieve target variance level.

    Similar to VolatilityTargetOverlay but targets variance instead of volatility.
    Since variance scales linearly with time (vs volatility which scales with sqrt(time)),
    the annualization is different: annualized_variance = daily_variance * 252

    This overlay runs the underlying strategy first to get its portfolio value
    timeseries, then calculates realized variance. At each rebalance, it
    scales the allocation weights to achieve the target variance level.

    Example:
        market = UKETFsMarket()
        hrp = HRPStrategy(underlying=market)
        var_target = VarianceTargetOverlay(underlying=hrp, target_variance=0.02)
        results = await var_target.run(engine, start_date, end_date)

    The scaling works as follows:
    1. Calculate realized variance from underlying portfolio returns
    2. Calculate scale = target_variance / realized_variance
    3. Scale weights: adjusted_weights = original_weights * scale
    4. Remaining allocation goes to cash (cash weight = 1 - sum(scaled_weights))
    5. Cap scaling to max 1.0 (no leverage)

    Variance is useful because:
    - It's additive over time (easier for portfolio optimization)
    - Some prefer it for risk budgeting
    - Smaller values than volatility for the same portfolio
    """

    def __init__(
        self,
        underlying: Strategy,
        target_variance: float = 0.02,
        lookback_days: int = 252,
    ):
        """
        Initialize variance target overlay.

        Args:
            underlying: Strategy to apply overlay to
            target_variance: Target annualized variance (default 0.02 = 2%)
                           Note: variance is vol^2, so 0.02 ≈ 14% volatility
            lookback_days: Lookback window for variance calculation (default 252 trading days)
        """
        super().__init__(
            underlying, name=f"Variance Target ({target_variance*100:.2f}%)"
        )
        self.target_variance = target_variance
        self.lookback_days = lookback_days

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        """
        Scale weights to achieve target variance.

        Args:
            weights: Original weights from underlying strategy
            context: OverlayContext with portfolio values and prices

        Returns:
            Scaled weights (sum may be < 1.0, with cash making up the difference)
        """
        portfolio_values = context.underlying_portfolio_values

        # Need at least 2 data points to calculate returns
        if len(portfolio_values) < 2:
            return weights

        # Filter to dates on or before current_date (important for overlay backtest)
        values_up_to_date = portfolio_values[portfolio_values.index <= context.current_date]

        if len(values_up_to_date) < 2:
            return weights

        # Get lookback window (at most all available data up to current date)
        lookback_start = max(0, len(values_up_to_date) - self.lookback_days)
        recent_values = values_up_to_date.iloc[lookback_start:]

        if len(recent_values) < 30:
            # Insufficient data for reliable variance estimate
            return weights

        # Calculate returns from portfolio values
        returns = recent_values.pct_change().dropna()

        if len(returns) < 2:
            return weights

        # Calculate realized variance (annualized)
        # Note: variance scales linearly with time, so multiply by 252 (not sqrt(252))
        realized_variance = returns.var() * 252

        # Avoid division by zero
        if realized_variance < 1e-8:
            # No variance, return original weights
            return weights

        # Calculate scaling factor: target_variance / realized_variance
        scale = self.target_variance / realized_variance

        # Cap scaling to max 1.0 (no leverage)
        # This allows scaling down to cash but not leveraging up
        scale = min(scale, 1.0)
        scale = max(scale, 0.0)

        # Scale weights
        scaled_weights = weights * scale

        return scaled_weights


class VolatilityTargetStrategy(OverlayStrategy):
    """
    Scale portfolio weights to achieve target volatility level.

    This overlay runs the underlying strategy first to get its portfolio value
    timeseries, then calculates realized volatility. At each rebalance, it
    scales the allocation weights to achieve the target volatility level.

    Example:
        market = UKETFsMarket()
        hrp = HRPStrategy(underlying=market)
        vol_target = VolatilityTargetOverlay(underlying=hrp, target_vol=0.12)
        results = await vol_target.run(engine, start_date, end_date)

    The scaling works as follows:
    1. Calculate realized vol from underlying portfolio returns
    2. Calculate scale = target_vol / realized_vol
    3. Scale weights: adjusted_weights = original_weights * scale
    4. Remaining allocation goes to cash (cash weight = 1 - sum(scaled_weights))
    5. Cap scaling to max 1.0 (no leverage)

    This allows the overlay to:
    - Reduce exposure when realized vol exceeds target (cash drag)
    - Increase exposure when realized vol below target
    - Never use leverage (scale capped at 1.0)
    """

    def __init__(
        self,
        underlying: Strategy,
        target_vol: float = 0.15,
        lookback_days: int = 252,
    ):
        """
        Initialize volatility target overlay.

        Args:
            underlying: Strategy to apply overlay to
            target_vol: Target annualized volatility (default 0.15 = 15%)
            lookback_days: Lookback window for volatility calculation (default 252 trading days)
        """
        super().__init__(
            underlying, name=f"Vol Target ({target_vol*100:.0f}%)"
        )
        self.target_vol = target_vol
        self.lookback_days = lookback_days

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        """
        Scale weights to achieve target volatility.

        Args:
            weights: Original weights from underlying strategy
            context: OverlayContext with portfolio values and prices

        Returns:
            Scaled weights (sum may be < 1.0, with cash making up the difference)
        """
        portfolio_values = context.underlying_portfolio_values

        # Need at least 2 data points to calculate returns
        if len(portfolio_values) < 2:
            return weights

        # Filter to dates on or before current_date (important for overlay backtest)
        values_up_to_date = portfolio_values[portfolio_values.index <= context.current_date]

        if len(values_up_to_date) < 2:
            return weights

        # Get lookback window (at most all available data up to current date)
        lookback_start = max(0, len(values_up_to_date) - self.lookback_days)
        recent_values = values_up_to_date.iloc[lookback_start:]

        if len(recent_values) < 30:
            # Insufficient data for reliable volatility estimate
            return weights

        # Calculate returns from portfolio values
        returns = recent_values.pct_change().dropna()

        if len(returns) < 2:
            return weights

        # Calculate realized volatility (annualized)
        realized_vol = returns.std() * np.sqrt(252)

        # Avoid division by zero
        if realized_vol < 1e-8:
            # No volatility, return original weights
            return weights

        # Calculate scaling factor: target_vol / realized_vol
        scale = self.target_vol / realized_vol

        # Cap scaling to max 1.0 (no leverage)
        # This allows scaling down to cash but not leveraging up
        scale = min(scale, 1.0)
        scale = max(scale, 0.0)

        # Scale weights
        scaled_weights = weights * scale

        return scaled_weights


class ConstraintStrategy(OverlayStrategy):
    """
    Apply minimum and maximum weight constraints to portfolio.

    This overlay enforces position size limits on the underlying allocation:
    - No position smaller than min_weight (or remove entirely)
    - No position larger than max_weight (redistribute excess to others)

    Example:
        hrp = HRPStrategy(underlying=market)
        constrained = ConstraintOverlay(
            underlying=hrp,
            min_weight=0.05,  # Minimum 5% per position
            max_weight=0.40   # Maximum 40% per position
        )

    The constraint algorithm:
    1. Remove any weights below min_weight
    2. Cap any weights above max_weight
    3. Redistribute removed/capped weight proportionally to remaining assets
    4. Repeat until convergence
    """

    def __init__(
        self,
        underlying: Strategy,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
    ):
        """
        Initialize constraint overlay.

        Args:
            underlying: Strategy to apply constraints to
            min_weight: Minimum weight for any position (default 0.0)
            max_weight: Maximum weight for any position (default 1.0)
        """
        if not 0 <= min_weight <= max_weight <= 1.0:
            raise ValueError(
                f"Invalid weights: min={min_weight}, max={max_weight}. "
                "Must satisfy: 0 <= min <= max <= 1.0"
            )

        super().__init__(underlying, name=f"Constraints ({min_weight:.0%}-{max_weight:.0%})")
        self.min_weight = min_weight
        self.max_weight = max_weight

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        """
        Apply weight constraints.

        Args:
            weights: Original weights from underlying strategy
            context: OverlayContext (unused for constraints)

        Returns:
            Constrained weights that satisfy min/max bounds
        """
        constrained = weights.copy()

        # Iterate up to 10 times to handle redistribution
        for _ in range(10):
            # Identify violations
            below_min = constrained < self.min_weight
            above_max = constrained > self.max_weight

            if not (below_min.any() or above_max.any()):
                # No violations, converged
                break

            # Step 1: Remove weights below minimum
            removed_weight = constrained[below_min].sum()
            constrained[below_min] = 0.0

            # Step 2: Cap weights above maximum (collect excess)
            excess_weight = (constrained[above_max] - self.max_weight).sum()
            constrained[above_max] = self.max_weight
            removed_weight += excess_weight

            # Step 3: Redistribute removed/excess weight to positions that can accept it
            # Only redistribute to positions that:
            # - Are currently above 0
            # - Haven't hit their maximum after capping
            active = (constrained > 0) & (constrained < self.max_weight)

            if active.any() and removed_weight > 1e-10:
                # Calculate how much each active position can accept
                active_capacity = self.max_weight - constrained[active]
                total_capacity = active_capacity.sum()

                if total_capacity > 0:
                    # Distribute removed weight proportionally to available capacity
                    redistribution = removed_weight * (active_capacity / total_capacity)
                    # Don't exceed max_weight for any position
                    redistribution = redistribution.clip(upper=active_capacity)
                    constrained[active] += redistribution

        # Final normalization to ensure sum = 1.0 (handle rounding errors)
        total = constrained.sum()
        if total > 1e-10:
            constrained = constrained / total

        return constrained


class LeverageStrategy(OverlayStrategy):
    """
    Apply leverage limits to portfolio.

    This overlay ensures gross leverage (sum of absolute values) stays within
    a maximum limit. Primarily useful when underlying strategy might produce
    short positions (though most current strategies are long-only).

    Example:
        hrp = HRPStrategy(underlying=market)
        deleveraged = LeverageOverlay(underlying=hrp, max_leverage=1.5)
        # Limits gross leverage to 150% (e.g., 1.5x long, 0x short)
    """

    def __init__(self, underlying: ExecutableStrategy, max_leverage: float = 1.0):
        """
        Initialize leverage overlay.

        Args:
            underlying: Strategy to apply leverage limit to
            max_leverage: Maximum gross leverage (default 1.0 = 100% long)
                         2.0 allows 2x leverage, e.g., 150% long + 50% short
        """
        if max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive, got {max_leverage}")

        super().__init__(underlying, name=f"Leverage ({max_leverage:.1f}x)")
        self.max_leverage = max_leverage

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        """
        Apply leverage constraints.

        Args:
            weights: Original weights from underlying strategy
            context: OverlayContext (unused for leverage)

        Returns:
            Deleveraged weights satisfying gross leverage limit
        """
        # Calculate gross leverage (sum of absolute values)
        gross_leverage = weights.abs().sum()

        if gross_leverage <= self.max_leverage:
            # Already within limit
            return weights

        # Scale down all positions proportionally to limit
        # This preserves relative weights while reducing leverage
        scale = self.max_leverage / gross_leverage
        deleveraged = weights * scale

        return deleveraged
