"""
Halloween Seasonal Rotation strategy.

Pure calendar rotation that holds an equal-weight equity sleeve in the
'winter' months (Nov-Apr) and rotates into a defensive sleeve for 'summer'
months (May-Oct).

The strategy implements the "Halloween Effect" or "Sell in May and go away"
seasonal pattern commonly observed in equities.

References:
- Bouman & Jacobsen (2002): "The Halloween Indicator"
- Seasonal rotation from global equities to defensive assets

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), AssetStrategy('IWRD'),
        AssetStrategy('IMEU'), AssetStrategy('IIND'), AssetStrategy('AIGC'),
        AssetStrategy('VUTY'), AssetStrategy('SGLN'),
    ]
    strategy = HalloweenSeasonalityStrategy(underlying=assets)
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Winter months: November-April
WINTER_MONTHS = {11, 12, 1, 2, 3, 4}

# Equity sleeve (summer rotation OUT of equities).
# AIGC is deliberately excluded: it is WisdomTree Broad Commodities ETC, not
# an equity/AI product (an earlier asset-definition label error implied
# otherwise).
EQUITY_SLEEVE = {
    'VUSA', 'EQQQ', 'IWRD', 'IMEU', 'IIND',
    'ASHR', 'SAEM', 'CACX', 'CSX5', 'IEMU', 'WCLD', 'WSML',
    'AWESGS', 'EMMCHA', 'EXXW', 'EXX5', 'EXI2', 'EXSA',
}

# Defensive sleeve (summer rotation INTO defensives)
DEFENSIVE_SLEEVE = {'VUTY', 'SGLN', 'AGGU', 'SEGA'}


class HalloweenSeasonalityStrategy(AllocationStrategy):
    """
    Pure calendar rotation strategy based on seasonal patterns.

    Allocates to an equity sleeve (VUSA, EQQQ, IWRD, IMEU, IIND, AIGC) during
    Nov-Apr and rotates to a defensive sleeve (VUTY, SGLN) during May-Oct.

    Only uses assets actually present in the rebalance universe. If a sleeve
    has no assets, falls back to equal weight across all available assets.

    Attributes:
        winter_months: Set of month numbers (1-12) for winter season
        equity_sleeve: Set of symbols for equity allocation
        defensive_sleeve: Set of symbols for defensive allocation
    """

    def __init__(self, underlying: List[Strategy], name: str = None):
        """
        Initialize Halloween Seasonality strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            name: Display name (default: "Halloween Seasonality")
        """
        super().__init__(
            underlying=underlying,
            name=name or "Halloween Seasonality",
        )

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate seasonal rotation weights based on current month.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=asset names, values=equal weights for selected sleeve
            Weights sum to 1.0 (long-only)

        Logic:
            - Extract current month from context.current_date
            - Nov-Apr: equal weight across equity sleeve
            - May-Oct: equal weight across defensive sleeve
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

        # Determine season and select sleeve
        current_month = context.current_date.month
        is_winter = current_month in WINTER_MONTHS

        if is_winter:
            selected_sleeve = EQUITY_SLEEVE
            season_name = "winter"
        else:
            selected_sleeve = DEFENSIVE_SLEEVE
            season_name = "summer"

        logger.debug(
            f"HalloweenSeasonality: month={current_month}, season={season_name}, "
            f"sleeve={selected_sleeve}"
        )

        # Filter sleeve assets to only those available in prices
        sleeve_assets = selected_sleeve & available_symbols

        if not sleeve_assets:
            # Fallback: if selected sleeve has no assets, use all available
            logger.warning(
                f"HalloweenSeasonality: no assets in {season_name} sleeve, "
                f"falling back to equal weight all available assets"
            )
            sleeve_assets = available_symbols

        # Assign equal weight to selected assets
        num_assets = len(sleeve_assets)
        equal_weight = 1.0 / num_assets if num_assets > 0 else 0.0

        for symbol in sleeve_assets:
            strategy_name = symbol_to_name.get(symbol, symbol)
            weights[strategy_name] = equal_weight

        logger.debug(
            f"HalloweenSeasonality weights: {dict(weights[weights > 0].round(4))}"
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        HalloweenSeasonality requires only current prices (no historical analysis).

        Returns:
            0 (no lookback needed)
        """
        return 0

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
