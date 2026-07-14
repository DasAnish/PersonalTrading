"""
Treasury Flight-to-Quality Hedge Overlay strategy.

Applies regime-dependent tilt toward VUTY (US Treasuries, GBP-hedged) based on
joint behaviour of equity sleeve and bond prices. Flight-to-quality regime
(equities down + VUTY up/flat = negative correlation) triggers duration tilt;
inflation/rate-shock regime (both down together = positive correlation) leaves
weights unchanged. Critically, overlay does NOT fire on positive-correlation
selloffs, matching the flight-to-quality thesis.

Based on stock-bond regime dependence literature:
- Stock-bond correlation is regime-dependent, not constant
- Negative correlation signals growth/demand shock (equity sell-off, capital
  rotates to bonds)
- Positive correlation signals inflation/rate shock (bonds sell off alongside
  equities, offering no protection)

Example (JSON definition):
    {
        "type": "allocation",
        "class": "TreasuryFlightToQualityOverlayStrategy",
        "name": "Treasury Flight-to-Quality Overlay",
        "parameters": {
            "class_window": 20,
            "duration_tilt_pp": 15,
            "correlation_threshold": -0.1
        },
        "underlying": "allocations/flexible_asset_allocation"
    }
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Equity sleeve for regime classification
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

# Treasury asset (hedge target)
TREASURY_ASSET = "VUTY"


class TreasuryFlightToQualityOverlayStrategy(AllocationStrategy):
    """
    Flight-to-quality overlay that tilts VUTY weight based on regime classification.

    Allocates across all available assets, detecting flight-to-quality vs.
    inflation-shock regime using realized stock-bond correlation over a trailing
    window. When FTQ regime is detected (equity drawdown + negative correlation),
    tilts duration_tilt_pp percentage points from equity sleeve to VUTY. Otherwise,
    uses equal-weight base—critically, does NOT fire on positive-correlation sell-offs.

    Attributes:
        class_window: Days for rolling correlation calculation (default 20)
        duration_tilt_pp: Percentage points to tilt to VUTY (e.g., 15pp)
        correlation_threshold: Correlation level for FTQ regime (default -0.1)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        class_window: int = 20,
        duration_tilt_pp: float = 15.0,
        correlation_threshold: float = -0.1,
        name: str = None,
    ):
        """
        Initialize Treasury Flight-to-Quality Overlay.

        Args:
            underlying: List of underlying asset strategies
            class_window: Rolling window for correlation calc (days, default 20)
            duration_tilt_pp: Percentage points to tilt to VUTY (default 15)
            correlation_threshold: Correlation threshold for FTQ regime (default -0.1)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or "Treasury Flight-to-Quality Overlay"
        )
        self.class_window = class_window
        self.duration_tilt_pp = duration_tilt_pp / 100.0  # Convert pp to decimal
        self.correlation_threshold = correlation_threshold

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate flight-to-quality-tilted weights based on regime classification.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=strategy names, values=weights (long-only, sum to 1.0)

        Logic:
            1. Start with equal-weight base across all assets
            2. Compute realized stock-bond correlation over class_window
            3. Compute equity sleeve drawdown
            4. If correlation < threshold AND equities in drawdown:
               - Trigger FTQ regime: tilt duration_tilt_pp from equities to VUTY
            5. Else: return base equal-weight unchanged
            6. Normalize to sum 1.0
        """
        # Get available symbols and build name mapping
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]

        # Initialize equal-weight base
        equal_weight = 1.0 / len(available_symbols)
        weights = pd.Series(equal_weight, index=strategy_names)

        # Check VUTY and equity assets available
        if TREASURY_ASSET not in available_symbols:
            logger.debug(
                f"TreasuryFTQ: {TREASURY_ASSET} not available, using base weights"
            )
            return weights

        available_equities = EQUITY_SLEEVE & available_symbols
        if not available_equities:
            logger.debug("TreasuryFTQ: no equity assets available, using base weights")
            return weights

        # Compute regime signal
        correlation, equity_dd = self._compute_regime_signal(
            context.prices, available_equities
        )

        logger.debug(
            f"TreasuryFTQ: correlation={correlation:.4f}, equity_dd={equity_dd:.4f}"
        )

        # Detect FTQ regime: negative correlation + equity drawdown
        is_ftq_regime = (
            correlation is not None
            and correlation < self.correlation_threshold
            and equity_dd < 0
        )

        if is_ftq_regime:
            logger.debug(
                f"TreasuryFTQ: FTQ regime detected (corr {correlation:.3f} "
                f"< {self.correlation_threshold:.3f}, equity_dd {equity_dd:.2%}), "
                f"tilting {self.duration_tilt_pp:.1%} to {TREASURY_ASSET}"
            )

            # Pull tilt from equity sleeve pro-rata
            equity_names = {
                symbol_to_name.get(sym, sym) for sym in available_equities
            }
            treasury_name = symbol_to_name.get(TREASURY_ASSET, TREASURY_ASSET)

            # Reduce equities pro-rata
            tilt_amount = self.duration_tilt_pp
            reduction_per_equity = tilt_amount / len(equity_names)
            for eq_name in equity_names:
                if eq_name in weights.index:
                    weights[eq_name] -= reduction_per_equity

            # Add tilt to treasury
            if treasury_name in weights.index:
                weights[treasury_name] += tilt_amount
            else:
                weights[treasury_name] = tilt_amount

            # Ensure no negative weights
            weights = weights.clip(0.0, None)

        # Normalize to sum 1.0
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            # Fallback to equal-weight
            weights = pd.Series(equal_weight, index=strategy_names)

        logger.debug(f"TreasuryFTQ: weights = {dict(weights[weights > 0.001].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Treasury FTQ requires trailing data for correlation calculation.

        Returns:
            class_window (days)
        """
        return self.class_window

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_regime_signal(
        self, prices: pd.DataFrame, equity_symbols: set
    ) -> tuple[float | None, float]:
        """
        Compute flight-to-quality regime signal.

        Returns:
            (correlation, equity_drawdown)
            correlation: Realized stock-bond correlation over class_window
                        (None if insufficient data)
            equity_drawdown: Trailing return of equity blend (e.g., -0.05 = -5%)
        """
        if len(prices) < self.class_window:
            logger.debug(
                f"TreasuryFTQ: insufficient price history ({len(prices)} < {self.class_window})"
            )
            return None, 0.0

        # Get equity and treasury prices over lookback window
        recent_prices = prices.tail(self.class_window)

        equity_prices = recent_prices[
            [sym for sym in recent_prices.columns if sym in equity_symbols]
        ]
        if equity_prices.empty or TREASURY_ASSET not in recent_prices.columns:
            return None, 0.0

        # Equal-weight equity blend
        equity_blend = equity_prices.mean(axis=1)
        treasury_prices = recent_prices[TREASURY_ASSET]

        # Compute returns
        equity_returns = equity_blend.pct_change().dropna()
        treasury_returns = treasury_prices.pct_change().dropna()

        if len(equity_returns) < 2 or len(treasury_returns) < 2:
            return None, 0.0

        # Ensure same length for correlation
        min_len = min(len(equity_returns), len(treasury_returns))
        if min_len < 2:
            return None, 0.0

        equity_returns = equity_returns.iloc[-min_len:]
        treasury_returns = treasury_returns.iloc[-min_len:]

        # Correlation
        try:
            correlation = equity_returns.corr(treasury_returns)
        except Exception as e:
            logger.debug(f"TreasuryFTQ: failed to compute correlation: {e}")
            correlation = None

        # Equity trailing return
        try:
            equity_trailing_return = (equity_blend.iloc[-1] / equity_blend.iloc[0] - 1.0)
        except Exception:
            equity_trailing_return = 0.0

        return correlation, equity_trailing_return

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}

        # If underlying is asset strategy, use symbol as name
        # If underlying is allocation/meta, build from strategy tree
        underlying = self.underlying

        def _collect_leaves(strat) -> None:
            if isinstance(strat, list):
                for child in strat:
                    _collect_leaves(child)
                return
            underlying_list = getattr(strat, "underlying", None)
            if underlying_list is None:
                # Leaf (AssetStrategy)
                for sym in strat.get_symbols():
                    symbol_to_name[sym] = strat.name
            elif isinstance(underlying_list, list):
                for child in underlying_list:
                    _collect_leaves(child)
            else:
                _collect_leaves(underlying_list)

        _collect_leaves(underlying)

        # Fallback: if map is empty, use symbols as names
        if not symbol_to_name:
            leaves = underlying if isinstance(underlying, list) else [underlying]
            for strat in leaves:
                for sym in strat.get_symbols():
                    symbol_to_name[sym] = sym

        return symbol_to_name
