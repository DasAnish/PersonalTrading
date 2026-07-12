"""
Low-Volatility Tilt strategy.

Ranks assets by trailing total volatility and tilts toward lowest-vol half,
zero-weights highest-vol half. Implements either equal-weight or inverse-vol
weighting within the held set.

Based on Blitz & van Vliet (2007, SSRN 980865) — low-volatility stocks earn
higher risk-adjusted returns than high-vol stocks (opposite of CAPM). Global
low-minus-high decile alpha ~12% annually over 1986-2006. Drivers: leverage
constraints, benchmark-relative tracking error aversion, behavioral biases
(lottery preference, overconfidence in volatile stocks).

Note: On a mixed-asset ETF universe, raw total-vol ranking mechanically favors
structurally low-vol assets (VUTY >> broad equity >> single-country/thematic).
Best applied within-sleeve (e.g., equity-only) rather than cross-asset.

Example:
    assets = [
        AssetStrategy('VUSA'), ..., AssetStrategy('SGLN'), AssetStrategy('VUTY')
    ]
    strategy = LowVolatilityTiltStrategy(
        underlying=assets,
        vol_lookback_days=252,
        held_fraction=0.5
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List, Literal

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class LowVolatilityTiltStrategy(AllocationStrategy):
    """
    Tilt toward lowest-volatility assets, zero-weight highest-volatility.

    Ranks assets by trailing total volatility (standard deviation of returns),
    holds lowest-vol fraction, zero-weights highest-vol fraction. Remaining
    assets hold zero weight.

    Attributes:
        vol_lookback_days: Lookback for vol calculation (252/504, default 252)
        held_fraction: Fraction of lowest-vol assets to hold (0.4-0.5, default 0.5)
        weighting: 'equal' (equal-weight held) or 'inverse_vol' (inverse-vol weighted)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        vol_lookback_days: int = 252,
        held_fraction: float = 0.5,
        weighting: Literal["equal", "inverse_vol"] = "equal",
        name: str = None,
    ):
        """
        Initialize Low-Volatility Tilt strategy.

        Args:
            underlying: List of underlying strategies (assets)
            vol_lookback_days: Lookback for vol calc (252/504, default 252)
            held_fraction: Fraction of lowest-vol assets to hold (0.4-0.5, default 0.5)
            weighting: 'equal' or 'inverse_vol' (default 'equal')
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Low Vol Tilt ({held_fraction:.0%})",
        )
        self.vol_lookback_days = vol_lookback_days
        self.held_fraction = held_fraction
        self.weighting = weighting

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate weights: tilt to lowest-vol half, zero high-vol half.

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=strategy names, values=weights (sum to 1.0)

        Logic:
            1. For each asset, compute trailing volatility (std of returns)
            2. Rank by volatility (ascending)
            3. Hold lowest-vol fraction, zero-weight remainder
            4. Apply weighting scheme (equal or inverse-vol)
            5. Normalize to sum to 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]
        weights = pd.Series(0.0, index=strategy_names)

        # Step 1: Compute volatility for each asset
        vol_scores = {}
        for symbol in available_symbols:
            price_series = context.prices[symbol]

            if len(price_series) >= self.vol_lookback_days:
                returns = (
                    price_series.iloc[-self.vol_lookback_days :].pct_change().dropna()
                )
            else:
                returns = price_series.pct_change().dropna()

            if len(returns) >= 2:
                vol = returns.std()
            else:
                vol = 0.0

            vol_scores[symbol] = vol
            logger.debug(f"Low Vol {symbol}: vol={vol:.6f}")

        # Step 2: Rank by volatility (ascending)
        ranked = sorted(vol_scores.items(), key=lambda x: x[1])
        num_to_hold = max(1, int(len(ranked) * self.held_fraction))
        held_symbols = [sym for sym, _ in ranked[:num_to_hold]]

        logger.debug(
            f"LowVolTilt: ranked={ranked}. Hold lowest {num_to_hold} "
            f"({self.held_fraction:.0%}): {held_symbols}"
        )

        # Step 3: Apply weighting
        if self.weighting == "inverse_vol":
            # Inverse-vol weighting: weight = 1/vol / sum(1/vol)
            inverse_vols = {}
            for symbol in held_symbols:
                vol = vol_scores[symbol]
                if vol > 0:
                    inverse_vols[symbol] = 1.0 / vol
                else:
                    inverse_vols[symbol] = 0.0

            total_inverse_vol = sum(inverse_vols.values())
            if total_inverse_vol > 0:
                for symbol in held_symbols:
                    weight = inverse_vols[symbol] / total_inverse_vol
                    strategy_name = symbol_to_name.get(symbol, symbol)
                    weights[strategy_name] = weight
        else:
            # Equal-weight
            num_held = len(held_symbols)
            equal_weight = 1.0 / num_held if num_held > 0 else 0.0
            for symbol in held_symbols:
                strategy_name = symbol_to_name.get(symbol, symbol)
                weights[strategy_name] = equal_weight

        logger.debug(
            f"LowVolTilt ({self.weighting}): {dict(weights[weights > 0].round(4))}"
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Low-Volatility Tilt requires lookback for volatility calculation.

        Returns:
            vol_lookback_days
        """
        return self.vol_lookback_days

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
