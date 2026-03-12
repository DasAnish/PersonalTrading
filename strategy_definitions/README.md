# Strategy Definitions

Configuration-driven strategy system using YAML files. Enables easy strategy definition, composition, and versioning.

## Structure

```
strategy_definitions/
├── markets/              # Market/asset universe definitions
├── allocations/          # Weight calculation strategies
├── overlays/             # Weight transformation strategies
├── composed/             # Multi-layer strategy compositions
└── README.md
```

## Strategy Types

### 1. Market Strategies
Define which assets to trade and how to fetch them.

**Example**: `uk_etfs.yaml`
```yaml
type: market
class: UKETFsMarket
description: UK-listed ETFs (VUSA, SSLN, SGLN, IWRD)
parameters: {}
```

**Available Markets**:
- `uk_etfs` - UK ETFs (VUSA, SSLN, SGLN, IWRD)
- `us_equities` - US Tech (AAPL, MSFT, GOOGL, AMZN)

### 2. Allocation Strategies
Calculate portfolio weights from price data.

**Example**: `trend_following.yaml`
```yaml
type: allocation
class: TrendFollowingStrategy
market: uk_etfs
description: Momentum-based allocation with signal processing
parameters:
  lookback_days: 504
  half_life_days: 60
  smooth_window: 5
  signal_threshold: 0.1
```

**Available Allocations**:
- `hrp_single` - HRP with single linkage
- `hrp_ward` - HRP with ward linkage
- `trend_following` - Momentum signals + volatility normalization
- `equal_weight` - 1/N baseline

### 3. Overlay Strategies
Transform weights from underlying allocation strategies.

**Example**: `vol_target_12pct.yaml`
```yaml
type: overlay
class: VolatilityTargetStrategy
underlying: trend_following
description: Scales allocation to achieve 12% volatility
parameters:
  target_vol: 0.12
  lookback_days: 252
```

**Available Overlays**:
- `vol_target_12pct` - Scale to 12% annual volatility
- `vol_target_15pct` - Scale to 15% annual volatility
- `constraints_5_40` - Min 5%, Max 40% per position
- `constraints_10_30` - Min 10%, Max 30% per position
- `leverage_1x` - Limit gross leverage to 1.0x

### 4. Composed Strategies
Stack multiple overlays for sophisticated portfolio construction.

**Example**: `trend_with_vol_12.yaml`
```yaml
type: composed
description: Trend Following scaled to 12% volatility
layers:
  - vol_target_12pct  # Single overlay
```

**Complex Example**: `trend_constrained_vol_target.yaml`
```yaml
type: composed
description: Trend + Constraints + Vol Target (multi-layer)
layers:
  - constraints_5_40    # First: apply constraints
  - vol_target_12pct    # Second: apply vol targeting to result
```

**Available Composed**:
- `trend_with_vol_12` - Trend Following + Vol Target (12%)
- `hrp_with_constraints` - HRP + Weight Constraints
- `trend_constrained_vol_target` - Multi-layer (Trend + Constraints + Vol Target)

## Usage

### Python API

```python
from strategies.strategy_loader import StrategyLoader
import pandas as pd

# Initialize loader
loader = StrategyLoader()

# Load and build allocation strategy
trend = loader.build_allocation_strategy('trend_following')

# Load overlay strategy (auto-resolves underlying)
vol_target = loader.build_overlay_strategy('vol_target_12pct')

# Load composed strategy (builds all layers)
strategy = loader.build_composed_strategy('trend_with_vol_12')

# Calculate weights
weights = strategy.calculate_weights(prices_df)

# List available strategies
markets = loader.list_strategies('market')
allocations = loader.list_strategies('allocation')
overlays = loader.list_strategies('overlay')
composed = loader.list_strategies('composed')

# Get strategy information
info = loader.get_strategy_info('trend_following')
loader.print_strategy_info('trend_following')
```

### Composition Flow

**Example 1: Simple Overlay**
```
trend_with_vol_12:
  └─ vol_target_12pct (overlay)
     └─ underlying: trend_following (allocation)
        └─ market: uk_etfs
```

**Example 2: Multi-Layer Composition**
```
trend_constrained_vol_target:
  └─ vol_target_12pct (overlay 2)
     └─ constraints_5_40 (overlay 1)
        └─ underlying: trend_following (allocation)
           └─ market: uk_etfs
```

## Adding New Strategies

### 1. Add New Allocation Strategy

Create `strategy_definitions/allocations/my_strategy.yaml`:
```yaml
type: allocation
class: MyNewStrategy
market: uk_etfs
description: |
  Description of the strategy.
  Multiple lines supported.

parameters:
  param1: value1
  param2: value2
```

### 2. Add New Overlay

Create `strategy_definitions/overlays/my_overlay.yaml`:
```yaml
type: overlay
class: MyOverlayStrategy
underlying: hrp_ward  # Reference existing allocation
description: Description of overlay transformation

parameters:
  param1: value1
```

### 3. Add Composed Strategy

Create `strategy_definitions/composed/my_composed.yaml`:
```yaml
type: composed
description: Multi-layer strategy combining multiple overlays

layers:
  - my_overlay        # Single layer
  - another_overlay   # Stacked on top
```

## Key-Based Referencing

All strategies can be referenced by their YAML filename (without extension):
- `uk_etfs` → `strategy_definitions/markets/uk_etfs.yaml`
- `trend_following` → `strategy_definitions/allocations/trend_following.yaml`
- `vol_target_12pct` → `strategy_definitions/overlays/vol_target_12pct.yaml`
- `trend_with_vol_12` → `strategy_definitions/composed/trend_with_vol_12.yaml`

## File Naming Conventions

- **Markets**: Descriptive names (e.g., `uk_etfs`, `us_equities`)
- **Allocations**: Strategy name (e.g., `hrp_single`, `trend_following`)
- **Overlays**: Transformation + parameter (e.g., `vol_target_12pct`, `constraints_5_40`)
- **Composed**: Descriptive composition (e.g., `trend_with_vol_12`, `hrp_with_constraints`)

## Best Practices

1. **Use descriptive names** - Make strategy purpose obvious from filename
2. **Document parameters** - Include explanation of what each parameter does
3. **Keep reusable** - Design overlays to work with different allocations
4. **Version variants** - Use suffixes for variations (e.g., `vol_target_12pct`, `vol_target_15pct`)
5. **Single responsibility** - Each overlay should do one thing well

## Advanced: Custom Composition

Build custom composed strategies at runtime:

```python
# Load base allocation
trend = loader.build_allocation_strategy('trend_following')

# Apply overlays in sequence
vol_target = loader.build_overlay_strategy('vol_target_12pct', underlying=trend)
constrained = loader.build_overlay_strategy('constraints_5_40', underlying=vol_target)

# Final strategy with multiple overlays applied
final_strategy = constrained
weights = final_strategy.calculate_weights(prices)
```

## Troubleshooting

**FileNotFoundError: Strategy definition not found**
- Check strategy filename matches the key used
- Verify file is in correct subdirectory (markets/, allocations/, etc.)

**ValueError: Overlay strategy requires underlying strategy**
- Check `underlying:` field is set in overlay YAML
- Verify referenced strategy exists

**ImportError: Cannot import class**
- Check `class:` field matches actual Python class name
- Verify class is exported from strategies module

## Future Enhancements

- [ ] Schema validation for YAML files
- [ ] Parameter type checking
- [ ] Strategy registry with CLI integration
- [ ] Backtesting directly from strategy YAML keys
- [ ] Strategy metadata (creation date, author, performance notes)
- [ ] Parameter optimization suggestions per strategy
