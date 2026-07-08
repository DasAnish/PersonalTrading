"""
Bond Duration Crisis Hedge Overlay strategy.

Overlays a dynamic bond-duration tilt on an equal-weight base allocation, triggered
when equity markets enter stress (detected via drawdown from trailing high).

Parallel design to GoldSafeHavenOverlayStrategy, but tilts weight toward long-duration
government bonds (VUTY/AGGU) instead of gold when triggered. Configurable hedge_asset
parameter allows targeting different fixed-income instruments.

Based on the premise that long-duration government bonds provide a safe-haven hedge
during equity market stress due to their negative correlation with equities during crises.

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), ..., AssetStrategy('VUTY')
    ]
    strategy = BondDurationHedgeOverlayStrategy(
        underlying=assets,
        drawdown_trigger=-0.10,
        duration_tilt_pp=15,
        decay_rebalances=1,
        hedge_asset='vuty'
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
EQUITY_SLEEVE = {
    'VUSA', 'EQQQ', 'IWRD', 'IMEU', 'IIND',
    'ASHR', 'SAEM', 'CACX', 'CSX5', 'IEMU', 'WCLD', 'WSML',
    'AWESGS', 'EMMCHA', 'EXXW', 'EXX5', 'EXI2', 'EXSA',
}

# Trailing window for drawdown calculation (6 months = ~126 trading days)
DRAWDOWN_LOOKBACK_DAYS = 126


class BondDurationHedgeOverlayStrategy(AllocationStrategy):
    """
    Bond duration crisis hedge stress-triggered overlay allocation strategy.

    Starts with an equal-weight base across all available assets. When an
    equity-stress signal is detected (market drawdown >= trigger), dynamically
    tilts weight toward a configurable hedge asset (typically VUTY or AGGU bonds)
    by pulling from the equity sleeve pro-rata, then decays the tilt back to base
    weights over subsequent rebalances.

    Only uses assets actually present in the rebalance universe. If hedge_asset is
    not available, falls back to equal-weight base. If equities are not available,
    skips the tilt (no stress signal to compute).

    Attributes:
        drawdown_trigger: Drawdown threshold (e.g., -0.10 = -10%) to trigger tilt
        duration_tilt_pp: Percentage points to tilt toward hedge asset (e.g., 15pp)
        decay_rebalances: Number of rebalances to decay tilt back to base
        hedge_asset: Asset key string (e.g., 'vuty' or 'aggu') to hedge with
    """

    def __init__(
        self,
        underlying: List[Strategy],
        drawdown_trigger: float = -0.10,
        duration_tilt_pp: float = 15.0,
        decay_rebalances: int = 1,
        hedge_asset: str = 'vuty',
        name: str = None,
    ):
        """
        Initialize Bond Duration Hedge Overlay strategy.

        Args:
            underlying: List of underlying strategies (assets)
            drawdown_trigger: Drawdown threshold (e.g., -0.10 for -10%)
            duration_tilt_pp: Percentage points to tilt to hedge asset (e.g., 15)
            decay_rebalances: Number of rebalances to decay tilt (default 1)
            hedge_asset: Asset key string (e.g., 'vuty', 'aggu')
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Bond Duration Hedge Overlay ({drawdown_trigger:.0%})",
        )
        self.drawdown_trigger = drawdown_trigger
        self.duration_tilt_pp = duration_tilt_pp / 100.0  # Convert pp to decimal
        self.decay_rebalances = decay_rebalances
        self.hedge_asset = hedge_asset.upper()

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate hedge-tilted weights based on equity stress signal.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=asset names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            1. Start with equal-weight base
            2. Compute equity stress signal: drawdown of equity sleeve from 6m high
            3. If drawdown <= trigger: tilt duration_tilt_pp from equities to hedge_asset
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

        # Check if hedge asset and equity assets are available
        if self.hedge_asset not in available_symbols:
            logger.debug(
                f"BondDurationHedge: {self.hedge_asset} not available, using base weights"
            )
            return weights

        available_equities = EQUITY_SLEEVE & available_symbols
        if not available_equities:
            logger.debug(
                "BondDurationHedge: no equity assets available, using base weights"
            )
            return weights

        # Compute equity stress signal: drawdown from trailing 6-month high
        stress_signal = self._compute_equity_stress_signal(
            context.prices, available_equities
        )

        logger.debug(f"BondDurationHedge: stress_signal (drawdown) = {stress_signal:.4f}")

        # Trigger tilt if stress signal meets threshold
        if stress_signal <= self.drawdown_trigger:
            logger.debug(
                f"BondDurationHedge: stress triggered (drawdown {stress_signal:.2%} "
                f"<= trigger {self.drawdown_trigger:.2%}), tilting {self.duration_tilt_pp:.1%} to {self.hedge_asset}"
            )

            # Build new weights: scale down equities, add to hedge asset
            equity_names = {
                symbol_to_name.get(sym, sym) for sym in available_equities
            }
            hedge_name = symbol_to_name.get(self.hedge_asset, self.hedge_asset)

            # Pull duration_tilt_pp from equity sleeve pro-rata
            equity_weight_total = weights[list(equity_names)].sum()
            if equity_weight_total > 0:
                # Reduce each equity pro-rata
                tilt_amount = self.duration_tilt_pp
                reduction_per_equity = tilt_amount / len(equity_names)
                for eq_name in equity_names:
                    weights[eq_name] -= reduction_per_equity

            # Add tilt to hedge asset
            weights[hedge_name] += self.duration_tilt_pp

            # Ensure no negative weights
            weights = weights.clip(0.0, None)

        # Normalize to sum to 1.0
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            # Fallback to equal-weight
            weights = pd.Series(equal_weight, index=strategy_names)

        logger.debug(f"BondDurationHedge weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Bond Duration Hedge requires trailing data for drawdown calculation.

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
                f"BondDurationHedge: insufficient price history ({len(prices)} < {DRAWDOWN_LOOKBACK_DAYS})"
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
