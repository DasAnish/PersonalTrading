"""
Turn-of-Month Seasonal Rotation strategy.

Pure calendar rotation that holds an equal-weight equity sleeve during the
turn-of-month window (last 1-2 and first 3-4 trading days of each calendar month)
and rotates to a defensive sleeve (VUTY, SGLN, AGGU, SEGA) for the rest of the month.

The strategy exploits the "Turn-of-the-Month Effect" — an observed pattern where
equity returns tend to be stronger around month boundaries (last and first few
trading days of each calendar month).

References:
- Ariel (1987): "A Monthly Effect in Stock Returns"
- Henkel, Martin & Nardari (2011): "Time-Varying Short-Horizon Predictability"
- Calendar-based seasonal rotation from defensive assets to equities

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), AssetStrategy('IWRD'),
        AssetStrategy('IMEU'), AssetStrategy('IIND'), AssetStrategy('AIGC'),
        AssetStrategy('VUTY'), AssetStrategy('SGLN'),
    ]
    strategy = TurnOfMonthSeasonalityStrategy(
        underlying=assets,
        days_before_month_end=2,
        days_after_month_start=3
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List
from datetime import datetime, timedelta
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Equity sleeve (held during turn-of-month window).
# AIGC is deliberately excluded: it is WisdomTree Broad Commodities ETC, not
# an equity/AI product (an earlier asset-definition label error implied
# otherwise).
EQUITY_SLEEVE = {
    "VUSA",
    "EQQQ",
    "IWRD",
    "IMEU",
    "IIND",
    "ASHR",
    "SAEM",
    "CACX",
    "CSX5",
    "IEMU",
    "WCLD",
    "WSML",
    "AWESGS",
    "EMMCHA",
    "EXXW",
    "EXX5",
    "EXI2",
    "EXSA",
}

# Defensive sleeve (held outside turn-of-month window)
DEFENSIVE_SLEEVE = {"VUTY", "SGLN", "AGGU", "SEGA"}


class TurnOfMonthSeasonalityStrategy(AllocationStrategy):
    """
    Turn-of-Month seasonal rotation strategy based on calendar patterns.

    Allocates to an equity sleeve during a window around month-end/month-start
    (last N trading days of month + first M trading days of next month) and
    rotates to a defensive sleeve for the remainder of the month.

    Only uses assets actually present in the rebalance universe. If a sleeve
    has no assets, falls back to equal weight across all available assets.

    Attributes:
        days_before_month_end: Number of trading days at end of month for risk-on
        days_after_month_start: Number of trading days at start of month for risk-on
        equity_sleeve: Set of symbols for equity allocation (risk-on)
        defensive_sleeve: Set of symbols for defensive allocation (risk-off)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        days_before_month_end: int = 2,
        days_after_month_start: int = 3,
        name: str = None,
    ):
        """
        Initialize Turn-of-Month Seasonality strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            days_before_month_end: Trading days at end of month to hold equities (default 2)
            days_after_month_start: Trading days at start of month to hold equities (default 3)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or "Turn-of-Month Seasonality",
        )
        self.days_before_month_end = days_before_month_end
        self.days_after_month_start = days_after_month_start

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate seasonal rotation weights based on day of month.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=asset names, values=equal weights for selected sleeve
            Weights sum to 1.0 (long-only)

        Logic:
            - Check if current date is in turn-of-month window
            - Window = last N trading days of month + first M trading days of next month
            - Inside window: equal weight across equity sleeve (risk-on)
            - Outside window: equal weight across defensive sleeve (risk-off)
            - Only use assets present in context.prices
            - If selected sleeve has no assets, fallback to equal weight all assets
        """
        # Get available symbols from price data
        available_symbols = set(context.prices.columns)

        # Build symbol -> strategy name mapping
        symbol_to_name = self._build_name_map()

        # Initialize weights (all zeros)
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Determine if current date is in turn-of-month window
        current_date = context.current_date
        is_turn_of_month = self._is_in_turn_of_month_window(current_date)

        if is_turn_of_month:
            selected_sleeve = EQUITY_SLEEVE
            regime_name = "risk-on (turn-of-month)"
        else:
            selected_sleeve = DEFENSIVE_SLEEVE
            regime_name = "risk-off (mid-month)"

        logger.debug(
            f"TurnOfMonth: date={current_date.date()}, regime={regime_name}, "
            f"sleeve={selected_sleeve}"
        )

        # Filter sleeve assets to only those available in prices
        sleeve_assets = selected_sleeve & available_symbols

        if not sleeve_assets:
            # Fallback: if selected sleeve has no assets, use all available
            logger.warning(
                f"TurnOfMonth: no assets in {regime_name} sleeve, "
                f"falling back to equal weight all available assets"
            )
            sleeve_assets = available_symbols

        # Assign equal weight to selected assets
        num_assets = len(sleeve_assets)
        equal_weight = 1.0 / num_assets if num_assets > 0 else 0.0

        for symbol in sleeve_assets:
            strategy_name = symbol_to_name.get(symbol, symbol)
            weights[strategy_name] = equal_weight

        logger.debug(f"TurnOfMonth weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        TurnOfMonth requires only current prices (no historical analysis).

        Returns:
            0 (no lookback needed, but recommend some historical data for context)
        """
        return 0

    def _is_in_turn_of_month_window(self, current_date: datetime) -> bool:
        """
        Determine if current date is within the turn-of-month window.

        The window consists of:
        - Last N trading days of the current month
        - First M trading days of the next month

        For simplicity, we use calendar days as a proxy for trading days.
        A more refined version could use actual trading-day calendars.

        Args:
            current_date: The current date to check

        Returns:
            True if in turn-of-month window, False otherwise
        """
        day_of_month = current_date.day

        # Get last day of current month
        if current_date.month == 12:
            next_month_date = datetime(current_date.year + 1, 1, 1)
        else:
            next_month_date = datetime(current_date.year, current_date.month + 1, 1)

        last_day_of_month = (next_month_date - timedelta(days=1)).day

        # Check if in last N days of month (end-of-month window)
        if day_of_month > (last_day_of_month - self.days_before_month_end):
            return True

        # Check if in first M days of month (start-of-month window)
        if day_of_month <= self.days_after_month_start:
            return True

        return False

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
