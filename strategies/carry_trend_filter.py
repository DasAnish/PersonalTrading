"""
Carry Conditioned on Trend Filter strategy.

Combines cross-asset carry ranking with a trend filter: only allocate to
carry-selected assets whose own 6-12m total return is positive. Assets
failing the trend filter route their weight to VUTY (safe asset) or
renormalize across survivors.

Based on Baz, Granger, Harvey, Le Roux & Rattray (2015) — carry crashes
are predictable from trend breaks, so filtering carry by asset-level trend
cuts the left tail while retaining most of the carry premium.

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('SSLN'), ..., AssetStrategy('VUTY')
    ]
    strategy = CarryTrendFilterStrategy(underlying=assets, top_n=3, trend_lookback_days=189)
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Ex-ante carry priors (shared with CarryTiltStrategy)
CARRY_PRIORS = {
    "VUTY": 0.035,
    "HYLD": 0.060,
    "AGGU": 0.045,
    "SEGA": 0.025,
    "TIGG": 0.070,
    "VUSA": 0.020,
    "EQQQ": 0.008,
    "IWRD": 0.025,
    "IMEU": 0.030,
    "IIND": 0.020,
    "ASHR": 0.020,
    "SAEM": 0.025,
    "CACX": 0.030,
    "CSX5": 0.030,
    "IEMU": 0.030,
    "WCLD": 0.003,
    "WSML": 0.018,
    "AWESGS": 0.018,
    "EMMCHA": 0.025,
    "EXXW": 0.040,
    "EXX5": 0.035,
    "EXI2": 0.022,
    "EXSA": 0.028,
    "SGLN": -0.005,
    "SSLN": -0.005,
    "BRNT": 0.000,
    "CRUD": 0.000,
    "COMM": 0.000,
    "ICOM": 0.000,
    "WCOA": 0.000,
    "AIGC": 0.000,
}

# Safe asset for failed trend filters
SAFE_ASSET = "VUTY"


class CarryTrendFilterStrategy(AllocationStrategy):
    """
    Carry allocation filtered by asset-level trend.

    Ranks assets by ex-ante carry, selects top-N, then applies a trend
    filter (6-12m positive return). Assets failing trend route weight to
    VUTY or renormalize.

    Attributes:
        top_n: Number of top-carry assets to screen (default 4)
        trend_lookback_days: Lookback for trend check (126/189/252)
        redirect_to_safe: If True, failed assets route to VUTY; else renormalize
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 3,
        trend_lookback_days: int = 189,
        redirect_to_safe: bool = True,
        name: str = None,
    ):
        """
        Initialize Carry Trend Filter strategy.

        Args:
            underlying: List of underlying strategies (assets)
            top_n: Number of top-carry assets to screen (2-4, default 3)
            trend_lookback_days: Lookback for trend check (126/189/252)
            redirect_to_safe: Redirect failed weight to VUTY (True) or renormalize (False)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Carry+Trend (top_{top_n}, {trend_lookback_days}d)",
        )
        self.top_n = min(max(top_n, 1), len(underlying))
        self.trend_lookback_days = trend_lookback_days
        self.redirect_to_safe = redirect_to_safe

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate weights: carry-selected, trend-filtered, with fallback to VUTY.

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=strategy names, values=weights (sum to 1.0)

        Logic:
            1. Rank available assets by carry (ex-ante yield)
            2. Select top_n by carry
            3. For each top_n asset, check 6-12m trend (positive return = keep)
            4. Assets failing trend route weight to VUTY (or renormalize)
            5. Normalize final weights to sum to 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Step 1: Rank by carry
        carry_scores = {}
        for symbol in available_symbols:
            carry_scores[symbol] = CARRY_PRIORS.get(symbol, 0.0)

        ranked = sorted(carry_scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [sym for sym, _ in ranked[: self.top_n]]

        logger.debug(
            f"CarryTrendFilter: ranked {ranked}. Top {self.top_n}: {top_symbols}"
        )

        # Step 2: Apply trend filter to top_n
        passed_symbols = []
        failed_symbols = []

        for symbol in top_symbols:
            if symbol not in context.prices.columns:
                continue

            # Check 6-12m trend (trend_lookback_days)
            price_series = context.prices[symbol]
            if len(price_series) >= self.trend_lookback_days:
                current_price = price_series.iloc[-1]
                past_price = price_series.iloc[-self.trend_lookback_days]
                price_return = (current_price - past_price) / past_price
            else:
                # Insufficient history; use current price vs first available
                current_price = price_series.iloc[-1]
                past_price = price_series.iloc[0]
                price_return = (current_price - past_price) / past_price

            if price_return > 0:
                passed_symbols.append(symbol)
                logger.debug(f"  {symbol}: trend PASS (return={price_return:.4f})")
            else:
                failed_symbols.append(symbol)
                logger.debug(f"  {symbol}: trend FAIL (return={price_return:.4f})")

        # Step 3: Assign weights
        if not passed_symbols:
            # All failed; fallback to equal weight across top_n
            logger.warning(
                f"CarryTrendFilter: all top {self.top_n} failed trend. "
                f"Falling back to equal weight top_n."
            )
            passed_symbols = top_symbols

        num_passed = len(passed_symbols)
        if num_passed > 0:
            equal_weight = 1.0 / num_passed
            for symbol in passed_symbols:
                strategy_name = symbol_to_name.get(symbol, symbol)
                weights[strategy_name] = equal_weight

        # Step 4: Handle failed weight
        if failed_symbols and self.redirect_to_safe:
            safe_name = symbol_to_name.get(SAFE_ASSET, SAFE_ASSET)
            if safe_name in weights.index:
                failed_weight = len(failed_symbols) / (num_passed + len(failed_symbols))
                weights[safe_name] += failed_weight
                # Renormalize
                total_weight = weights.sum()
                if total_weight > 0:
                    weights /= total_weight

        logger.debug(f"CarryTrendFilter weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Carry Trend Filter requires lookback for trend check.

        Returns:
            trend_lookback_days
        """
        return self.trend_lookback_days

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
