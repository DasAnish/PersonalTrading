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
from .trend_following import TrendFollowingStrategy
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
    },
    'trend_following': {
        'class': TrendFollowingStrategy,
        'display_name': 'Trend Following',
        'params': {
            'lookback_days': {
                'type': int,
                'default': 504,
                'help': 'Historical window for momentum calculation (default 504 = 2 years)'
            },
            'half_life_days': {
                'type': int,
                'default': 60,
                'help': 'EWMA decay parameter (default 60 days)'
            },
            'signal_threshold': {
                'type': float,
                'default': 0.1,
                'help': 'Minimum signal magnitude to include in portfolio'
            }
        }
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

    # Special handling for AllocationStrategy subclasses that require an underlying market
    if strategy_name in ['trend_following', 'hrp', 'equal_weight']:
        # These allocation strategies need an underlying market
        underlying_market = UKETFsMarket()
        return strategy_class(underlying=underlying_market, **kwargs)
    else:
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
    'TrendFollowingStrategy',
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
