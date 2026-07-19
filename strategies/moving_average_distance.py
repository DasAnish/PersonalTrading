"""
Moving Average Distance (MAD) cross-sectional tilt.

Based on Avramov, Kaplanski & Subrahmanyam (2021), "Moving average
distance as a predictor of equity returns", Review of Financial Economics
39(2): the ratio of short- to long-run moving averages predicts
cross-sectional returns beyond momentum and 52-week-high, attributed to
anchoring-driven under-reaction. Long-only adaptation: hold the top-N
assets by MAD ratio (only while MAD > 1), inverse-vol weighted, with any
shortfall parked in defensive assets.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MovingAverageDistanceStrategy(AllocationStrategy):
    """
    Top-N MAD tilt.

    1. MAD_i = SMA(``short_days``) / SMA(``long_days``) per asset.
    2. Hold the ``top_n`` assets with the highest MAD, requiring MAD > 1.
    3. Inverse-vol weight (``vol_window_days``); each unfilled top-N slot's
       1/top_n weight share goes to the defensive assets present.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        short_days: int = 21,
        long_days: int = 200,
        top_n: int = 3,
        vol_window_days: int = 63,
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or f"MAD Top-{top_n}")
        self.short_days = short_days
        self.long_days = long_days
        self.top_n = top_n
        self.vol_window_days = vol_window_days
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 1:
            raise ValueError("MAD requires at least 1 asset.")

        min_required = max(self.long_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for MAD: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        mad = (
            prices.iloc[-self.short_days :].mean()
            / prices.iloc[-self.long_days :].mean()
        )
        eligible = mad[mad > 1.0].nlargest(self.top_n)
        n_filled = len(eligible)
        n_slots = min(self.top_n, len(prices.columns))

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        invested_share = n_filled / n_slots if n_slots else 0.0

        if n_filled:
            vol_returns = (
                prices.iloc[-self.vol_window_days :].pct_change().dropna()
            )
            vols = vol_returns.std()
            vols[vols == 0] = 1e-10
            inv_vol = 1.0 / vols[eligible.index]
            alloc = inv_vol / inv_vol.sum() * invested_share
            for symbol, w in alloc.items():
                weights[symbol_to_name.get(symbol, symbol)] += w

        shortfall = 1.0 - invested_share
        if shortfall > 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            targets = defensive or list(prices.columns)
            for symbol in targets:
                weights[symbol_to_name.get(symbol, symbol)] += shortfall / len(
                    targets
                )

        total = weights.sum()
        if total > 0:
            weights = weights / total
        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return max(self.long_days, self.vol_window_days) + 10
