"""
Strategy discovery and CLI-argument extraction helpers.

Moved from ``scripts/run_backtest.py`` (Phase 3 refactor):
    ``extract_strategy_params``      (:150)
    ``get_all_available_strategies`` (:174)

These are pure catalog/lookup helpers with no dependency on the CLI script
itself (only on the strategy registry and ``StrategyLoader``), so they now
live alongside the rest of the ``strategies`` package.
"""

from __future__ import annotations

import logging

from . import STRATEGY_REGISTRY, create_strategy
from .strategy_loader import StrategyLoader

logger = logging.getLogger(__name__)


def extract_strategy_params(args, strategy_name: str) -> dict:
    """
    Extract parameters for a specific strategy from CLI args.

    Args:
        args: Parsed command-line arguments
        strategy_name: Strategy key (e.g., 'hrp')

    Returns:
        Dictionary of strategy-specific parameters
    """
    config = STRATEGY_REGISTRY[strategy_name]
    params = {}

    for param_name in config.get("params", {}).keys():
        arg_name = f"{strategy_name}_{param_name}"
        if hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                params[param_name] = value

    return params


def get_all_available_strategies(use_definitions: bool = True) -> dict:
    """
    Get all available strategies from strategy definitions.

    Args:
        use_definitions: If True, load from YAML definitions; else from registry

    Returns:
        Dict mapping strategy_key to (strategy_object, strategy_info)
    """
    if use_definitions:
        loader = StrategyLoader()
        available = {}

        # Get all allocations, composed strategies, and meta-portfolios
        allocations = loader.list_strategies("allocation")
        composed = loader.list_strategies("composed")
        portfolios = loader.list_strategies("portfolio")

        for strategy_key in (
            list(allocations.keys()) + list(composed.keys()) + list(portfolios.keys())
        ):
            try:
                strategy = loader.build_strategy(strategy_key)
                definition = loader.load_definition(strategy_key)
                info = {
                    "key": strategy_key,
                    "type": definition.get("type"),
                    "class": definition.get("class"),
                    "description": definition.get("description", ""),
                    "parameters": definition.get("parameters", {}),
                }
                available[strategy_key] = (strategy, info)
            except Exception as e:
                logger.warning(f"Could not load strategy {strategy_key}: {e}")

        return available
    else:
        # Use registry
        available = {}
        for strategy_key, config in STRATEGY_REGISTRY.items():
            if strategy_key not in ["hrp", "equal_weight", "trend_following"]:
                continue  # Only include main allocation strategies
            try:
                strategy = create_strategy(strategy_key)
                info = {
                    "key": strategy_key,
                    "type": "allocation",
                    "class": config["display_name"],
                    "description": "",
                    "parameters": {},
                }
                available[strategy_key] = (strategy, info)
            except Exception as e:
                logger.warning(f"Could not create strategy {strategy_key}: {e}")

        return available
