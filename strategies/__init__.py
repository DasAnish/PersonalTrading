"""
Portfolio optimization strategies.

This module provides various portfolio optimization strategies including:
- Hierarchical Risk Parity (HRP)
- Equal Weight benchmark

Strategy Registry:
    Provides a pluggable system for strategy selection via CLI arguments.
    New strategies can be added by registering them in STRATEGY_REGISTRY.
"""

from typing import List, Type
from .base import BaseStrategy
from .hrp import HRPStrategy
from .equal_weight import EqualWeightStrategy


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
    'BaseStrategy',
    'HRPStrategy',
    'EqualWeightStrategy',
    'STRATEGY_REGISTRY',
    'create_strategy',
    'get_available_strategies',
    'get_strategy_display_name',
]
