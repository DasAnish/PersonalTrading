"""
Cross-Asset Carry Tilt strategy.

Ranks assets by ex-ante carry (expected return from holding with flat prices)
and overweights high-carry assets, underweights/zeros low-carry assets.

Based on Koijen, Moskowitz, Pedersen & Vrugt (2018) "Carry" — carry predicts
returns cross-sectionally across equities, bonds, commodities, and currencies.

References:
- Koijen, Moskowitz, Pedersen & Vrugt (2018): "Carry", Journal of Financial
  Economics 127(2) 197-225
- Long-only implementation using ETF prices only; true carry (roll yield for
  futures) unavailable, so we use a pragmatic ex-ante carry proxy based on
  asset-class yield characteristics.

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), AssetStrategy('IWRD'),
        ...
    ]
    strategy = CarryTiltStrategy(underlying=assets, top_n=4)
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List, Dict

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# ============================================================================
# Ex-ante carry proxy definitions (model-free, price-only)
# ============================================================================

# Static carry priors by asset class (annual %, since we have price data only)
CARRY_PRIORS: Dict[str, float] = {
    # Bonds: strong positive carry (yield-to-maturity, roll-down)
    'VUTY': 0.035,  # US Treasuries: ~3.5% typical yield
    # Equities: moderate positive carry (dividend yield)
    'VUSA': 0.020,  # US equities: ~2% dividend yield
    'EQQQ': 0.008,  # Tech equities: ~0.8% dividend yield
    'IWRD': 0.025,  # Global equities: ~2.5% dividend yield
    'IMEU': 0.030,  # European equities: ~3% dividend yield
    'IIND': 0.020,  # Indian equities: ~2% dividend yield
    'AIGC': 0.015,  # AI/tech: ~1.5% dividend yield
    # Precious metals: negative carry (storage costs, no coupon)
    'SGLN': -0.005,  # Silver: storage costs, no yield
    'SSLN': -0.005,  # Gold: storage costs, no yield
    # Commodities: near-zero to negative (depends on futures term structure)
    'BRNT': 0.000,  # Brent oil: contango/backwardation dependent
    'CRUD': 0.000,  # Crude oil: contango/backwardation dependent
    'COMM': 0.000,  # Broad commodity: roll-dependent
    'WCOA': 0.000,  # Coal: commodity carry
}


class CarryTiltStrategy(AllocationStrategy):
    """
    Cross-asset carry tilt allocation strategy.

    Ranks assets by ex-ante carry (expected return from holding with flat prices)
    and concentrates weight into the top-N high-carry assets, with zero allocation
    to low-carry assets. This implements the "carry" factor across asset classes.

    Carry is model-free: bonds earn their yield-to-maturity, equities earn their
    dividend yield, commodities earn (or lose) their roll yield. The strategy
    is long-only, so the "short" leg is simply underweighting.

    Example:
        assets = [AssetStrategy('VUSA'), ..., AssetStrategy('SGLN')]
        strategy = CarryTiltStrategy(underlying=assets, top_n=4)
        weights = strategy.calculate_weights(context)  # Equal-weight top 4 by carry

    Attributes:
        top_n: Number of top-carry assets to hold equal-weight (default 4)
        carry_priors: Dict mapping symbols to ex-ante carry (annual %)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        top_n: int = 4,
        name: str = None,
    ):
        """
        Initialize Carry Tilt strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            top_n: Number of high-carry assets to overweight (default 4, range 3-6)
            name: Display name (default: "Carry Tilt")
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Carry Tilt (top_{top_n})",
        )
        self.top_n = min(max(top_n, 1), len(underlying))  # Clamp to [1, len(underlying)]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate carry-tilted weights: equal-weight top_n by carry, zero others.

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=strategy names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            1. Build symbol -> strategy name mapping
            2. For each available symbol, lookup carry prior
            3. Rank by carry (descending)
            4. Equal-weight top_n, zero the rest
            5. Normalize to sum to 1.0
        """
        # Get available symbols from price data
        available_symbols = set(context.prices.columns)

        # Build symbol -> strategy name mapping
        symbol_to_name = self._build_name_map()

        # Initialize weights (all zeros)
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Lookup carry for each available symbol
        carry_scores = {}
        for symbol in available_symbols:
            carry = CARRY_PRIORS.get(symbol, 0.0)
            carry_scores[symbol] = carry
            logger.debug(f"Carry[{symbol}] = {carry:.4f}")

        # Rank by carry (descending) and select top_n
        ranked = sorted(carry_scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [sym for sym, _ in ranked[:self.top_n]]

        logger.debug(
            f"CarryTilt: ranked by carry = {ranked}. "
            f"Top {self.top_n}: {top_symbols}"
        )

        # Assign equal weight to top_n, zero to rest
        num_top = len(top_symbols)
        if num_top > 0:
            equal_weight = 1.0 / num_top
            for symbol in top_symbols:
                strategy_name = symbol_to_name.get(symbol, symbol)
                weights[strategy_name] = equal_weight

        logger.debug(f"CarryTilt weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Carry Tilt requires only current prices (no historical calculation).

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
