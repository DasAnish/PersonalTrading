"""
Quality-Weighted Stability Tilt portfolio allocation strategy.

Weights assets proportional to a quality score (Calmar ratio or Sortino ratio)
that rewards steady compounding with shallow drawdowns, tilting toward assets
with strong risk-adjusted returns rather than merely low volatility.

Example:
    from strategies.core import AssetStrategy
    from strategies.quality_weighted_stability import QualityWeightedStabilityStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    quality = QualityWeightedStabilityStrategy(underlying=assets, lookback_days=252, quality_metric='calmar')
"""

import pandas as pd
import numpy as np
from typing import List, Literal
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class QualityWeightedStabilityStrategy(AllocationStrategy):
    """
    Quality-Weighted Stability Tilt allocation strategy.

    Two quality_metric modes:
    1. "calmar": score = trailing_return / abs(trailing_max_drawdown)
    2. "sortino": score = trailing_mean_return / downside_deviation
       (only negative-return periods contribute to denominator)

    Weights proportional to quality score (floored at zero), renormalized to sum to 1.
    Falls back to equal weight if all scores floor to zero.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        quality_metric: Literal["calmar", "sortino"] = "calmar",
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookback_days: Lookback for quality score calculation (default 252)
            quality_metric: "calmar" or "sortino" (default "calmar")
            name: Display name
        """
        super().__init__(underlying, name=name or f"Quality-Weighted ({quality_metric})")
        self.lookback_days = lookback_days
        self.quality_metric = quality_metric
        if quality_metric not in ("calmar", "sortino"):
            raise ValueError(f"quality_metric must be 'calmar' or 'sortino', got {quality_metric}")

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Quality-Weighted Stability requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for quality-weighted stability: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        # Use trailing lookback window
        lookback_prices = prices.iloc[-self.lookback_days :]
        returns = lookback_prices.pct_change().dropna()

        symbols = list(prices.columns)
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in symbols]

        if self.quality_metric == "calmar":
            weights = self._calculate_calmar_weights(lookback_prices, returns, symbols, index)
        else:  # sortino
            weights = self._calculate_sortino_weights(returns, symbols, index)

        return weights

    def _calculate_calmar_weights(
        self,
        lookback_prices: pd.DataFrame,
        returns: pd.DataFrame,
        symbols: list,
        index: list,
    ) -> pd.Series:
        """Weight by Calmar ratio: return / abs(max_drawdown), floored at zero."""
        # Calculate trailing return
        trailing_returns = (lookback_prices.iloc[-1] / lookback_prices.iloc[0]) - 1

        # Calculate max drawdown for each asset
        max_drawdowns = self._calculate_max_drawdowns(lookback_prices)

        # Calmar ratio: return / abs(max_drawdown)
        calmar_scores = pd.Series(0.0, index=symbols)
        for symbol in symbols:
            if max_drawdowns[symbol] != 0:
                calmar_score = trailing_returns[symbol] / abs(max_drawdowns[symbol])
                calmar_scores[symbol] = max(0, calmar_score)  # Floor at zero
            else:
                calmar_scores[symbol] = 0.0

        # If all scores floor to zero, fall back to equal weight
        if calmar_scores.sum() == 0:
            logger.warning(
                "All Calmar scores floored to zero. Falling back to equal weight."
            )
            weights_dict = {s: 1.0 / len(symbols) for s in symbols}
        else:
            weights_dict = (calmar_scores / calmar_scores.sum()).to_dict()

        weights = pd.Series(
            [weights_dict.get(s, 0.0) for s in symbols],
            index=index
        )

        logger.debug(
            f"Quality-Weighted (Calmar) scores: {dict(calmar_scores.round(4))}. "
            f"Weights: {dict(weights.round(4))}"
        )

        return weights

    def _calculate_sortino_weights(
        self,
        returns: pd.DataFrame,
        symbols: list,
        index: list,
    ) -> pd.Series:
        """Weight by Sortino ratio: mean_return / downside_deviation, floored at zero."""
        sortino_scores = pd.Series(0.0, index=symbols)

        for symbol in symbols:
            asset_returns = returns[symbol].dropna()
            mean_return = asset_returns.mean()

            # Downside deviation: std of only negative returns
            negative_returns = asset_returns[asset_returns < 0]
            if len(negative_returns) > 0:
                downside_deviation = negative_returns.std()
            else:
                downside_deviation = 1e-10  # Avoid division by zero

            if downside_deviation > 0:
                sortino_score = mean_return / downside_deviation
                sortino_scores[symbol] = max(0, sortino_score)  # Floor at zero
            else:
                sortino_scores[symbol] = 0.0

        # If all scores floor to zero, fall back to equal weight
        if sortino_scores.sum() == 0:
            logger.warning(
                "All Sortino scores floored to zero. Falling back to equal weight."
            )
            weights_dict = {s: 1.0 / len(symbols) for s in symbols}
        else:
            weights_dict = (sortino_scores / sortino_scores.sum()).to_dict()

        weights = pd.Series(
            [weights_dict.get(s, 0.0) for s in symbols],
            index=index
        )

        logger.debug(
            f"Quality-Weighted (Sortino) scores: {dict(sortino_scores.round(4))}. "
            f"Weights: {dict(weights.round(4))}"
        )

        return weights

    def _calculate_max_drawdowns(self, lookback_prices: pd.DataFrame) -> pd.Series:
        """Calculate maximum drawdown for each asset."""
        max_drawdowns = {}
        for symbol in lookback_prices.columns:
            prices = lookback_prices[symbol].values
            cumulative_max = np.maximum.accumulate(prices)
            drawdown = (prices - cumulative_max) / cumulative_max
            max_drawdown = drawdown.min()
            max_drawdowns[symbol] = max_drawdown
        return pd.Series(max_drawdowns)

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
