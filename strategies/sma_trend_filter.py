"""
SMA Trend Filter (Faber Tactical Timing) strategy.

Binary 10-month (approx 200-trading-day) simple moving average crossover:
hold asset when price > SMA, zero weight when price <= SMA. Freed weight
from "out" assets redistributes to remaining "in" assets (renormalization).

Based on Faber (2007, SSRN 962461) — simple 200-day SMA crossover delivers
equity-like returns with materially lower volatility and max drawdown
across S&P 500 and 20+ other asset classes. Mechanism: trend persistence
and gradual information diffusion.

Key difference from repo's TrendFollowingStrategy: binary SMA crossover
(no vol-normalization, no continuous momentum score) vs. continuous EWMA
momentum. Both test the same underlying trend signal but via different
mechanics.

Example:
    assets = [
        AssetStrategy('VUSA'), ..., AssetStrategy('SGLN'), AssetStrategy('VUTY')
    ]
    strategy = SMATrendFilterStrategy(underlying=assets, lookback_days=210)
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class SMATrendFilterStrategy(AllocationStrategy):
    """
    Binary SMA trend filter: in if price > SMA, out otherwise.

    Equal-weights assets currently "in" (price > SMA), zero-weights "out"
    assets. Freed weight redistributes pro-rata across "in" assets.

    Attributes:
        lookback_days: SMA window (168/210/252 trading days, default 210 ≈ 10 months)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 210,
        name: str = None,
    ):
        """
        Initialize SMA Trend Filter strategy.

        Args:
            underlying: List of underlying strategies (assets)
            lookback_days: SMA window in trading days (168/210/252, default 210)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"SMA Trend ({lookback_days}d)",
        )
        self.lookback_days = lookback_days

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate binary SMA crossover weights: in/out per asset, equal-weight "in".

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=strategy names, values=weights (sum to 1.0)

        Logic:
            1. For each asset, compute SMA over lookback_days
            2. Signal: in (1) if current price > SMA, out (0) if price <= SMA
            3. Equal-weight "in" assets, zero-weight "out" assets
            4. Normalize to sum to 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Step 1: Compute SMA and signal for each asset
        in_signals = {}
        for symbol in available_symbols:
            price_series = context.prices[symbol]

            if len(price_series) >= self.lookback_days:
                sma = price_series.iloc[-self.lookback_days:].mean()
                current_price = price_series.iloc[-1]
            else:
                # Insufficient history; use all available
                sma = price_series.mean()
                current_price = price_series.iloc[-1]

            # Binary signal
            in_signal = 1 if current_price > sma else 0
            in_signals[symbol] = in_signal

            logger.debug(
                f"SMA {symbol}: price={current_price:.4f}, sma={sma:.4f}, "
                f"signal={in_signal}"
            )

        # Step 2: Count "in" assets
        in_symbols = [sym for sym, sig in in_signals.items() if sig == 1]

        if not in_symbols:
            # All "out"; fallback to equal weight across all
            logger.warning(
                f"SMATrendFilter: all assets are 'out'. Falling back to equal weight."
            )
            in_symbols = list(available_symbols)

        # Step 3: Equal-weight "in" assets
        num_in = len(in_symbols)
        equal_weight = 1.0 / num_in if num_in > 0 else 0.0

        for symbol in in_symbols:
            strategy_name = symbol_to_name.get(symbol, symbol)
            weights[strategy_name] = equal_weight

        logger.debug(
            f"SMATrendFilter: {len(in_symbols)} assets 'in', {len(available_symbols) - len(in_symbols)} 'out'. "
            f"Weights: {dict(weights[weights > 0].round(4))}"
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        SMA Trend Filter requires lookback for SMA calculation.

        Returns:
            lookback_days
        """
        return self.lookback_days

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
