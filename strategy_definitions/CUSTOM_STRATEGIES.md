# Creating Custom Strategies

Guide to defining and using custom strategies with the YAML-based configuration system.

## Quick Start

1. **Create a YAML file** in the appropriate subdirectory
2. **Define strategy parameters** in YAML format
3. **Use it immediately** - no code changes needed!

## Step-by-Step Guide

### Step 1: Choose Strategy Type

**Markets** (asset universe definitions)
- Which assets to trade
- Located in: `strategy_definitions/markets/`

**Allocations** (weight calculation)
- How to allocate to assets
- Located in: `strategy_definitions/allocations/`

**Overlays** (weight transformation)
- Transform weights from allocation
- Located in: `strategy_definitions/overlays/`

**Composed** (multi-layer)
- Stack allocations and overlays
- Located in: `strategy_definitions/composed/`

### Step 2: Create YAML File

#### Example 1: Custom Allocation Strategy

File: `strategy_definitions/allocations/my_momentum.yaml`

```yaml
type: allocation
class: TrendFollowingStrategy
market: uk_etfs
description: |
  My custom momentum strategy with different parameters.
  Uses faster EWMA decay and stricter thresholding.

parameters:
  lookback_days: 252      # 1 year instead of 2 years
  half_life_days: 30      # 30-day EWMA instead of 60
  smooth_window: 3        # Less smoothing
  signal_threshold: 0.15  # Stricter threshold
```

**Usage**:
```bash
python scripts/run_backtest.py --use-definitions --strategy my_momentum --benchmark hrp_ward
```

#### Example 2: Custom Overlay Strategy

File: `strategy_definitions/overlays/vol_target_10pct.yaml`

```yaml
type: overlay
class: VolatilityTargetStrategy
underlying: hrp_single
description: |
  Aggressive volatility target for growth portfolios.
  Targets 10% annual volatility (conservative).

parameters:
  target_vol: 0.10
  lookback_days: 252
```

**Usage**:
```bash
python scripts/run_backtest.py --use-definitions --strategy hrp_single --benchmark equal_weight
# The overlay will be applied when building from YAML
```

#### Example 3: Custom Composed Strategy

File: `strategy_definitions/composed/balanced_momentum.yaml`

```yaml
type: composed
description: |
  Balanced momentum strategy with risk constraints.

  Composition:
  1. Market: UK ETFs
  2. Allocation: Trend Following with aggressive lookback
  3. Overlay 1: Weight constraints (10%-25% per position)
  4. Overlay 2: Volatility target (15%)

layers:
  - my_constraints_10_25
  - vol_target_15pct
```

**Note**: The first layer references an allocation's underlying strategy.
Subsequent layers are applied on top.

**Usage**:
```bash
python scripts/run_backtest.py --use-definitions --composed-strategy balanced_momentum
```

## Key Concepts

### 1. File Naming

Your YAML filename becomes the strategy key:
- `my_strategy.yaml` → key is `my_strategy`
- `aggressive_hrp.yaml` → key is `aggressive_hrp`
- `vol_target_10pct.yaml` → key is `vol_target_10pct`

**Naming conventions**:
- Use lowercase with underscores
- Be descriptive: `hrp_aggressive` not `strat1`
- Include parameters if relevant: `vol_target_10pct` not just `vol_target`

### 2. Strategy References

Strategies reference each other by key (filename without .yaml):

```yaml
type: overlay
class: VolatilityTargetStrategy
underlying: my_momentum    # References allocations/my_momentum.yaml
```

The loader searches all subdirectories for matching keys automatically.

### 3. Parameter Types

YAML supports different parameter types:

```yaml
parameters:
  lookback_days: 504        # Integer
  target_vol: 0.12          # Float
  signal_threshold: 0.1     # Float (0-1)
  linkage_method: ward      # String
  use_cache: true           # Boolean
```

### 4. Multi-Layer Composition

Stack overlays in order:

```yaml
type: composed
description: |
  Multiple overlays applied in sequence:
  1. First overlay modifies allocation weights
  2. Second overlay receives result from first
  3. Third overlay receives result from second

layers:
  - constraints_5_40       # Layer 1: Apply constraints
  - vol_target_12pct       # Layer 2: Apply vol target
  - leverage_1x            # Layer 3: Apply leverage limit
```

