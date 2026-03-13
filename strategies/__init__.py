"""
Portfolio optimization strategies using new unified architecture.

All strategies inherit from the unified Strategy interface in core.py:
- AssetStrategy: Individual instruments (VUSA, AAPL, etc.)
- AllocationStrategy: Portfolio allocation (HRP, TrendFollowing, EqualWeight)
- OverlayStrategy: Weight transformations (VolTarget, Constraints, etc.)

Strategies are composable and can be nested at any depth.

Example:
    from strategies.core import AssetStrategy
    from strategies.hrp import HRPStrategy
    from strategies.overlays import VolatilityTargetStrategy

    # Assets as strategies
    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
    ]

    # Portfolio strategy
    hrp = HRPStrategy(underlying=assets, linkage_method='ward')

    # Overlay on portfolio
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)

    # Meta-portfolio (portfolio of strategies)
    from strategies.equal_weight import EqualWeightStrategy
    meta = EqualWeightStrategy(underlying=[hrp, vol_target])
"""

# Core interfaces
from .core import (
    Strategy,
    AssetStrategy,
    AllocationStrategy,
    OverlayStrategy,
    StrategyContext,
    DataRequirements
)

# Concrete allocation strategies
from .hrp import HRPStrategy
from .equal_weight import EqualWeightStrategy
from .trend_following import TrendFollowingStrategy

# Overlay strategies
from .overlays import (
    VolatilityTargetStrategy,
    ConstraintStrategy,
    LeverageStrategy
)

__all__ = [
    # Core interfaces
    'Strategy',
    'AssetStrategy',
    'AllocationStrategy',
    'OverlayStrategy',
    'StrategyContext',
    'DataRequirements',
    # Allocation strategies
    'HRPStrategy',
    'EqualWeightStrategy',
    'TrendFollowingStrategy',
    # Overlay strategies
    'VolatilityTargetStrategy',
    'ConstraintStrategy',
    'LeverageStrategy',
]
