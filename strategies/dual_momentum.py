"""
Dual Momentum strategy (Gary Antonacci).

Combines two momentum filters before investing:

1. **Relative Momentum**: Rank assets by trailing return.  Only consider
   the top-ranked assets.
2. **Absolute Momentum**: Check whether each selected asset's own trailing
   return is positive (above a threshold).  If not, treat that allocation
   as "cash" (held as a zero-weight position).

The dual filter is designed to:
- Participate in the best-performing assets during up-trends (relative)
- Sidestep assets that are in absolute downtrends (absolute / trend filter)

With only four assets (VUSA, SSLN, SGLN, IWRD), the classic implementation
selects top-N by relative momentum, then applies the absolute filter.
Filtered-out allocations remain as cash (not redistributed), so the
portfolio can be partially invested.

Parameters
----------
top_n : int
    Number of top assets to consider by relative momentum (default 2).
lookback_days : int
    Return lookback for both momentum filters (default 252 = 1 year).
abs_threshold : float
    Minimum trailing return for absolute momentum filter (default 0.0 = any
    positive return passes).  Set > 0 to require a minimum positive return.
cash_redistribute : bool
    If True, redistribute filtered-out weights to remaining assets instead
    of leaving as cash.  Default False (Antonacci's original: hold cash).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class DualMomentumStrategy(AllocationStrategy):
    """
    Dual momentum (relative + absolute) allocation strategy.

    Relative momentum selects the top_n assets; absolute momentum filters
    out those in a downtrend.  Filtered assets become cash drag (zero weight)
    unless cash_redistribute=True.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 2,
        lookback_days: int = 252,
        abs_threshold: float = 0.0,
        cash_redistribute: bool = False,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Dual Momentum (top_{top_n}, {lookback_days}d)",
        )
        self.top_n = min(top_n, len(underlying))
        self.lookback_days = lookback_days
        self.abs_threshold = abs_threshold
        self.cash_redistribute = cash_redistribute

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Step 1: Relative momentum — trailing returns over lookback
        lookback_prices = prices.iloc[-self.lookback_days:]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1

        # Rank descending; select top_n
        ranked = trailing_returns.sort_values(ascending=False)
        candidates = ranked.index[:self.top_n].tolist()

        logger.debug(
            f"DualMomentum rankings: {dict(ranked.round(4))}. "
            f"Candidates: {candidates}"
        )

        # Step 2: Absolute momentum — keep only those with return > threshold
        passed = [sym for sym in candidates if trailing_returns[sym] > self.abs_threshold]

        logger.debug(
            f"DualMomentum after absolute filter (threshold={self.abs_threshold}): {passed}"
        )

        # Step 3: Build weights
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        if not passed:
            # All filtered out — hold cash (all zeros) or equal weight fallback
            logger.debug("DualMomentum: all candidates filtered, holding cash")
            return weights

        # Inverse-volatility weighting among passing assets
        returns = prices[passed].pct_change().dropna()
        vols = returns.std()
        vols[vols == 0] = 1e-10

        if self.cash_redistribute:
            inv_vol = 1.0 / vols
            selected_weights = inv_vol / inv_vol.sum()
        else:
            # Equal inverse-vol weights, but don't redistribute filtered cash
            inv_vol = 1.0 / vols
            # Normalise only among passing assets (cash drag preserved)
            selected_weights = inv_vol / inv_vol.sum()

        for symbol in passed:
            name = symbol_to_name.get(symbol, symbol)
            weights[name] = selected_weights[symbol]

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
