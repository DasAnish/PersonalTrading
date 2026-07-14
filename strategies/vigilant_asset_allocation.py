"""
Vigilant Asset Allocation strategy (Keller & Keuning, 2017).

Binary regime detection using offensive asset breadth:

1. **Offensive Pool**: Growth assets (equities, gold, commodities).
   Compute 13612W momentum (1m, 3m, 6m, 12m) for each.

2. **Defensive Pool**: Safe assets (bonds).

3. **Breadth Gate**: Count offensive assets in downtrend (momentum <= 0).
   If count >= breadth_threshold: DEFENSIVE mode (hold 100% single best defensive).
   Else: OFFENSIVE mode (hold top_n offensive assets, equal-weight).

Parameters
----------
offensive_assets : list of str
    Asset symbols for growth allocation (e.g. ['VUSA', 'EQQQ', 'IWRD', 'IMEU', 'IIND', 'SGLN', 'COMM', 'BRNT']).
defensive_assets : list of str
    Asset symbols for safe allocation (e.g. ['VUTY', 'AGGU']).
top_n : int
    Number of offensive assets to hold in offensive mode (default 1).
breadth_threshold : int
    Number of weak offensive assets to trigger defensive mode (default 1).
lookback_days : int
    Lookback for 13612W momentum calculation (default 252 = 1 year).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class VigilantAssetAllocationStrategy(AllocationStrategy):
    """
    Vigilant Asset Allocation using binary breadth gate on offensive universe.

    When many offensive assets are in downtrend (momentum <= 0), allocate 100%
    to the single best defensive asset. Otherwise, allocate equally across
    top momentum offensive assets.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        offensive_assets: List[str] = None,
        defensive_assets: List[str] = None,
        top_n: int = 1,
        breadth_threshold: int = 1,
        lookback_days: int = 252,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
            offensive_assets: Symbols for growth allocation (e.g. ['VUSA', 'EQQQ', ...]).
            defensive_assets: Symbols for safe allocation (e.g. ['VUTY', 'AGGU']).
            top_n: Number of offensive assets to hold in offensive mode (default 1).
            breadth_threshold: Count of weak offensive assets to trigger defensive mode (default 1).
            lookback_days: Lookback for momentum (default 252).
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Vigilant Asset Allocation ({lookback_days}d)",
        )
        self.offensive_assets = offensive_assets or []
        self.defensive_assets = defensive_assets or []
        self.top_n = top_n
        self.breadth_threshold = breadth_threshold
        self.lookback_days = lookback_days

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Build symbol-to-name mapping
        symbol_to_name = self._build_name_map()
        all_index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=all_index)

        # Step 1: Compute 13612W momentum for offensive assets
        offensive_momentum = self._compute_13612w_momentum(prices)

        # Count offensive assets in downtrend (momentum <= 0)
        weak_count = sum(
            1
            for sym in self.offensive_assets
            if sym in offensive_momentum and offensive_momentum[sym] <= 0
        )

        logger.debug(
            f"VAA: offensive momentum {dict(offensive_momentum)}. "
            f"weak_count={weak_count}, breadth_threshold={self.breadth_threshold}"
        )

        # Step 2: Binary breadth gate
        if weak_count >= self.breadth_threshold:
            # DEFENSIVE mode: hold 100% of single best defensive asset
            logger.debug(
                f"VAA: DEFENSIVE mode triggered (weak_count {weak_count} >= threshold {self.breadth_threshold})"
            )

            if self.defensive_assets:
                # Compute momentum for defensive assets
                defensive_momentum = {
                    sym: offensive_momentum.get(sym, self._momentum_13612w(prices, sym))
                    for sym in self.defensive_assets
                    if sym in prices.columns
                }

                if defensive_momentum:
                    # Select best defensive asset by momentum
                    best_defensive = max(
                        defensive_momentum.items(), key=lambda x: x[1]
                    )[0]
                    if best_defensive in symbol_to_name:
                        name = symbol_to_name[best_defensive]
                        weights[name] = 1.0
                        logger.debug(f"VAA: holding 100% {best_defensive}")

        else:
            # OFFENSIVE mode: hold top_n offensive assets, equal-weight
            logger.debug(
                f"VAA: OFFENSIVE mode (weak_count {weak_count} < threshold {self.breadth_threshold})"
            )

            if self.offensive_assets:
                # Compute momentum for offensive assets
                risky_momentum = {
                    sym: offensive_momentum.get(sym, self._momentum_13612w(prices, sym))
                    for sym in self.offensive_assets
                    if sym in prices.columns
                }

                if risky_momentum:
                    # Rank by momentum and select top_n
                    ranked = sorted(
                        risky_momentum.items(), key=lambda x: x[1], reverse=True
                    )
                    top_offensive = [sym for sym, _ in ranked[: self.top_n]]

                    per_asset_weight = (
                        1.0 / len(top_offensive) if top_offensive else 0.0
                    )
                    for symbol in top_offensive:
                        if symbol in symbol_to_name:
                            name = symbol_to_name[symbol]
                            weights[name] = per_asset_weight

                    logger.debug(
                        f"VAA: offensive ranked {dict(risky_momentum)}. "
                        f"Top {self.top_n}: {top_offensive}, per_asset={per_asset_weight:.4f}"
                    )

        return weights

    def _compute_13612w_momentum(self, prices: pd.DataFrame) -> dict:
        """Compute 13612W momentum for all available assets."""
        # Approximate months as trading days: 1m=21, 3m=63, 6m=126, 12m=252
        lookbacks = [21, 63, 126, 252]
        weights_mom = [12, 4, 2, 1]

        result = {}
        for symbol in prices.columns:
            momentum_components = []
            for lookback, weight in zip(lookbacks, weights_mom):
                if len(prices) >= lookback + 1:
                    ret = prices[symbol].iloc[-1] / prices[symbol].iloc[-lookback - 1] - 1
                    momentum_components.append(weight * ret)
            if momentum_components:
                weighted_mom = sum(momentum_components) / sum(weights_mom)
                result[symbol] = weighted_mom

        return result

    def _momentum_13612w(self, prices: pd.DataFrame, symbol: str) -> float:
        """Compute 13612W momentum for a single asset."""
        lookbacks = [21, 63, 126, 252]
        weights_mom = [12, 4, 2, 1]

        if symbol not in prices.columns:
            return 0.0

        momentum_components = []
        for lookback, weight in zip(lookbacks, weights_mom):
            if len(prices) >= lookback + 1:
                ret = prices[symbol].iloc[-1] / prices[symbol].iloc[-lookback - 1] - 1
                momentum_components.append(weight * ret)

        if momentum_components:
            return sum(momentum_components) / sum(weights_mom)
        return 0.0

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