Result: `leverage_1x(vol_target_12pct(constraints_5_40(trend_following)))`

## Real-World Examples

### Example 1: Aggressive Growth Strategy

File: `strategy_definitions/allocations/aggressive_momentum.yaml`

```yaml
type: allocation
class: TrendFollowingStrategy
market: uk_etfs
description: |
  Aggressive momentum strategy targeting growth.
  - Shorter lookback for faster trend detection
  - Lower EWMA half-life for responsiveness
  - Lower threshold to capture weak trends

  Best for: Growth portfolios, bull markets

parameters:
  lookback_days: 252       # 1 year
  half_life_days: 30       # Very responsive
  smooth_window: 3         # Minimal smoothing
  signal_threshold: 0.05   # Capture weak signals
```

### Example 2: Conservative Risk-Managed Strategy

File: `strategy_definitions/composed/conservative_income.yaml`

```yaml
type: composed
description: |
  Conservative portfolio with multiple risk controls.

  Components:
  1. HRP allocation for diversification
  2. Tight constraints to prevent concentration
  3. Low volatility target

  Best for: Income investors, retirement portfolios

layers:
  - conservative_constraints
  - vol_target_8pct
```

Where `conservative_constraints` is defined as:

File: `strategy_definitions/overlays/conservative_constraints.yaml`

```yaml
type: overlay
class: ConstraintStrategy
underlying: hrp_ward
description: Very conservative position limits

parameters:
  min_weight: 0.15       # Minimum 15% per position
  max_weight: 0.25       # Maximum 25% per position
```

### Example 3: Tactical Rebalancing Strategy

File: `strategy_definitions/allocations/tactical.yaml`

```yaml
type: allocation
class: TrendFollowingStrategy
market: uk_etfs
description: |
  Tactical allocation based on intermediate momentum.
  Balances responsiveness with stability.

parameters:
  lookback_days: 504      # 2 years (standard)
  half_life_days: 90      # Slower decay (3 months)
  smooth_window: 10       # Significant smoothing
  signal_threshold: 0.12  # Only strong signals
```

## Testing Your Strategies

### 1. List Available Strategies

```bash
python -c "
from strategies.strategy_loader import StrategyLoader
loader = StrategyLoader()
print('Markets:', list(loader.list_strategies('market').keys()))
print('Allocations:', list(loader.list_strategies('allocation').keys()))
print('Overlays:', list(loader.list_strategies('overlay').keys()))
print('Composed:', list(loader.list_strategies('composed').keys()))
"
```

### 2. Print Strategy Info

```bash
python -c "
from strategies.strategy_loader import StrategyLoader
loader = StrategyLoader()
loader.print_strategy_info('my_momentum')
"
```

### 3. Build and Test Strategy

```python
from strategies.strategy_loader import StrategyLoader
import pandas as pd

loader = StrategyLoader()

# Build your strategy
strategy = loader.build_allocation_strategy('my_momentum')

# Test with sample data
prices_df = pd.DataFrame({...})  # Your price data
weights = strategy.calculate_weights(prices_df)
print(weights)
```

### 4. Backtest Your Strategy

```bash
# Single strategy vs benchmark
python scripts/run_backtest.py --use-definitions \
  --strategy my_momentum \
  --benchmark hrp_ward

# Composed strategy
python scripts/run_backtest.py --use-definitions \
  --composed-strategy balanced_momentum
```

## Available Classes

### Allocation Classes

```python
from strategies import (
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy
)
```

Use these class names in your YAML:
- `HRPStrategy`
- `TrendFollowingStrategy`
- `EqualWeightStrategy`

### Overlay Classes

```python
from strategies import (
    VolatilityTargetStrategy,
    VarianceTargetStrategy,
    ConstraintStrategy,
    LeverageStrategy
)
```

Use these class names in your YAML:
- `VolatilityTargetStrategy`
- `VarianceTargetStrategy`
- `ConstraintStrategy`
- `LeverageStrategy`

## Parameter Reference

### TrendFollowingStrategy Parameters

```yaml
parameters:
  lookback_days: 504              # Historical window (days)
  half_life_days: 60              # EWMA decay (days)
  smooth_window: 5                # Signal smoothing window (days)
  signal_threshold: 0.1           # Min signal magnitude to include
  min_volatility: 0.001           # Floor for volatility
```

