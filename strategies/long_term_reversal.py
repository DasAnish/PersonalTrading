"""
Long-Term Reversal (Overreaction) portfolio allocation strategy.

Ranks assets by trailing 36-60 month total return and holds the bottom_n
(worst performers) equal-weighted. De Bondt & Thaler-style long-horizon
contrarian signal, economically distinct from short-horizon (20-day)
mean reversion.

Example:
    from strategies.core import AssetStrategy
    from strategies.long_term_reversal import LongTermReversalStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    ltr = LongTermReversalStrategy(underlying=assets, formation_window_months=48, bottom_n=4)
"""

import pandas as pd
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class LongTermReversalStrategy(AllocationStrategy):
    """
    Long-Term Reversal allocation strategy.

    1. Calculates each asset's total return over formation_window_months
    2. Ranks assets in ascending order (worst performers first)
    3. Selects bottom N performers
    4. Weights selected assets equally
    5. Unselected assets receive zero weight

    Note: Source paper (De Bondt & Thaler, 1985) uses annual rebalancing.
    This implementation uses monthly rebalancing per engine default; to achieve
    annual rebalancing, set rebalance_frequency='annual' when running the backtest.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        formation_window_months: int = 48,
        bottom_n: int = 4,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            formation_window_months: Lookback for long-term return calc (default 48)
            bottom_n: Number of bottom (worst) assets to select (default 4)
            name: Display name
        """
        super().__init__(underlying, name=name or f"Long-Term Reversal ({formation_window_months}m)")
        self.formation_window_months = formation_window_months
        self.bottom_n = min(bottom_n, len(underlying))

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Long-Term Reversal requires at least 2 assets, received {len(prices.columns)}."
            )

        # Convert months to trading days (~21 trading days per month)
        lookback_days = self.formation_window_months * 21

        min_required = max(30, lookback_days)
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for long-term reversal: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        # Calculate long-term trailing returns over formation window
        lookback_prices = prices.iloc[-lookback_days :]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1

        # Rank and select bottom N (worst performers first)
        ranked = trailing_returns.sort_values(ascending=True)
        selected_symbols = ranked.index[: self.bottom_n].tolist()

        logger.debug(
            f"Long-Term Reversal rankings: {dict(ranked.round(4))}. "
            f"Selected (bottom {self.bottom_n}): {selected_symbols}"
        )

        # Equal weight for selected assets
        selected_weights = pd.Series(1.0 / len(selected_symbols), index=selected_symbols)

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
        return self.formation_window_months * 21
