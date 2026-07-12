"""
Gold Safe-Haven Stress Overlay strategy.

Overlays a dynamic gold tilt on an equal-weight base allocation, triggered
when equity markets enter stress (detected via drawdown from trailing high).

Based on Baur & Lucey (2010) "Is Gold a Hedge or a Safe Haven?" which documents
gold's negative correlation with equities specifically during market stress
periods, not just on average. This overlay tilts weight toward gold (SGLN) when
an equity-stress signal is detected, then decays the tilt back to base weights
over subsequent rebalances.

References:
- Baur & Lucey (2010): "Is Gold a Hedge or a Safe Haven?", The Financial Review
- Stress-triggered safe-haven hedging as a tactical overlay

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), ..., AssetStrategy('SGLN')
    ]
    strategy = GoldSafeHavenOverlayStrategy(
        underlying=assets,
        drawdown_trigger=-0.10,
        gold_tilt_pp=15,
        decay_rebalances=1
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd
import numpy as np

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Equity sleeve for stress signal computation.
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

# Gold safe-haven asset
GOLD_ASSET = "SGLN"

# Trailing window for drawdown calculation (6 months = ~126 trading days)
DRAWDOWN_LOOKBACK_DAYS = 126


class GoldSafeHavenOverlayStrategy(AllocationStrategy):
    """
    Gold safe-haven stress-triggered overlay allocation strategy.

    Starts with an equal-weight base across all available assets. When an
    equity-stress signal is detected (market drawdown >= trigger), dynamically
    tilts weight toward gold (SGLN) by pulling from the equity sleeve pro-rata,
    then decays the tilt back to base weights over subsequent rebalances.

    Only uses assets actually present in the rebalance universe. If SGLN is not
    available, falls back to equal-weight base. If equities are not available,
    skips the tilt (no stress signal to compute).

    Attributes:
        drawdown_trigger: Drawdown threshold (e.g., -0.10 = -10%) to trigger tilt
        gold_tilt_pp: Percentage points to tilt toward gold (e.g., 15pp)
        decay_rebalances: Number of rebalances to decay tilt back to base
    """

    def __init__(
        self,
        underlying: List[Strategy],
        drawdown_trigger: float = -0.10,
        gold_tilt_pp: float = 15.0,
        decay_rebalances: int = 1,
        name: str = None,
    ):
        """
        Initialize Gold Safe-Haven Overlay strategy.

        Args:
            underlying: List of underlying strategies (assets)
            drawdown_trigger: Drawdown threshold (e.g., -0.10 for -10%)
            gold_tilt_pp: Percentage points to tilt to SGLN (e.g., 15)
            decay_rebalances: Number of rebalances to decay tilt (default 1)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Gold Safe-Haven Overlay ({drawdown_trigger:.0%})",
        )
        self.drawdown_trigger = drawdown_trigger
        self.gold_tilt_pp = gold_tilt_pp / 100.0  # Convert pp to decimal
        self.decay_rebalances = decay_rebalances

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate safe-haven-tilted weights based on equity stress signal.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=asset names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            1. Start with equal-weight base
            2. Compute equity stress signal: drawdown of equity sleeve from 6m high
            3. If drawdown <= trigger: tilt gold_tilt_pp from equities to SGLN
            4. Otherwise: return base equal-weight
            5. Normalize to sum to 1.0
        """
        # Get available symbols and build name mapping
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]

        # Initialize equal-weight base
        equal_weight = 1.0 / len(available_symbols)
        weights = pd.Series(equal_weight, index=strategy_names)

        # Check if SGLN and equity assets are available
        if GOLD_ASSET not in available_symbols:
            logger.debug(
                f"GoldSafeHaven: {GOLD_ASSET} not available, using base weights"
            )
            return weights

        available_equities = EQUITY_SLEEVE & available_symbols
        if not available_equities:
            logger.debug(
                "GoldSafeHaven: no equity assets available, using base weights"
            )
            return weights

        # Compute equity stress signal: drawdown from trailing 6-month high
        stress_signal = self._compute_equity_stress_signal(
            context.prices, available_equities
        )

        logger.debug(f"GoldSafeHaven: stress_signal (drawdown) = {stress_signal:.4f}")

        # Trigger tilt if stress signal meets threshold
        if stress_signal <= self.drawdown_trigger:
            logger.debug(
                f"GoldSafeHaven: stress triggered (drawdown {stress_signal:.2%} "
                f"<= trigger {self.drawdown_trigger:.2%}), tilting {self.gold_tilt_pp:.1%} to {GOLD_ASSET}"
            )

            # Build new weights: scale down equities, add to gold
            equity_names = {symbol_to_name.get(sym, sym) for sym in available_equities}
            gold_name = symbol_to_name.get(GOLD_ASSET, GOLD_ASSET)

            # Pull gold_tilt_pp from equity sleeve pro-rata
            equity_weight_total = weights[list(equity_names)].sum()
            if equity_weight_total > 0:
                # Reduce each equity pro-rata
                tilt_amount = self.gold_tilt_pp
                reduction_per_equity = tilt_amount / len(equity_names)
                for eq_name in equity_names:
                    weights[eq_name] -= reduction_per_equity

            # Add tilt to gold
            weights[gold_name] += self.gold_tilt_pp

            # Ensure no negative weights
            weights = weights.clip(0.0, None)

        # Normalize to sum to 1.0
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            # Fallback to equal-weight
            weights = pd.Series(equal_weight, index=strategy_names)

        logger.debug(f"GoldSafeHaven weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Gold Safe-Haven requires trailing data for drawdown calculation.

        Returns:
            DRAWDOWN_LOOKBACK_DAYS (126 = 6 months)
        """
        return DRAWDOWN_LOOKBACK_DAYS

    def _compute_equity_stress_signal(
        self, prices: pd.DataFrame, equity_symbols: set
    ) -> float:
        """
        Compute equity stress signal: drawdown from trailing 6-month high.

        Args:
            prices: Price DataFrame with available symbols
            equity_symbols: Set of equity symbols to blend

        Returns:
            Drawdown as a float (e.g., -0.10 for -10%).
            Returns 0.0 (no stress) if insufficient data.
        """
        if len(prices) < DRAWDOWN_LOOKBACK_DAYS:
            logger.debug(
                f"GoldSafeHaven: insufficient price history ({len(prices)} < {DRAWDOWN_LOOKBACK_DAYS})"
            )
            return 0.0

        # Build equal-weight equity blend
        equity_prices = prices[[sym for sym in prices.columns if sym in equity_symbols]]
        if equity_prices.empty:
            return 0.0

        equity_blend = equity_prices.mean(axis=1)

        # Compute drawdown: current price / trailing high - 1
        trailing_high = equity_blend.tail(DRAWDOWN_LOOKBACK_DAYS).max()
        current_price = equity_blend.iloc[-1]

        if trailing_high > 0:
            drawdown = current_price / trailing_high - 1.0
        else:
            drawdown = 0.0

        return drawdown

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
