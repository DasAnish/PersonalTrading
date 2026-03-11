# Composable Strategy Architecture

## Overview

The new composable strategy architecture enables building complex trading strategies by composing simpler, reusable components. Think of it like LEGO blocks - you can build different portfolios by stacking market definitions, allocation strategies, and risk overlays.

```
VolatilityTarget
      ↓ (wraps)
    HRP
      ↓ (wraps)
  UKETFsMarket
```

## Architecture

The system is built on three main types of strategies:

### 1. Market Strategies

Define **which assets** to trade. Built-in markets include:

- **UKETFsMarket**: VUSA, SSLN, SGLN, IWRD (GBP)
- **USEquitiesMarket**: AAPL, MSFT, GOOGL, AMZN (USD)
- **EuropeanEquitiesMarket**: ASML, SAP, UNA, NSRGY (EUR)
- **CustomMarket**: Define your own symbols

```python
from strategies import UKETFsMarket, CustomMarket

# Built-in market
uk_etfs = UKETFsMarket()

# Custom market
my_market = CustomMarket(
    symbols=['VUSA', 'VGOV', 'VBTA'],
    currency='GBP'
)
```

### 2. Allocation Strategies

Calculate **how much** to allocate to each asset. Currently:

- **HRPStrategy**: Hierarchical Risk Parity (advanced optimization)
- **EqualWeightStrategy**: 1/N allocation (simple benchmark)

All allocation strategies wrap a market definition:

```python
from strategies import HRPStrategy, EqualWeightStrategy, UKETFsMarket

market = UKETFsMarket()

# HRP with single linkage
hrp = HRPStrategy(underlying=market, linkage_method='single')

# HRP with ward linkage (different clustering)
hrp_ward = HRPStrategy(underlying=market, linkage_method='ward')

# Equal weight
ew = EqualWeightStrategy(underlying=market)
```

### 3. Overlay Strategies

Apply **dynamic adjustments** to weights. Built-in overlays:

- **VarianceTargetOverlay**: Scale weights to achieve target variance (math-friendly alternative to vol targeting)
- **VolatilityTargetOverlay**: Scale weights to achieve target volatility
- **ConstraintOverlay**: Apply min/max weight limits per position
- **LeverageOverlay**: Apply gross leverage limits

Overlays wrap any other strategy:

```python
from strategies import (
    VolatilityTargetOverlay,
    ConstraintOverlay,
    HRPStrategy,
    UKETFsMarket
)

market = UKETFsMarket()
hrp = HRPStrategy(underlying=market)

# Single overlay
vol_target = VolatilityTargetOverlay(underlying=hrp, target_vol=0.12)

# Chained overlays
constrained = ConstraintOverlay(
    underlying=vol_target,
    min_weight=0.05,
    max_weight=0.40
)
```

## Usage Patterns

### Pattern 1: Simple Allocation

Just calculate weights for a given set of assets:

```python
from strategies import HRPStrategy, UKETFsMarket

market = UKETFsMarket()
strategy = HRPStrategy(underlying=market)

# Calculate weights from prices
weights = strategy.calculate_weights(prices_dataframe)
print(weights)
# Output:
# VUSA    0.30
# SSLN    0.25
# SGLN    0.20
# IWRD    0.25
```

### Pattern 2: Allocation with Overlay

Apply risk management on top of allocation:

```python
from strategies import (
    HRPStrategy,
    VolatilityTargetOverlay,
    UKETFsMarket
)

market = UKETFsMarket()
hrp = HRPStrategy(underlying=market)
vol_target = VolatilityTargetOverlay(underlying=hrp, target_vol=0.15)

# Weights are automatically scaled based on realized volatility
weights = vol_target.calculate_weights(prices_dataframe)
```

### Pattern 3: Multiple Overlays

Stack overlays for comprehensive portfolio management:

```python
from strategies import (
    HRPStrategy,
    VolatilityTargetOverlay,
    ConstraintOverlay,
    UKETFsMarket
)

market = UKETFsMarket()
allocation = HRPStrategy(underlying=market)
vol_targeted = VolatilityTargetOverlay(underlying=allocation, target_vol=0.12)
constrained = ConstraintOverlay(
    underlying=vol_targeted,
    min_weight=0.05,   # Min 5% per position
    max_weight=0.35    # Max 35% per position
)

weights = constrained.calculate_weights(prices_dataframe)
```

