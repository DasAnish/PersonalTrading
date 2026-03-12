"""
Portfolio optimization strategies.

This module provides:
1. Legacy strategies (BaseStrategy interface):
   - HRPStrategy: Hierarchical Risk Parity
   - EqualWeightStrategy: 1/N benchmark

2. Composable strategies (ExecutableStrategy interface):
   - MarketStrategy: Define asset universes (e.g., UKETFsMarket)
   - AllocationStrategy: Calculate weights (HRPStrategy, EqualWeightStrategy)
   - OverlayStrategy: Transform weights (e.g., VolatilityTargetOverlay)

3. Strategy Registry:
   Pluggable system for strategy selection via CLI arguments.
"""

from typing import List, Type
from .base import BaseStrategy, ExecutableStrategy, MarketStrategy, AllocationStrategy, OverlayStrategy
from .models import Instrument, MarketDefinition, OverlayContext
from .hrp import HRPStrategy
from .equal_weight import EqualWeightStrategy
from .markets import UKETFsMarket, USEquitiesMarket, CustomMarket, EuropeanEquitiesMarket, BondsMarket, CommunitiesMarket
from .overlays import VarianceTargetStrategy, VolatilityTargetStrategy, ConstraintStrategy, LeverageStrategy


# Strategy Registry for pluggable strategy selection
STRATEGY_REGISTRY = {
    'hrp': {
        'class': HRPStrategy,
        'display_name': 'Hierarchical Risk Parity',
        'params': {
            'linkage_method': {
                'type': str,
                'default': 'single',
                'choices': ['single', 'complete', 'average', 'ward'],
                'help': 'Linkage criterion for hierarchical clustering'
            }
        }
    },
    'equal_weight': {
        'class': EqualWeightStrategy,
        'display_name': 'Equal Weight',
        'params': {}
    }
}


def create_strategy(strategy_name: str, **kwargs) -> BaseStrategy:
    """
    Create strategy instance from registry.

    Args:
        strategy_name: Strategy key from STRATEGY_REGISTRY
        **kwargs: Strategy-specific parameters (e.g., linkage_method='ward' for HRP)

    Returns:
        Initialized strategy instance

    Raises:
        ValueError: If strategy_name not in registry or invalid parameters

    Example:
        >>> strategy = create_strategy('hrp', linkage_method='ward')
        >>> strategy.name
        'Hierarchical Risk Parity'
    """
    if strategy_name not in STRATEGY_REGISTRY:
        available = ', '.join(STRATEGY_REGISTRY.keys())
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. Available: {available}"
        )

    config = STRATEGY_REGISTRY[strategy_name]
    strategy_class = config['class']

    return strategy_class(**kwargs)


def get_available_strategies() -> List[str]:
    """
    Get list of available strategy names.

    Returns:
        List of strategy keys in STRATEGY_REGISTRY

    Example:
        >>> get_available_strategies()
        ['hrp', 'equal_weight']
    """
    return list(STRATEGY_REGISTRY.keys())


def get_strategy_display_name(strategy_name: str) -> str:
    """
    Get display name for a strategy.

    Args:
        strategy_name: Strategy key

    Returns:
        Human-friendly display name

    Raises:
        ValueError: If strategy_name not in registry
    """
    if strategy_name not in STRATEGY_REGISTRY:
        available = ', '.join(STRATEGY_REGISTRY.keys())
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. Available: {available}"
        )

    return STRATEGY_REGISTRY[strategy_name]['display_name']


__all__ = [
    # Legacy interfaces
    'BaseStrategy',
    # Composable strategy interfaces
    'ExecutableStrategy',
    'MarketStrategy',
    'AllocationStrategy',
    'OverlayStrategy',
    # Data models
    'Instrument',
    'MarketDefinition',
    'OverlayContext',
    # Strategies
    'HRPStrategy',
    'EqualWeightStrategy',
    # Market strategies
    'UKETFsMarket',
    'USEquitiesMarket',
    'CustomMarket',
    'EuropeanEquitiesMarket',
    'BondsMarket',
    'CommunitiesMarket',
    # Overlay strategies
    'VarianceTargetStrategy',
    'VolatilityTargetStrategy',
    'ConstraintStrategy',
    'LeverageStrategy',
    # Registry and utilities
    'STRATEGY_REGISTRY',
    'create_strategy',
    'get_available_strategies',
    'get_strategy_display_name',
]
