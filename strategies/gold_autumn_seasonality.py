"""
Gold Autumn Effect Seasonality strategy.

Overwrites gold (SGLN) allocation during Sep-Nov based on documented seasonal
strength in those months. Remainder allocated to base portfolio (equity/bond mix
or equal weight across other assets).

Based on Baur (2013) — September and November show significant positive gold
returns over 1980-2010. Drivers: hedging ahead of equity Halloween effect,
Indian wedding-season jewellery demand, seasonal negative sentiment.

Example:
    assets = [AssetStrategy('VUSA'), ..., AssetStrategy('SGLN'), AssetStrategy('VUTY')]
    strategy = GoldAutumnSeasonalityStrategy(underlying=assets, w_high=0.30, months='sep_nov')
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List, Literal

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Autumn months: Sep-Nov (9, 10, 11) or just Sep-Oct (9, 10)
AUTUMN_MONTHS_FULL = {9, 10, 11}
AUTUMN_MONTHS_SHORT = {9}

# Gold symbols
GOLD_SYMBOLS = {"SGLN", "SSLN"}  # SGLN primary, SSLN silver optional


class GoldAutumnSeasonalityStrategy(AllocationStrategy):
    """
    Seasonal rotation into gold during Sep-Nov, base allocation otherwise.

    Overwrites gold weight during autumn months (parameter-driven: full Sep-Nov
    or Sep+Nov only), with remainder allocated equally across equity/bond base.

    Attributes:
        w_high: Overweight allocation to gold during Sep-Nov (0.20-0.40)
        w_low: Base allocation to gold outside Sep-Nov (0.00-0.10)
        months: 'sep_nov' (full Sep-Nov) or 'sep_only' (Sep+Nov only, skip Oct)
        base_symbols: Assets for remainder (all except gold)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        w_high: float = 0.30,
        w_low: float = 0.05,
        months: Literal["sep_nov", "sep_only"] = "sep_nov",
        name: str = None,
    ):
        """
        Initialize Gold Autumn Seasonality strategy.

        Args:
            underlying: List of underlying strategies (assets)
            w_high: Overweight gold during autumn (0.20-0.40, default 0.30)
            w_low: Base gold weight outside autumn (0.00-0.10, default 0.05)
            months: 'sep_nov' (full Sep-Nov) or 'sep_only' (Sep+Nov only)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Gold Autumn (w_high={w_high:.0%})",
        )
        self.w_high = w_high
        self.w_low = w_low
        self.months = months
        self.autumn_set = (
            AUTUMN_MONTHS_FULL if months == "sep_nov" else AUTUMN_MONTHS_SHORT
        )

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate weights: gold overweighted Sep-Nov, equal weight base remainder.

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=strategy names, values=weights (sum to 1.0)

        Logic:
            1. Determine if current month is in autumn window
            2. Set gold weight (high or low)
            3. Equal-weight remainder across non-gold assets
            4. Normalize to sum to 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Step 1: Check if current month is in autumn
        current_month = context.current_date.month
        is_autumn = current_month in self.autumn_set

        gold_weight = self.w_high if is_autumn else self.w_low
        season = "autumn" if is_autumn else "non-autumn"

        logger.debug(
            f"GoldAutumnSeasonality: month={current_month}, season={season}, "
            f"gold_weight={gold_weight:.4f}"
        )

        # Step 2: Assign gold weight
        gold_symbols_available = GOLD_SYMBOLS & available_symbols
        if gold_symbols_available:
            # Use primary gold symbol (SGLN) if available, else SSLN
            gold_symbol = (
                "SGLN"
                if "SGLN" in gold_symbols_available
                else list(gold_symbols_available)[0]
            )
            gold_name = symbol_to_name.get(gold_symbol, gold_symbol)
            weights[gold_name] = gold_weight

        # Step 3: Equal-weight remainder
        base_symbols = available_symbols - GOLD_SYMBOLS
        if base_symbols:
            num_base = len(base_symbols)
            base_weight_total = 1.0 - gold_weight
            base_weight_per_asset = (
                base_weight_total / num_base if num_base > 0 else 0.0
            )

            for symbol in base_symbols:
                strategy_name = symbol_to_name.get(symbol, symbol)
                weights[strategy_name] = base_weight_per_asset

        logger.debug(
            f"GoldAutumnSeasonality weights: {dict(weights[weights > 0].round(4))}"
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Gold Autumn Seasonality requires only current prices (calendar-based).

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