### Pattern 4: Testing Same Allocation on Different Markets

Easily compare how a strategy performs on different asset universes:

```python
from strategies import HRPStrategy, UKETFsMarket, USEquitiesMarket

uk_market = UKETFsMarket()
us_market = USEquitiesMarket()

# Same strategy, different markets
hrp_uk = HRPStrategy(underlying=uk_market)
hrp_us = HRPStrategy(underlying=us_market)

# Run backtests to compare
results_uk = engine.run_backtest(hrp_uk, uk_prices, start, end)
results_us = engine.run_backtest(hrp_us, us_prices, start, end)
```

## How Overlays Work

### Variance Target Overlay

Scales portfolio weights to achieve a target variance level.

**Variance vs Volatility:**
- **Variance**: Variance of returns × 252 (scales linearly with time)
- **Volatility**: Standard deviation of returns × √252 (scales with sqrt of time)
- **Relationship**: Volatility = √Variance

Example: 15% volatility = 0.0225 variance

**How it works:**
1. **Calculate realized variance** from underlying strategy's returns
   - Formula: `realized_var = returns.var() * 252` (annualized)
   - Uses lookback window (default 252 days)

2. **Calculate scaling factor**: `scale = target_variance / realized_variance`
   - If realized_var = 0.04 and target = 0.02, scale = 0.50
   - Scales DOWN when variance is high, scales UP when variance is low

3. **Scale weights**: `scaled_weights = original_weights * scale`
   - Maintains relative proportions while reducing risk
   - No leverage (capped at scale = 1.0)

4. **Remaining goes to cash**: `cash = 1 - sum(scaled_weights)`
   - Variance targeting often results in cash allocation
   - Can provide stability during high-variance periods

**When to use:**
- Risk budgeting and portfolio optimization (variance is additive)
- When you prefer working with variance instead of volatility
- More mathematical/formal portfolio approaches

Example:
```python
from strategies import VarianceTargetOverlay, HRPStrategy, UKETFsMarket

market = UKETFsMarket()
hrp = HRPStrategy(underlying=market)
var_target = VarianceTargetOverlay(
    underlying=hrp,
    target_variance=0.02,  # Targets 2% annual variance
    lookback_days=252
)

weights = var_target.calculate_weights(prices)
```

### Volatility Target Overlay

Scales portfolio weights to achieve a target volatility level:

1. **Calculate realized volatility** from the underlying strategy's returns
   - Uses historical portfolio values over a lookback window (default 252 days)
   - Formula: `realized_vol = returns.std() * sqrt(252)` (annualized)

2. **Calculate scaling factor**: `scale = target_vol / realized_vol`
   - If realized_vol = 20% and target = 12%, scale = 0.60
   - Scales DOWN when vol is high, scales UP when vol is low

3. **Scale weights**: `scaled_weights = original_weights * scale`
   - Larger positions become smaller
   - Maintains relative proportions while reducing risk

4. **Remaining goes to cash**: `cash = 1 - sum(scaled_weights)`
   - Typically 0% when vol target is met
   - Can be 40%+ when vol is very high (cash drag)

### Constraint Overlay

Enforces position size limits:

1. **Remove positions below minimum**: `weight < min_weight`
2. **Cap positions above maximum**: `weight > max_weight`
3. **Redistribute removed/capped weight** proportionally to remaining positions
4. **Iterate until converged** (typically 2-3 iterations)

Benefits:
- Prevents portfolio concentration
- Ensures all positions are meaningful (avoid tiny positions)
- Controls single-stock risk

### Leverage Overlay

Applies gross leverage limits:

1. **Calculate gross leverage**: `sum(abs(weights))`
2. **Scale down if needed**: `weights * (max_leverage / gross_leverage)`

Useful for:
- Preventing leverage creep
- Ensuring portfolio stays within risk limits
- Managing margin requirements

## Backtesting with Overlays

### Using Traditional API

The traditional approach still works for backward compatibility:

```python
from backtesting import BacktestEngine
from strategies import HRPStrategy, UKETFsMarket

engine = BacktestEngine(
    initial_capital=10000.0,
    transaction_cost_bps=7.5,
    rebalance_frequency='monthly'
)

market = UKETFsMarket()
strategy = HRPStrategy(underlying=market)

# Run backtest with pre-fetched prices
results = engine.run_backtest(
    strategy=strategy,
    historical_data=prices_dataframe,
    start_date=start_date,
    end_date=end_date
)

print(f"Final portfolio value: {results.final_value:.2f}")
print(f"Return: {(results.final_value/10000 - 1)*100:.2f}%")
```

