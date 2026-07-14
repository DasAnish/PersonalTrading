"""
Short-Term Reversal (1-Month) portfolio allocation strategy.

Ranks assets by trailing ~21-trading-day (1 month) total return and holds the bottom_n
(worst performers) equal-weighted. Jegadeesh (1990) 1-month cross-sectional reversal,
mean-reversion anomaly on short horizons, distinct from long-term overreaction.

Example:
    from strategies.core import AssetStrategy
    from strategies.short_term_reversal import ShortTermReversalStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    str = ShortTermReversalStrategy(underlying=assets, lookback_days=21, bottom_n=3)
"""

import pandas as pd
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class ShortTermReversalStrategy(AllocationStrategy):
    """
    Short-Term Reversal allocation strategy.

    1. Calculates each asset's total return over lookback_days (typically ~21 trading days)
    2. Ranks assets in ascending order (worst performers first)
    3. Selects bottom N performers
    4. Weights selected assets equally
    5. Unselected assets receive zero weight

    Note: Monthly rebalancing per engine default.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 21,
        bottom_n: int = 3,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookback_days: Lookback window for short-term return calc (default 21)
            bottom_n: Number of bottom (worst) assets to select (default 3)
            name: Display name
        """
        super().__init__(
            underlying, name=name or f"Short-Term Reversal ({lookback_days}d)"
        )
        self.lookback_days = lookback_days
        self.bottom_n = min(bottom_n, len(underlying))

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Short-Term Reversal requires at least 2 assets, received {len(prices.columns)}."
            )

        prices = prices.ffill(limit=3).dropna()

        # Adapt to available history. Use the longest window that fits.
        effective_lookback = min(self.lookback_days, len(prices))

        # Calculate short-term trailing returns over the effective lookback window
        lookback_prices = prices.iloc[-effective_lookback:]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1

        # Rank and select bottom N (worst performers first)
        ranked = trailing_returns.sort_values(ascending=True)
        selected_symbols = ranked.index[: self.bottom_n].tolist()

        logger.debug(
            f"Short-Term Reversal rankings: {dict(ranked.round(4))}. "
            f"Selected (bottom {self.bottom_n}): {selected_symbols}"
        )

        # Equal weight for selected assets
        selected_weights = pd.Series(
            1.0 / len(selected_symbols), index=selected_symbols
        )

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
