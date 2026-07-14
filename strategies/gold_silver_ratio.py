"""
Gold-Silver Ratio Mean Reversion strategy.

Two-asset tilt between gold (SGLN) and silver (SSLN) based on their price ratio.

Implementation
--------------
1. Compute daily gold/silver price ratio.
2. Calculate z-score: (ratio - trailing_mean) / trailing_std over lookback_days.
3. Tilt weights based on z-score:
   - High z (silver cheap): overweight silver
   - Low z (gold cheap): overweight gold
   - Neutral z: equal weight

Weight formula:
   w_silver = clip(0.5 + k*z, w_min, w_max)
   w_gold = 1 - w_silver

Long-only, always fully invested.

Parameters
----------
lookback_days : int
    Lookback for ratio mean and std (default 250).
k : float
    Z-score gain (default 0.15). Higher = more aggressive tilt.
w_min : float
    Minimum silver weight (default 0.2).
w_max : float
    Maximum silver weight (default 0.8).
gold_symbol : str
    Gold asset symbol (default 'SGLN').
silver_symbol : str
    Silver asset symbol (default 'SSLN').
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class GoldSilverRatioStrategy(AllocationStrategy):
    """
    Gold-Silver ratio mean reversion tilt.

    Tilts between gold and silver based on their price ratio z-score.
    High ratio (silver cheap) → overweight silver.
    Low ratio (gold cheap) → overweight gold.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 250,
        k: float = 0.15,
        w_min: float = 0.2,
        w_max: float = 0.8,
        gold_symbol: str = "SGLN",
        silver_symbol: str = "SSLN",
        name: str = None,
    ):
        """
        Args:
            underlying: List containing exactly 2 strategies (gold, silver).
            lookback_days: Lookback for ratio mean/std (default 250).
            k: Z-score gain factor (default 0.15).
            w_min: Minimum silver weight (default 0.2).
            w_max: Maximum silver weight (default 0.8).
            gold_symbol: Gold asset symbol (default 'SGLN').
            silver_symbol: Silver asset symbol (default 'SSLN').
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or "Gold-Silver Ratio Mean Reversion",
        )
        self.lookback_days = lookback_days
        self.k = k
        self.w_min = w_min
        self.w_max = w_max
        self.gold_symbol = gold_symbol
        self.silver_symbol = silver_symbol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Check that we have both gold and silver
        if self.gold_symbol not in prices.columns or self.silver_symbol not in prices.columns:
            logger.warning(
                f"Gold-Silver: missing symbols. Have {list(prices.columns)}, "
                f"need {self.gold_symbol} and {self.silver_symbol}"
            )
            return self._equal_weight(prices)

        # Compute gold/silver ratio
        gold_prices = prices[self.gold_symbol]
        silver_prices = prices[self.silver_symbol]
        ratio = gold_prices / silver_prices

        # Z-score over lookback window
        lookback_ratio = ratio.iloc[-self.lookback_days :]
        ratio_mean = lookback_ratio.mean()
        ratio_std = lookback_ratio.std()

        if ratio_std < 1e-10:
            # No volatility, fall back to equal weight
            logger.debug("Gold-Silver: ratio has zero volatility, equal weight")
            return self._equal_weight(prices)

        z_score = (ratio.iloc[-1] - ratio_mean) / ratio_std

        # Tilt weights based on z-score
        w_silver_target = 0.5 + self.k * z_score
        w_silver = np.clip(w_silver_target, self.w_min, self.w_max)
        w_gold = 1.0 - w_silver

        logger.debug(
            f"Gold-Silver: ratio={ratio.iloc[-1]:.4f}, mean={ratio_mean:.4f}, "
            f"std={ratio_std:.4f}, z={z_score:.4f}, "
            f"w_silver={w_silver:.4f}, w_gold={w_gold:.4f}"
        )

        # Build weight series
        symbol_to_name = self._build_name_map()
        gold_name = symbol_to_name.get(self.gold_symbol, self.gold_symbol)
        silver_name = symbol_to_name.get(self.silver_symbol, self.silver_symbol)

        all_index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=all_index)
        weights[gold_name] = w_gold
        weights[silver_name] = w_silver

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
