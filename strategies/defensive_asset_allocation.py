"""
Defensive Asset Allocation strategy (Keller & Keuning, 2018).

Two-stage approach using canary assets to signal regime:

1. **Canary Assets**: A pool of risk-sensitive assets (e.g. EM equity + bonds).
   Compute weighted 13612W momentum (1m, 3m, 6m, 12m) for each.
   Count how many are in downtrend (momentum <= 0). Call this b.

2. **Regime Detection**: cash_fraction = min(b / b_max, 1).
   When many canary assets are weak, shift to cash. Otherwise, invest in risky.

3. **Asset Allocation**:
   - risky_fraction = 1 - cash_fraction goes to top_n risky assets (equal-weight).
   - cash_fraction goes to safe asset (e.g. bonds).

Parameters
----------
canary_assets : list of str
    Asset symbols to monitor for regime (e.g. ['IIND', 'AGGU']).
risky_assets : list of str
    Asset symbols for growth allocation (e.g. ['VUSA', 'IWRD', 'SGLN']).
safe_asset : str
    Single safe asset symbol (e.g. 'VUTY').
top_n : int
    Number of risky assets to allocate to when in growth regime (default 4).
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


class DefensiveAssetAllocationStrategy(AllocationStrategy):
    """
    Defensive Asset Allocation using canary breadth to signal regime.

    Canary assets detect weakness; when many are in downtrend (momentum <= 0),
    allocate to cash (safe asset). Otherwise, invest in top momentum risky assets.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        canary_assets: List[str] = None,
        risky_assets: List[str] = None,
        safe_asset: str = None,
        top_n: int = 4,
        lookback_days: int = 252,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
            canary_assets: Symbols to monitor for regime (e.g. ['IIND', 'AGGU']).
            risky_assets: Symbols for growth allocation when not defensive.
            safe_asset: Single safe symbol (e.g. 'VUTY').
            top_n: Number of risky assets to hold in growth mode (default 4).
            lookback_days: Lookback for momentum (default 252).
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Defensive Asset Allocation ({lookback_days}d)",
        )
        self.canary_assets = canary_assets or []
        self.risky_assets = risky_assets or []
        self.safe_asset = safe_asset
        self.top_n = top_n
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

        # Step 1: Compute 13612W momentum for canary assets
        canary_momentum = self._compute_13612w_momentum(prices)

        # Count canary assets in downtrend (momentum <= 0)
        b = sum(1 for sym in self.canary_assets if sym in canary_momentum and canary_momentum[sym] <= 0)
        b_max = len(self.canary_assets) if self.canary_assets else 1
        cash_fraction = min(b / b_max, 1.0) if b_max > 0 else 0.0

        logger.debug(
            f"DAA: canary momentum {dict(canary_momentum)}. "
            f"b={b}/{b_max}, cash_fraction={cash_fraction:.4f}"
        )

        # Step 2: Allocate to safe asset
        if self.safe_asset and self.safe_asset in symbol_to_name:
            safe_name = symbol_to_name[self.safe_asset]
            weights[safe_name] = cash_fraction

        # Step 3: Allocate risky_fraction to top risky assets
        risky_fraction = 1.0 - cash_fraction
        if risky_fraction > 1e-6 and self.risky_assets:
            # Compute momentum for risky assets
            risky_momentum = {
                sym: canary_momentum.get(sym, self._momentum_13612w(prices, sym))
                for sym in self.risky_assets
                if sym in prices.columns
            }

            if risky_momentum:
                # Rank by momentum and select top_n
                ranked = sorted(
                    risky_momentum.items(), key=lambda x: x[1], reverse=True
                )
                top_risky = [sym for sym, _ in ranked[:self.top_n]]

                per_asset_weight = risky_fraction / len(top_risky) if top_risky else 0.0
                for symbol in top_risky:
                    if symbol in symbol_to_name:
                        name = symbol_to_name[symbol]
                        weights[name] = per_asset_weight

                logger.debug(
                    f"DAA: risky ranked {dict(risky_momentum)}. "
                    f"Top {self.top_n}: {top_risky}, per_asset={per_asset_weight:.4f}"
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