### HRPStrategy Parameters

```yaml
parameters:
  linkage_method: single          # Clustering: single|complete|average|ward
```

### VolatilityTargetStrategy Parameters

```yaml
parameters:
  target_vol: 0.15               # Target annual volatility (0-1)
  lookback_days: 252             # Volatility lookback (days)
```

### VarianceTargetStrategy Parameters

```yaml
parameters:
  target_variance: 0.02          # Target annual variance (0-1)
  lookback_days: 252             # Variance lookback (days)
```

### ConstraintStrategy Parameters

```yaml
parameters:
  min_weight: 0.05               # Minimum weight (0-1)
  max_weight: 0.40               # Maximum weight (0-1)
```

### LeverageStrategy Parameters

```yaml
parameters:
  max_leverage: 1.0              # Max gross leverage (1.0 = long-only)
```

## Best Practices

### 1. Use Descriptive Names

Good:
```yaml
# strategy_definitions/overlays/vol_target_conservative_8pct.yaml
```

Bad:
```yaml
# strategy_definitions/overlays/vt_8.yaml
```

### 2. Document Purpose

Always include a clear description:

```yaml
description: |
  This strategy targets conservative growth with:
  - HRP allocation for diversification
  - 8% volatility target for stability
  - Tight constraints for consistency

  Suitable for: Conservative investors, retirement funds
```

### 3. Use Sensible Defaults

Start with proven values:
- Lookback: 252-504 days (1-2 years)
- EWMA half-life: 30-120 days
- Volatility target: 10-15% annual
- Position limits: 5-40% range

### 4. Version Your Variants

Create variants for different risk levels:

```yaml
# Conservative: 8% vol target
vol_target_8pct.yaml

# Moderate: 12% vol target
vol_target_12pct.yaml

# Aggressive: 15% vol target
vol_target_15pct.yaml
```

### 5. Keep Overlays Generic

Design overlays to work with any allocation:

```yaml
type: overlay
class: VolatilityTargetStrategy
underlying: null    # Leave blank to allow any underlying
```

Then use programmatically:
```python
loader = StrategyLoader()
vol_target = loader.build_overlay_strategy('vol_target_12pct', underlying=my_allocation)
```

## Troubleshooting

### Error: "Strategy definition not found: my_strategy"

**Cause**: YAML file not in correct directory or wrong filename

**Solution**:
- Check file is named `my_strategy.yaml`
- Verify it's in the correct subdirectory (markets, allocations, overlays, or composed)
- Run: `ls strategy_definitions/*/*.yaml | grep my_strategy`

### Error: "Cannot import class: MyClass"

**Cause**: Class name doesn't exist in strategies module

**Solution**:
- Check class name matches exactly
- Verify it's exported from strategies/__init__.py
- List available: `python -c "from strategies import *; print(dir())"`

### Error: "Overlay strategy requires underlying strategy"

**Cause**: Overlay definition missing `underlying:` field

**Solution**:
```yaml
type: overlay
class: VolatilityTargetStrategy
underlying: hrp_ward    # Add this field!
```

### Strategy Loads But Gives Wrong Results

**Cause**: Parameter types or values incorrect

**Solution**:
- Check YAML syntax (colons, indentation)
- Verify parameter values are in valid ranges
- Test with simple parameters first
- Compare with working examples

## Advanced: Using Multiple Markets

Create market-specific variants:

```yaml
# strategy_definitions/allocations/hrp_us_aggressive.yaml
type: allocation
class: HRPStrategy
market: us_equities           # Use US market instead
parameters:
  linkage_method: ward
```

```yaml
# strategy_definitions/allocations/hrp_uk_conservative.yaml
type: allocation
class: HRPStrategy
market: uk_etfs               # Use UK market
parameters:
  linkage_method: single
```

## Next Steps

1. Review existing strategies in `strategy_definitions/`
2. Copy a similar YAML file as template
3. Modify parameters for your use case
4. Test with backtest script
5. Compare results with benchmarks
6. Iterate and refine

## Resources

- [Strategy Definitions README](README.md) - System overview
- [strategy_definitions/ folder](.) - Existing examples
- `python -c "from strategies.strategy_loader import StrategyLoader; help(StrategyLoader)"`
