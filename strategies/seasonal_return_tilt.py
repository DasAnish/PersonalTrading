"""
Seasonal Return Tilt strategy for commodity return seasonality.

Based on "Return seasonality in commodity futures"
(International Review of Economics & Finance, 2024).

Ranks commodities each month by their historical same-month average return
over trailing years, then overweights the highest-expected performers.

Example:
    from strategies.core import AssetStrategy
    from strategies.seasonal_return_tilt import SeasonalReturnTiltStrategy

    commodities = [
        AssetStrategy('SGLN', currency='GBP'),  # Gold
        AssetStrategy('SSLN', currency='GBP'),  # Silver
        AssetStrategy('BRNT', currency='GBP'),  # Brent
        AssetStrategy('CRUD', currency='GBP'),  # WTI
    ]
    seasonal = SeasonalReturnTiltStrategy(underlying=commodities, top_n=2)
"""

import pandas as pd
import numpy as np
from typing import List
from datetime import datetime
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class SeasonalReturnTiltStrategy(AllocationStrategy):
    """
    Seasonal Return Tilt allocation strategy for commodities.

    1. For each asset, compute the mean return in the coming calendar month
       over a trailing historical window
    2. Rank assets by expected seasonal return
    3. Select top N and equal-weight
    4. Unselected assets receive zero weight
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 2,
        history_years: int = 10,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets (typically commodities)
            top_n: Number of top assets to select (default 2)
            history_years: Years of history to compute seasonal mean (default 10)
            name: Display name
        """
        super().__init__(underlying, name=name or f"Seasonal Return Tilt (top-{top_n})")
        self.top_n = min(top_n, len(underlying))
        self.history_years = history_years

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 1:
            raise ValueError("Seasonal Return Tilt requires at least 1 asset.")

        # Ensure we have enough history (in trading days, roughly 252 per year)
        min_required = max(self.history_years * 252, 500)
        if len(prices) < min_required:
            logger.warning(
                f"Seasonal Return Tilt: only {len(prices)} data points, "
                f"need {min_required} for {self.history_years}-year seasonal mean. "
                f"Using equal weight fallback."
            )
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            equal_weight = 1.0 / len(symbols) if symbols else 1.0
            return pd.Series(equal_weight, index=index)

        prices = prices.ffill(limit=3).dropna()

        # Step 1: Compute monthly returns for each asset
        prices_with_date = prices.copy()
        prices_with_date.index = pd.to_datetime(prices_with_date.index)

        # Resample to month-end and compute monthly returns
        monthly_prices = prices_with_date.resample("ME").last()
        monthly_returns = monthly_prices.pct_change().dropna()

        if len(monthly_returns) < 12:
            # Not enough monthly data, fallback
            logger.warning(
                f"Seasonal Return Tilt: only {len(monthly_returns)} monthly observations. "
                f"Using equal weight fallback."
            )
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            equal_weight = 1.0 / len(symbols) if symbols else 1.0
            return pd.Series(equal_weight, index=index)

        # Step 2: Extract calendar month from each observation
        monthly_returns["month"] = monthly_returns.index.month

        # Step 3: Compute expected return for coming month
        # Current month (at end of context.prices)
        current_month = context.current_date.month

        # Next month for coming-month forecast
        next_month = (current_month % 12) + 1

        # Compute mean return for next_month across all historical years
        seasonal_mean = monthly_returns[monthly_returns["month"] == next_month].drop(
            columns="month"
        ).mean()

        if seasonal_mean.empty or seasonal_mean.isna().all():
            # No historical data for next month, fallback
            logger.warning(
                f"Seasonal Return Tilt: no historical data for month {next_month}. "
                f"Using equal weight fallback."
            )
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            equal_weight = 1.0 / len(symbols) if symbols else 1.0
            return pd.Series(equal_weight, index=index)

        # Step 4: Rank and select top N
        seasonal_mean = seasonal_mean.dropna()
        ranked = seasonal_mean.sort_values(ascending=False)
        selected_symbols = ranked.index[: self.top_n].tolist()

        logger.debug(
            f"Seasonal Return Tilt: month={current_month}, "
            f"coming={next_month}, expected returns={dict(ranked.round(4))}. "
            f"Selected top {self.top_n}: {selected_symbols}"
        )

        # Step 5: Equal-weight selected assets
        if not selected_symbols:
            # Fallback to equal weight across all
            symbols = list(prices.columns)
            symbol_to_name = self._build_name_map()
            index = [symbol_to_name.get(s, s) for s in symbols]
            equal_weight = 1.0 / len(symbols) if symbols else 1.0
            return pd.Series(equal_weight, index=index)

        selected_weight = 1.0 / len(selected_symbols)
        selected_weights = pd.Series(
            selected_weight, index=selected_symbols
        )

        # Step 6: Build full weight vector
        symbols = list(prices.columns)
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in symbols]

        weights = pd.Series(0.0, index=index)
        for symbol in selected_symbols:
            name = symbol_to_name.get(symbol, symbol)
            weights[name] = selected_weight

        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return max(self.history_years * 252, 500)
