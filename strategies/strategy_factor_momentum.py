"""
Strategy-Level (Factor) Momentum — Ehsani & Linnainmaa (Journal of Finance 2022).

At each rebalance, hold only sub-strategies whose trailing 12-month paper NAV
return is positive; allocate freed weight to defensive assets (VUTY, SGLN).
Economic rationale: factor premia autocorrelate as arbitrage capital moves slowly.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class StrategyFactorMomentumStrategy(AllocationStrategy):
    """
    Meta-portfolio using time-series momentum at the strategy level.

    For each rebalance:
    1. Compute trailing momentum_lookback_days return for each sub-strategy.
    2. Include sub-strategy iff trailing return > 0.
    3. Blend included sleeves equal-weight.
    4. Allocate freed weight (excluded sleeves) to defensive assets.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        momentum_lookback_days: int = 252,
        name: Optional[str] = None,
    ):
        """
        Args:
            underlying: List of underlying strategies (sleeves).
            momentum_lookback_days: Lookback for trailing return (default 252 = 1y).
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Strategy Factor Momentum ({momentum_lookback_days}d)",
        )
        self.momentum_lookback_days = momentum_lookback_days

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """Calculate weights based on sub-strategy trailing returns."""
        prices = context.prices

        if len(prices) < self.momentum_lookback_days + 1:
            return self._equal_weight_blend(prices)

        # Get all symbols from underlying strategies
        all_symbols = sorted(
            set(sym for strat in self.underlying for sym in strat.get_symbols())
        )

        # Compute trailing returns for each sub-strategy
        sub_strategy_returns = {}
        included_strategies = []

        for sub_strategy in self.underlying:
            try:
                trailing_return = self._compute_trailing_return(
                    sub_strategy, context, self.momentum_lookback_days
                )
                sub_strategy_returns[sub_strategy.name] = trailing_return

                logger.debug(
                    f"Strategy Factor Momentum: {sub_strategy.name} "
                    f"trailing {self.momentum_lookback_days}d return = {trailing_return:.4f}"
                )

                # Include iff trailing return > 0
                if trailing_return > 0.0:
                    included_strategies.append(sub_strategy)
                else:
                    logger.debug(
                        f"Strategy Factor Momentum: excluding {sub_strategy.name} "
                        f"(return {trailing_return:.4f} <= 0)"
                    )

            except Exception as e:
                logger.warning(
                    f"Strategy Factor Momentum: could not compute return for "
                    f"{sub_strategy.name}: {e}, excluding"
                )

        if not included_strategies:
            # All strategies excluded → default to equal weight
            logger.warning(
                "Strategy Factor Momentum: all sub-strategies excluded, "
                "using equal weight fallback"
            )
            return self._equal_weight_blend(prices)

        # Blend included strategies equal-weight
        blended = pd.Series(0.0, index=all_symbols)
        total_weight = 0.0

        for sub_strategy in included_strategies:
            try:
                sub_weights = sub_strategy.calculate_weights(context)
                asset_weights = self._resolve_to_symbols(
                    sub_weights, sub_strategy, all_symbols
                )
                blended += asset_weights
                total_weight += 1.0
            except Exception as e:
                logger.warning(
                    f"Strategy Factor Momentum: could not get weights for "
                    f"{sub_strategy.name}: {e}, skipping"
                )

        if total_weight > 0:
            blended /= total_weight
        else:
            return self._equal_weight_blend(prices)

        # Compute freed weight (from excluded strategies)
        freed_weight = 1.0 - (len(included_strategies) / len(self.underlying))

        if freed_weight > 0:
            # Allocate freed weight to defensive assets
            defensive_assets = [
                s for s in all_symbols if s in ["VUTY", "SGLN", "AGGU"]
            ]
            if not defensive_assets:
                # Fallback: use any available asset
                defensive_assets = [all_symbols[0]]

            for asset in defensive_assets:
                blended[asset] += freed_weight / len(defensive_assets)

        # Normalize
        total = blended.sum()
        if total > 0:
            blended /= total

        return blended

    def get_strategy_lookback(self) -> int:
        """Return max lookback across all sub-strategies + momentum lookback."""
        lookbacks = [self.momentum_lookback_days]
        for strat in self.underlying:
            try:
                req = strat.get_data_requirements()
                if req.lookback_days:
                    lookbacks.append(req.lookback_days)
            except Exception:
                lookbacks.append(252)
        return max(lookbacks)

    def _compute_trailing_return(
        self,
        strategy: Strategy,
        context: StrategyContext,
        lookback_days: int,
    ) -> float:
        """
        Compute trailing return for a sub-strategy.

        Returns portfolio value at start_of_lookback vs end_of_lookback.
        """
        prices = context.prices

        if len(prices) < lookback_days + 1:
            return 0.0

        # Get price timeseries for this strategy
        try:
            strategy_prices = strategy.get_price_timeseries(context)
        except Exception as e:
            logger.debug(f"Could not get price timeseries for {strategy.name}: {e}")
            return 0.0

        # Slice to lookback window
        if len(strategy_prices) < lookback_days + 1:
            return 0.0

        start_price = strategy_prices.iloc[-lookback_days - 1]
        end_price = strategy_prices.iloc[-1]

        if start_price <= 0:
            return 0.0

        trailing_return = (end_price - start_price) / start_price
        return trailing_return

    def _resolve_to_symbols(
        self,
        weights: pd.Series,
        sub_strategy: Strategy,
        all_symbols: List[str],
    ) -> pd.Series:
        """
        Convert weight Series indexed by asset symbols or strategy names
        into one indexed by asset symbols.

        Adapted from MetaPortfolioStrategy._resolve_to_symbols.
        """
        result = pd.Series(0.0, index=all_symbols)

        # Fast path: all weight labels are already asset symbols
        if all(label in all_symbols for label in weights.index):
            for sym, w in weights.items():
                result[sym] = w
            total = result.sum()
            if total > 0:
                result /= total
            return result

        # Slow path: build name → symbol mapping by traversing underlying leaves
        name_to_symbols: dict[str, List[str]] = {}

        def _collect_leaves(strat: Strategy) -> None:
            underlying = getattr(strat, "underlying", None)
            if underlying is None:
                # Leaf node (AssetStrategy)
                for sym in strat.get_symbols():
                    name_to_symbols.setdefault(strat.name, []).append(sym)
            elif isinstance(underlying, list):
                for child in underlying:
                    _collect_leaves(child)
            else:
                _collect_leaves(underlying)

        _collect_leaves(sub_strategy)

        for idx_label, w in weights.items():
            if idx_label in all_symbols:
                result[idx_label] += w
            elif idx_label in name_to_symbols:
                syms = name_to_symbols[idx_label]
                for sym in syms:
                    if sym in result.index:
                        result[sym] += w / len(syms)

        total = result.sum()
        if total > 0:
            result /= total

        return result

    def _equal_weight_blend(self, prices: pd.DataFrame) -> pd.Series:
        """Equal-weight blend of all assets."""
        all_symbols = sorted(prices.columns)
        return pd.Series(1.0 / len(all_symbols), index=all_symbols)
