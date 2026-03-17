"""
Protective Asset Allocation strategy (Keller & Keuning).

Combines trend-following with defensive positioning:

1. For each risky asset, compute SMA (simple moving average) over lookback_days.
2. Count how many risky assets are above their SMA (call this n_good).
3. Compute a "protection factor": pf = (N - n_good) / N, ranges 0 to 1.
4. Allocate (1 - pf) weight equally across risky assets above their SMA.
5. Allocate pf weight to the safe asset (bonds, last asset in underlying list).
6. If no risky assets pass, allocate 100% to safe asset.

The strategy becomes more defensive (more weight to bonds) as fewer assets are
above their trends. This provides automatic risk reduction in downturns.

Parameters
----------
lookback_days : int
    Lookback period for SMA calculation (default 252 = 1 year).
min_weight : float
    Minimum weight per passing risky asset (default 0.0). Currently unused.

Example
-------
    from strategies.core import AssetStrategy
    from strategies.protective_asset_allocation import ProtectiveAssetAllocationStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),  # Risky
        AssetStrategy('SSLN', currency='GBP'),  # Risky
        AssetStrategy('SGLN', currency='GBP'),  # Risky
        AssetStrategy('IWRD', currency='GBP'),  # Risky
        AssetStrategy('VUTY', currency='GBP'),  # Safe (bonds)
    ]
    paa = ProtectiveAssetAllocationStrategy(underlying=assets, lookback_days=252)
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class ProtectiveAssetAllocationStrategy(AllocationStrategy):
    """
    Protective Asset Allocation (PAA) strategy.

    Allocates defensively by shifting weight from risky assets to safe assets
    based on how many risky assets are above their trend (SMA).

    The last asset in the underlying list is treated as the safe asset (bonds).
    All other assets are treated as risky assets.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        min_weight: float = 0.0,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
                       Last asset is treated as safe (bonds).
            lookback_days: Lookback days for SMA calculation (default 252).
            min_weight: Minimum weight per passing risky asset (default 0.0).
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Protective Asset Allocation ({lookback_days}d)",
        )
        self.lookback_days = lookback_days
        self.min_weight = min_weight

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Identify safe asset (last symbol) and risky assets (all others)
        symbols = list(prices.columns)
        if len(symbols) < 2:
            raise ValueError(
                f"Protective Asset Allocation requires at least 2 assets "
                f"(risky + safe), received {len(symbols)}."
            )

        safe_symbol = symbols[-1]
        risky_symbols = symbols[:-1]

        logger.debug(
            f"PAA: {len(risky_symbols)} risky assets {risky_symbols}, "
            f"safe asset {safe_symbol}"
        )

        # Step 1: For each risky asset, check if above its SMA
        lookback_prices = prices.iloc[-self.lookback_days :]
        sma = lookback_prices.mean()

        current_prices = prices.iloc[-1]
        passed = [
            sym for sym in risky_symbols if current_prices[sym] > sma[sym]
        ]

        n_good = len(passed)
        n_risky = len(risky_symbols)
        protection_factor = (n_risky - n_good) / n_risky if n_risky > 0 else 1.0

        logger.debug(
            f"PAA: {n_good}/{n_risky} risky assets above SMA. "
            f"Protection factor: {protection_factor:.4f}. "
            f"Passed: {passed}"
        )

        # Step 2: Calculate weights
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        # Allocate to safe asset
        safe_name = symbol_to_name.get(safe_symbol, safe_symbol)
        weights[safe_name] = protection_factor

        # Allocate to passed risky assets
        if passed:
            risky_weight = 1.0 - protection_factor
            per_asset_weight = risky_weight / len(passed)

            for symbol in passed:
                name = symbol_to_name.get(symbol, symbol)
                weights[name] = per_asset_weight
        else:
            # All risky assets filtered out — 100% to safe
            logger.debug(
                "PAA: no risky assets above SMA, holding 100% safe asset"
            )
            weights[safe_name] = 1.0

        return weights

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
