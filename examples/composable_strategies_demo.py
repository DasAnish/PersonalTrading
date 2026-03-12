"""
Demonstration of the new composable strategy architecture.

This example shows how to:
1. Define a market (asset universe)
2. Create allocation strategies that wrap the market
3. Apply overlay strategies on top of allocation strategies
4. Run backtests with the composed strategies

Example compositions:
- VolatilityTarget(HRP(UKETFs))
- Constraint(EqualWeight(USEquities))
- ViolTarget(VolTarget(HRP(UKETFs)))  # Multiple overlays
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta

# Import the composable strategy components
from strategies.markets import UKETFsMarket, USEquitiesMarket
from strategies.hrp import HRPStrategy
from strategies.equal_weight import EqualWeightStrategy
from strategies.overlays import VarianceTargetStrategy, VolatilityTargetStrategy, ConstraintStrategy
from backtesting import BacktestEngine


def example_1_simple_allocation():
    """Example 1: Use allocation strategy with market definition."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Allocation Strategy with Market Definition")
    print("=" * 70)

    # Step 1: Create market definition
    market = UKETFsMarket()
    print(f"\nMarket: {market.name}")
    print(f"  Symbols: {market.get_market_definition().symbols}")

    # Step 2: Create allocation strategy on top of market
    hrp = HRPStrategy(underlying=market, linkage_method='ward')
    print(f"\nStrategy: {hrp.name}")
    print(f"  Underlying market: {hrp.get_market_definition().name}")
    print(f"  Market symbols: {hrp.get_market_definition().symbols}")

    return hrp


def example_2_overlay_strategy():
    """Example 2: Apply overlay strategy on top of allocation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Overlay Strategy (Volatility Target)")
    print("=" * 70)

    # Step 1: Create market
    market = UKETFsMarket()

    # Step 2: Create allocation strategy
    hrp = HRPStrategy(underlying=market, linkage_method='ward')

    # Step 3: Apply overlay
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)
    print(f"\nComposed Strategy: {vol_target.name}")
    print(f"  Layer 1 (Overlay): {vol_target.name}")
    print(f"  Layer 2 (Allocation): {hrp.name}")
    print(f"  Layer 3 (Market): {market.name}")
    print(f"  Symbols: {vol_target.get_market_definition().symbols}")

    return vol_target


def example_2b_variance_target_overlay():
    """Example 2b: Variance Target Overlay (alternative to Vol Target)."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2b: Variance Target Overlay")
    print("=" * 70)

    # Variance vs Volatility explanation
    print("\nVariance vs Volatility:")
    print("  - Variance: var(returns) × 252  (scales linearly)")
    print("  - Volatility: std(returns) × √252  (scales with sqrt)")
    print("  - Relationship: vol = √var")
    print("\nExample: 12% volatility ≈ 0.0144 variance")
    print("         15% volatility ≈ 0.0225 variance")

    # Step 1: Create market
    market = UKETFsMarket()

    # Step 2: Create allocation strategy
    hrp = HRPStrategy(underlying=market, linkage_method='ward')

    # Step 3: Apply variance target (0.02 variance ≈ 14.1% volatility)
    var_target = VarianceTargetStrategy(underlying=hrp, target_variance=0.02)

    print(f"\nComposed Strategy: {var_target.name}")
    print(f"  Layer 1 (Overlay): {var_target.name}")
    print(f"  Layer 2 (Allocation): {hrp.name}")
    print(f"  Layer 3 (Market): {market.name}")
    print(f"  Symbols: {var_target.get_market_definition().symbols}")
    print(f"\nTarget variance: 0.02 (equivalent to ~14.1% volatility)")

    return var_target


