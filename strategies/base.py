"""
Compatibility aliases for strategy base classes.

The canonical implementations live in strategies.core. This module
re-exports them under the names used by strategy_loader and run_backtest.

  ExecutableStrategy  →  Strategy   (the abstract base)
  MarketStrategy      →  AssetStrategy  (single-instrument leaf)
  AllocationStrategy  →  AllocationStrategy
  OverlayStrategy     →  OverlayStrategy
"""

from strategies.core import (
    Strategy as ExecutableStrategy,
    AssetStrategy as MarketStrategy,
    AllocationStrategy,
    OverlayStrategy,
    StrategyContext,
    DataRequirements,
)

__all__ = [
    'ExecutableStrategy',
    'MarketStrategy',
    'AllocationStrategy',
    'OverlayStrategy',
    'StrategyContext',
    'DataRequirements',
]
