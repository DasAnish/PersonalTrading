"""
52-Week High Momentum portfolio allocation strategy.

Selects assets nearest their 52-week high and weights them by inverse
volatility (or equally). George & Hwang (2015) show this signal subsumes
trailing-return momentum through anchoring, not continuation.

Example:
    from strategies.core import AssetStrategy
    from strategies.fifty_two_week_high import FiftyTwoWeekHighStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
    ]
    strategy = FiftyTwoWeekHighStrategy(underlying=assets, top_n=2, weighting='equal')
"""

import pandas as pd
from typing import List, Literal
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class FiftyTwoWeekHighStrategy(AllocationStrategy):
    """
    52-Week High Momentum allocation strategy.

    1. Calculates price_t / rolling_max(price, lookback_days) for each asset
    2. Ranks assets by this ratio (descending: closest to 52-week high first)
    3. Selects top N performers
    4. Weights selected assets by inverse volatility or equally
    5. Unselected assets receive zero weight
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 3,
        lookback_days: int = 252,
        weighting: Literal["equal", "inverse_vol"] = "equal",
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            top_n: Number of top assets to select (default 3)
            lookback_days: Lookback for rolling max (default 252 = 1 year)
            weighting: Weight selected assets equally or by inverse volatility (default "equal")
            name: Display name
        """
        super().__init__(underlying, name=name or f"52-Week High Top-{top_n}")
        self.top_n = min(top_n, len(underlying))
        self.lookback_days = lookback_days
        self.weighting = weighting
        if weighting not in ("equal", "inverse_vol"):
            raise ValueError(
                f"weighting must be 'equal' or 'inverse_vol', got {weighting}"
            )

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"52-Week High requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for 52-week high: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        # Calculate 52-week high ratio: price_t / rolling_max(price, lookback_days)
        lookback_prices = prices.iloc[-self.lookback_days :]
        rolling_max = lookback_prices.max()
        current_prices = prices.iloc[-1]

        signal = current_prices / rolling_max
        signal = signal.replace([float("inf"), -float("inf")], 0)

        # Rank and select top N (highest ratio = closest to 52-week high)
        ranked = signal.sort_values(ascending=False)
        selected_symbols = ranked.index[: self.top_n].tolist()

        logger.debug(
            f"52-Week High rankings: {dict(ranked.round(4))}. "
            f"Selected: {selected_symbols}"
        )

        # Calculate weights for selected assets
        if self.weighting == "equal":
            selected_weights = pd.Series(
                1.0 / len(selected_symbols), index=selected_symbols
            )
        else:  # inverse_vol
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