### Using Overlay API

For overlays, use the specialized overlay method:

```python
from backtesting import BacktestEngine
from strategies import (
    HRPStrategy,
    VolatilityTargetOverlay,
    UKETFsMarket
)

engine = BacktestEngine(initial_capital=10000.0)

market = UKETFsMarket()
hrp = HRPStrategy(underlying=market)
vol_target = VolatilityTargetOverlay(underlying=hrp, target_vol=0.12)

# First run underlying to get portfolio values
hrp_results = engine.run_backtest(hrp, prices_dataframe, start, end)

# Then run overlay which uses underlying results
overlay_results = engine.run_backtest_with_overlay(
    underlying_strategy=hrp,
    overlay_strategy=vol_target,
    historical_data=prices_dataframe,
    underlying_results=hrp_results,
    start_date=start,
    end_date=end
)

print(f"HRP final value: {hrp_results.final_value:.2f}")
print(f"Vol-targeted HRP final value: {overlay_results.final_value:.2f}")
```

## Creating Custom Strategies

### Custom Market

```python
from strategies import CustomMarket, Instrument

instruments = [
    Instrument('VUSA', currency='GBP', exchange='SMART'),
    Instrument('BTC', currency='USD', exchange='GEMINI'),
]

crypto_market = CustomMarket(instruments=instruments, name="Crypto Portfolio")
```

### Custom Overlay

```python
from strategies import OverlayStrategy
from strategies.models import OverlayContext
import pandas as pd

class MyCustomOverlay(OverlayStrategy):
    """Apply custom logic to transform weights."""

    def __init__(self, underlying, custom_param):
        super().__init__(underlying, name="My Custom Overlay")
        self.custom_param = custom_param

    def transform_weights(self, weights: pd.Series, context: OverlayContext) -> pd.Series:
        """Transform weights based on custom logic."""
        # Apply your custom transformation
        transformed = weights * self.custom_param
        # Normalize if needed
        return transformed / transformed.sum()

# Use it like any other overlay
from strategies import HRPStrategy

hrp = HRPStrategy(underlying=market)
custom = MyCustomOverlay(underlying=hrp, custom_param=0.8)
weights = custom.calculate_weights(prices)
```

## Data Flow

When you call `calculate_weights()` on a composed strategy:

```
Input: prices_dataframe
  ↓
1. AllocationStrategy.calculate_weights(prices)
   - Calls underlying if it's also AllocationStrategy
   - Implements weight calculation logic (e.g., HRP)
   ↓
2. OverlayStrategy.transform_weights(weights, context)
   - Takes weights from underlying
   - Applies transformation (e.g., scaling for vol target)
   - Returns adjusted weights
  ↓
Output: transformed_weights_series
```

## Examples

See `examples/composable_strategies_demo.py` for comprehensive examples:

```bash
python examples/composable_strategies_demo.py
```

## Benefits

1. **Modularity**: Each component has a single responsibility
2. **Reusability**: Markets, allocations, and overlays can be mixed and matched
3. **Testability**: Easy to test each layer independently
4. **Flexibility**: Add new overlays without modifying existing code
5. **Composability**: Combine as many overlays as needed
6. **Clarity**: Code reads like a description of the portfolio

## Backward Compatibility

Old code continues to work:

```python
# Old API - still works
from strategies import BaseStrategy

strategy = HRPStrategy(linkage_method='ward')
weights = strategy.calculate_weights(prices)
```

The new composable architecture is **optional** - use it when you want composition, use the old API when you don't.

## Next Steps

1. **Try the examples**: Run `composable_strategies_demo.py`
2. **Create custom overlays**: Implement your own risk management logic
3. **Define custom markets**: Target specific asset universes
4. **Run backtests**: Compare strategies with and without overlays
5. **Build your portfolio**: Compose your ideal strategy

## Architecture Details

See `CLAUDE.md` for the technical architecture, including:
- Class hierarchy and interfaces
- Design decisions and trade-offs
- Implementation details
- Future enhancement roadmap
