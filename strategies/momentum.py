"""
Momentum Top-N portfolio allocation strategy.

Selects the top N assets by trailing return and weights them by inverse
volatility (risk parity among selected assets). Unselected assets get zero weight.

This is a concentrated momentum strategy — different from TrendFollowingStrategy
which uses EWMA signals across all assets.

Example:
    from strategies.core import AssetStrategy
    from strategies.momentum import MomentumTopNStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    momentum = MomentumTopNStrategy(underlying=assets, top_n=2)
"""

import pandas as pd
import numpy as np
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MomentumTopNStrategy(AllocationStrategy):
    """
    Momentum Top-N allocation strategy.

    1. Ranks all assets by trailing 12-month return
    2. Selects top N performers
    3. Weights selected assets by inverse volatility (equal risk contribution)
    4. Unselected assets receive zero weight
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 2,
        lookback_days: int = 252,
        name: str = None
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            top_n: Number of top assets to select (default 2)
            lookback_days: Lookback for momentum calculation (default 252 = 1 year)
            name: Display name
        """
        super().__init__(underlying, name=name or f"Momentum Top-{top_n}")
        self.top_n = min(top_n, len(underlying))
        self.lookback_days = lookback_days

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Momentum requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            logger.warning(
                f"Insufficient data ({len(prices)} < {min_required}). "
                "Falling back to equal weight."
            )
            n = len(prices.columns)
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            return pd.Series(np.ones(n) / n, index=index)

        prices = prices.ffill(limit=3).dropna()

        # Calculate trailing returns over lookback period
        lookback_prices = prices.iloc[-self.lookback_days:]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1

        # Rank and select top N
        ranked = trailing_returns.sort_values(ascending=False)
        selected_symbols = ranked.index[:self.top_n].tolist()

        logger.debug(
            f"Momentum rankings: {dict(ranked.round(4))}. "
            f"Selected: {selected_symbols}"
        )

        # Calculate inverse-volatility weights for selected assets
        returns = prices[selected_symbols].pct_change().dropna()
        vols = returns.std()
        vols[vols == 0] = 1e-10

        inv_vol = 1.0 / vols
        selected_weights = inv_vol / inv_vol.sum()

        # Build full weight vector (zeros for unselected)
        symbols = list(prices.columns)
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in symbols]

        weights = pd.Series(0.0, index=index)
        for symbol in selected_symbols:
            name = symbol_to_name.get(symbol, symbol)
            weights[name] = selected_weights[symbol]

        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