def example_3_multiple_overlays():
    """Example 3: Chain multiple overlays."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Multiple Overlays (Vol Target + Constraints)")
    print("=" * 70)

    # Build composition layer by layer
    market = UKETFsMarket()
    hrp = HRPStrategy(underlying=market)

    # First overlay: Volatility target
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)

    # Second overlay: Constraints on top of vol target
    constrained = ConstraintStrategy(
        underlying=vol_target,
        min_weight=0.05,  # Minimum 5% per position
        max_weight=0.40   # Maximum 40% per position
    )

    print(f"\nComposed Strategy: {constrained.name}")
    print(f"  Layer 1 (Constraints): {constrained.name}")
    print(f"  Layer 2 (Vol Target): {vol_target.name}")
    print(f"  Layer 3 (Allocation): {hrp.name}")
    print(f"  Layer 4 (Market): {market.name}")

    return constrained


def example_4_market_variants():
    """Example 4: Try different markets with same allocation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Same Allocation, Different Markets")
    print("=" * 70)

    # Create different markets
    uk_etfs = UKETFsMarket()
    us_equities = USEquitiesMarket()

    # Apply same HRP strategy to different markets
    hrp_uk = HRPStrategy(underlying=uk_etfs, linkage_method='ward')
    hrp_us = HRPStrategy(underlying=us_equities, linkage_method='ward')

    print(f"\nStrategy 1: {hrp_uk.name}")
    print(f"  Market: {hrp_uk.get_market_definition().name}")
    print(f"  Symbols: {hrp_uk.get_market_definition().symbols}")

    print(f"\nStrategy 2: {hrp_us.name}")
    print(f"  Market: {hrp_us.get_market_definition().name}")
    print(f"  Symbols: {hrp_us.get_market_definition().symbols}")

    return hrp_uk, hrp_us


def example_5_weight_calculation():
    """Example 5: Calculate weights for a specific date."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Calculate Portfolio Weights")
    print("=" * 70)

    # Create a composed strategy
    market = UKETFsMarket()
    hrp = HRPStrategy(underlying=market)
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.15)

    # Create sample price data
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    prices = pd.DataFrame(
        {
            'VUSA': 100 + 0.5 * (dates - dates[0]).days + 2 * (dates - dates[0]).days ** 0.5,
            'SSLN': 50 + 0.3 * (dates - dates[0]).days + 1 * (dates - dates[0]).days ** 0.5,
            'SGLN': 75 + 0.4 * (dates - dates[0]).days + 1.5 * (dates - dates[0]).days ** 0.5,
            'IWRD': 120 + 0.6 * (dates - dates[0]).days + 2.5 * (dates - dates[0]).days ** 0.5,
        },
        index=dates
    )

    print(f"\nSample price data:")
    print(f"  Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"  Symbols: {list(prices.columns)}")

    # Calculate weights using the strategy
    weights = hrp.calculate_weights(prices)

    print(f"\nHRP weights (before overlay):")
    for symbol, weight in weights.items():
        print(f"  {symbol}: {weight:.2%}")
    print(f"  Total: {weights.sum():.2%}")

    # Apply overlay transformation (need to calculate portfolio values first)
    from strategies.models import OverlayContext
    import numpy as np

    # Simulate portfolio values (for demonstration)
    portfolio_values = pd.Series(
        10000 * (1 + np.cumsum(np.random.normal(0, 0.001, len(prices)))),
        index=prices.index
    )

    context = OverlayContext(
        current_date=prices.index[-1],
        prices=prices.iloc[-1],
        underlying_portfolio_values=portfolio_values,
        lookback_window=252
    )

    # Transform weights using overlay
    overlay_weights = vol_target.transform_weights(weights, context)

    print(f"\nVol-target adjusted weights (target vol=15%):")
    for symbol, weight in overlay_weights.items():
        print(f"  {symbol}: {weight:.2%}")
    print(f"  Total: {overlay_weights.sum():.2%}")
    print(f"  Cash allocation: {(1 - overlay_weights.sum()):.2%}")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("COMPOSABLE STRATEGY ARCHITECTURE DEMONSTRATION")
    print("=" * 70)

    # Run examples
    example_1_simple_allocation()
    example_2_overlay_strategy()
    example_2b_variance_target_overlay()
    example_3_multiple_overlays()
    example_4_market_variants()
    example_5_weight_calculation()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
The new composable architecture enables:

1. Market Definitions
   - UKETFsMarket, USEquitiesMarket, etc.
   - Define which assets to trade and how to fetch them

2. Allocation Strategies
   - HRPStrategy, EqualWeightStrategy
   - Calculate portfolio weights from prices
   - Wrap a market definition

3. Overlay Strategies
   - VolatilityTargetStrategy: Scale weights to achieve target vol
   - ConstraintStrategy: Apply min/max weight constraints
   - LeverageStrategy: Apply leverage limits
   - Wrap any other strategy

4. Composition
   - Combine strategies: VolTarget(HRP(UKETFsMarket()))
   - Chain multiple overlays
   - Test same allocation on different markets
   - Compare strategies with consistent market definitions

5. Benefits
   - Modular and testable
   - Reusable components
   - Easy to experiment with risk overlays
   - Clear separation of concerns
   - Backward compatible with old API
    """)
    print("=" * 70)
