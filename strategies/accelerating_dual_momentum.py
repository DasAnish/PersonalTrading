"""
Accelerating Dual Momentum allocation strategy.

Based on Ludlow & Hanly (2018). Modifies classic dual momentum by scoring
each asset on a multi-lookback momentum measure — the average of its 1-, 3-,
and 6-month total returns — rather than a single 12-month lookback.

Averaging several short lookbacks makes the score "accelerate": it responds
faster to turning points than a 12-month signal, capturing regime shifts
earlier while multi-window averaging damps whipsaw.

Combined with an absolute-momentum overlay: hold the top-N assets if their
score is positive, else rotate freed weight to the defensive asset (VUTY).

Rebalance: Monthly. Portfolio construction: long-only — for each asset,
average its trailing 1m/3m/6m returns; rank by this acceleration score;
apply absolute-momentum filter (score > threshold); if passed, hold top_n
equal-weighted; if failed, allocate to defensive asset.

Key parameters:
- lookbacks: list of days for multi-window average (default [21,63,126])
- top_n: number of assets to hold when absolute momentum passes (default 1)
- abs_threshold: minimum score to pass absolute filter (default 0.0)
- defensive_asset: symbol to hold when absolute momentum fails (default 'VUTY')
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class AcceleratingDualMomentumStrategy(AllocationStrategy):
    """
    Accelerating Dual Momentum allocation strategy.

    Combines multi-lookback relative momentum (average of 1m/3m/6m returns)
    with absolute momentum filter (score > threshold). Holds top-N if
    absolute momentum passes, else rotates to defensive asset.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookbacks: Optional[List[int]] = None,
        top_n: int = 1,
        abs_threshold: float = 0.0,
        defensive_asset: str = "VUTY",
        name: Optional[str] = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookbacks: Days for multi-window momentum (default [21,63,126] = 1m/3m/6m)
            top_n: Number of top assets to hold (default 1)
            abs_threshold: Minimum score to pass absolute filter (default 0.0)
            defensive_asset: Symbol to hold when absolute momentum fails (default 'VUTY')
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Accelerating Dual Momentum (top_{top_n})",
        )
        self.lookbacks = lookbacks if lookbacks is not None else [21, 63, 126]
        self.top_n = min(top_n, len(underlying))
        self.abs_threshold = abs_threshold
        self.defensive_asset = defensive_asset

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Accelerating Dual Momentum requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, max(self.lookbacks))
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Step 1: Calculate acceleration score (average of multi-lookback returns)
        scores = {}
        for symbol in prices.columns:
            try:
                score = self._acceleration_score(prices[symbol])
                scores[symbol] = score
            except Exception as e:
                logger.debug(f"Could not compute acceleration score for {symbol}: {e}")
                scores[symbol] = np.nan

        # Filter valid scores
        valid_scores = {k: v for k, v in scores.items() if not np.isnan(v)}

        if not valid_scores:
            logger.warning("No valid acceleration scores; using equal-weight fallback")
            return self._equal_weight(prices)

        # Step 2: Relative momentum — rank by score
        ranked = sorted(valid_scores.items(), key=lambda x: x[1], reverse=True)
        candidates = [symbol for symbol, _ in ranked[: self.top_n]]

        logger.debug(
            f"ADM rankings: {dict(ranked)}. "
            f"Candidates: {candidates}"
        )

        # Step 3: Absolute momentum — keep only those with score > threshold
        passed = [sym for sym in candidates if valid_scores[sym] > self.abs_threshold]

        logger.debug(
            f"ADM after absolute filter (threshold={self.abs_threshold}): {passed}"
        )

        # Step 4: Build weights
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        if passed:
            # Hold top_n with equal weight among passed assets
            equal_weight_value = 1.0 / len(passed)
            for symbol in passed:
                name = symbol_to_name.get(symbol, symbol)
                weights[name] = equal_weight_value
        else:
            # All filtered out — allocate to defensive asset
            if self.defensive_asset in prices.columns:
                name = symbol_to_name.get(self.defensive_asset, self.defensive_asset)
                weights[name] = 1.0
            else:
                logger.warning(
                    f"Defensive asset {self.defensive_asset} not found; using equal-weight fallback"
                )
                return self._equal_weight(prices)

        return weights

    def _acceleration_score(self, asset_prices: pd.Series) -> float:
        """
        Calculate acceleration score for a single asset.

        Average of trailing returns over multiple lookback windows (1m/3m/6m).
        """
        max_lookback = max(self.lookbacks)

        if len(asset_prices) < max_lookback:
            return np.nan

        prices = asset_prices.ffill(limit=3).dropna()

        if len(prices) < max_lookback:
            return np.nan

        # Calculate returns for each lookback
        returns = []
        for lookback in self.lookbacks:
            if len(prices) >= lookback:
                ret = prices.iloc[-1] / prices.iloc[-lookback] - 1
                returns.append(ret)

        if not returns:
            return np.nan

        # Average of all lookback returns
        score = np.mean(returns)

        return score

    def get_strategy_lookback(self) -> int:
        return max(self.lookbacks)

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
