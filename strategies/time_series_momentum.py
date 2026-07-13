"""
Time-Series Momentum strategy using vol-scaled trailing returns.

Based on Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum".
Selects assets with positive trailing returns, weights by inverse volatility.

Example:
    from strategies.core import AssetStrategy
    from strategies.time_series_momentum import TimeSeriesMomentumStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    tsm = TimeSeriesMomentumStrategy(underlying=assets, lookback_months=12)
"""

import pandas as pd
import numpy as np
from typing import List
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class TimeSeriesMomentumStrategy(AllocationStrategy):
    """
    Time-Series Momentum allocation strategy.

    1. For each asset, compute the sign of trailing lookback_months return
    2. Assets with positive return: select (long-only)
    3. Assets with non-positive return: zero weight
    4. Weight selected assets by inverse realized volatility
    5. Normalize weights to sum 1
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_months: int = 12,
        vol_window_days: int = 60,
        target_vol: float = None,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookback_months: Lookback for signal (default 12 months)
            vol_window_days: Days for realized volatility estimate (default 60)
            target_vol: Optional portfolio vol target for scaling (default None)
            name: Display name
        """
        super().__init__(underlying, name=name or f"Time-Series Momentum ({lookback_months}m)")
        self.lookback_months = lookback_months
        self.vol_window_days = vol_window_days
        self.target_vol = target_vol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 1:
            raise ValueError("Time-Series Momentum requires at least 1 asset.")

        # Convert months to trading days (roughly 21 days/month)
        lookback_days = max(int(self.lookback_months * 21), 30)
        min_required = max(lookback_days, self.vol_window_days) + 20

        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for time-series momentum: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        # Step 1: Calculate trailing returns over lookback period
        lookback_prices = prices.iloc[-lookback_days:]
        trailing_returns = lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1

        # Step 2: Identify positive-return assets (long signal)
        positive_mask = trailing_returns > 0
        selected_symbols = trailing_returns[positive_mask].index.tolist()

        if not selected_symbols:
            # No positive signals, equal weight fallback
            logger.warning(
                "Time-Series Momentum: no positive signals, using equal weight fallback."
            )
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            equal_weight = 1.0 / len(symbols) if symbols else 1.0
            return pd.Series(equal_weight, index=index)

        logger.debug(
            f"Time-Series Momentum: {len(selected_symbols)}/{len(trailing_returns)} "
            f"assets have positive {self.lookback_months}m return. "
            f"Selected: {selected_symbols}"
        )

        # Step 3: Calculate realized volatility over vol_window_days
        vol_prices = prices.iloc[-self.vol_window_days:]
        returns = vol_prices.pct_change().dropna()
        vols = returns.std()
        vols[vols == 0] = 1e-10

        # Step 4: Weight selected assets by inverse volatility
        selected_vols = vols[selected_symbols]
        inv_vol = 1.0 / selected_vols
        selected_weights = inv_vol / inv_vol.sum()

        # Optional: scale to target vol if specified
        if self.target_vol is not None and len(returns) > 0:
            port_vol = np.sqrt(
                (selected_weights ** 2).dot(selected_vols.values ** 2)
            )
            if port_vol > 0:
                selected_weights = selected_weights * (self.target_vol / port_vol)

        # Step 5: Build full weight vector (zeros for non-selected)
        symbols = list(prices.columns)
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in symbols]

        weights = pd.Series(0.0, index=index)
        for symbol in selected_symbols:
            name = symbol_to_name.get(symbol, symbol)
            weights[name] = selected_weights[symbol]

        # Normalize to sum 1
        if weights.sum() > 0:
            weights = weights / weights.sum()

        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        lookback_days = max(int(self.lookback_months * 21), 30)
        return max(lookback_days, self.vol_window_days) + 20
