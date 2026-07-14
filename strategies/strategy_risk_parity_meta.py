"""
Strategy-Level Risk Parity Ensemble (volatility-weighted meta-portfolio).

Applies Qian's risk parity logic across sub-strategies instead of assets.
Each sub-strategy weighted by inverse of its trailing volatility,
normalized to sum 1.0. Produces more balanced ensemble risk contribution
than naive equal-weight blending.

Based on Qian (2005): "Risk Parity Portfolios: Efficient Portfolios Through
True Diversification"

Example (JSON definition):
    {
        "type": "portfolio",
        "class": "StrategyRiskParityMetaStrategy",
        "name": "Strategy Risk Parity",
        "parameters": {
            "vol_lookback": 504,
            "weight_floor": 0.05,
            "weight_cap": 0.50
        },
        "underlying": [
            "allocations/flexible_asset_allocation",
            "allocations/stock_bond_correlation_regime",
            "allocations/short_term_reversal",
            "composed/minimum_cvar_full",
            "composed/residual_momentum"
        ]
    }
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class StrategyRiskParityMetaStrategy(AllocationStrategy):
    """
    Inverse-volatility weighted meta-portfolio across sub-strategies.

    For each rebalance:
    1. Each sub-strategy computes its asset weight vector.
    2. For each sub-strategy, compute trailing realized volatility from its
       monthly returns (default 504d lookback = 24 months).
    3. Weight each sub-strategy by 1 / trailing_volatility.
    4. Normalize weights to sum 1.0.
    5. Blend asset weight vectors using sub-strategy weights.

    Optional weight floor/cap per sub-strategy prevents temporary low-vol
    sub-strategies from dominating the ensemble.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        vol_lookback: int = 504,
        weight_floor: float = None,
        weight_cap: float = None,
        name: str = None,
    ):
        """
        Initialize strategy risk-parity meta-portfolio.

        Args:
            underlying: List of underlying strategies to blend
            vol_lookback: Trailing days for volatility calculation (default 504 = 24 months)
            weight_floor: Minimum weight per sub-strategy (e.g., 0.05 = 5%), or None for no floor
            weight_cap: Maximum weight per sub-strategy (e.g., 0.50 = 50%), or None for no cap
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or "Strategy Risk Parity Meta",
        )
        self.vol_lookback = vol_lookback
        self.weight_floor = weight_floor
        self.weight_cap = weight_cap

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate inverse-volatility weighted blend of sub-strategies.

        Args:
            context: StrategyContext with prices, current_date, portfolio_values

        Returns:
            pd.Series with index=asset symbols, values=blended weights.
            Weights sum to 1.0 (long-only).
        """
        all_symbols = sorted(
            set(sym for strat in self.underlying for sym in strat.get_symbols())
        )

        # Collect sub-strategy weight vectors
        sub_strategy_weights = {}  # name -> pd.Series (asset weights)
        sub_strategy_vols = {}  # name -> realized vol

        for sub_strategy in self.underlying:
            try:
                # Get asset weights from sub-strategy
                sub_weights = sub_strategy.calculate_weights(context)
                asset_weights = self._resolve_to_symbols(
                    sub_weights, sub_strategy, all_symbols
                )
                sub_strategy_weights[sub_strategy.name] = asset_weights

                # Compute trailing realized volatility
                vol = self._compute_trailing_vol(sub_strategy, context)
                sub_strategy_vols[sub_strategy.name] = vol

                logger.debug(
                    f"StrategyRiskParity: {sub_strategy.name} vol={vol:.4f}"
                )

            except Exception as e:
                logger.warning(
                    f"StrategyRiskParity: sub-strategy {sub_strategy.name} failed: {e}, skipping"
                )

        if not sub_strategy_weights:
            logger.warning(
                "StrategyRiskParity: all sub-strategies failed, using equal weight"
            )
            return pd.Series(1.0 / len(all_symbols), index=all_symbols)

        # Compute inverse-volatility weights
        inv_vol_weights = self._compute_inverse_vol_weights(
            sub_strategy_vols,
            weight_floor=self.weight_floor,
            weight_cap=self.weight_cap,
        )

        # Blend sub-strategy weight vectors
        blended = pd.Series(0.0, index=all_symbols)
        for name, weight in inv_vol_weights.items():
            if name in sub_strategy_weights:
                blended += weight * sub_strategy_weights[name]

        # Normalize
        total = blended.sum()
        if total > 0:
            blended /= total

        logger.debug(
            f"StrategyRiskParity: meta weights = {dict(blended[blended > 0.001].round(4))}"
        )

        return blended

    def get_strategy_lookback(self) -> int:
        """
        Use max of underlying lookback + own vol lookback.

        Returns:
            Lookback in days
        """
        lookbacks = [self.vol_lookback]
        for strat in self.underlying:
            try:
                req = strat.get_data_requirements()
                lookbacks.append(req.lookback_days or 252)
            except Exception:
                lookbacks.append(252)
        return max(lookbacks) if lookbacks else 504

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_to_symbols(
        self,
        weights: pd.Series,
        sub_strategy: Strategy,
        all_symbols: List[str],
    ) -> pd.Series:
        """
        Convert weight Series indexed by asset symbols or strategy names
        into one indexed by asset symbols.

        Same logic as MetaPortfolioStrategy._resolve_to_symbols.
        """
        result = pd.Series(0.0, index=all_symbols)

        # Fast path: all weight labels are already asset symbols
        if all(label in all_symbols for label in weights.index):
            for sym, w in weights.items():
                result[sym] = w
            total = result.sum()
            if total > 0:
                result /= total
            return result

        # Slow path: build name → symbol mapping
        name_to_symbols: dict[str, List[str]] = {}

        def _collect_leaves(strat: Strategy) -> None:
            underlying = getattr(strat, "underlying", None)
            if underlying is None:
                # Leaf node
                for sym in strat.get_symbols():
                    name_to_symbols.setdefault(strat.name, []).append(sym)
            elif isinstance(underlying, list):
                for child in underlying:
                    _collect_leaves(child)
            else:
                _collect_leaves(underlying)

        _collect_leaves(sub_strategy)

        for idx_label, w in weights.items():
            if idx_label in all_symbols:
                result[idx_label] += w
            elif idx_label in name_to_symbols:
                syms = name_to_symbols[idx_label]
                for sym in syms:
                    if sym in result.index:
                        result[sym] += w / len(syms)

        total = result.sum()
        if total > 0:
            result /= total

        return result

    def _compute_trailing_vol(
        self, sub_strategy: Strategy, context: StrategyContext
    ) -> float:
        """
        Compute trailing realized volatility of sub-strategy's returns.

        Args:
            sub_strategy: Strategy to measure
            context: StrategyContext with portfolio_values and prices

        Returns:
            Annualized volatility (float). Returns 0.1 (10%) if unable to compute.
        """
        try:
            # Get price timeseries for this sub-strategy
            strategy_prices = sub_strategy.get_price_timeseries(context)

            # Only use data up to current_date
            prices_up_to_date = strategy_prices[
                strategy_prices.index <= context.current_date
            ]

            if len(prices_up_to_date) < 20:
                logger.debug(
                    f"StrategyRiskParity: {sub_strategy.name} has <20 prices, using default vol 0.1"
                )
                return 0.1

            # Compute returns (daily)
            returns = prices_up_to_date.pct_change().dropna()

            if len(returns) < 2:
                return 0.1

            # Annualized volatility (sqrt(252))
            vol = returns.std() * np.sqrt(252)

            # Clamp to reasonable range
            if vol < 0.001:
                vol = 0.001
            if vol > 1.0:
                vol = 1.0

            return vol

        except Exception as e:
            logger.debug(
                f"StrategyRiskParity: failed to compute vol for {sub_strategy.name}: {e}"
            )
            return 0.1

    def _compute_inverse_vol_weights(
        self,
        vols: dict[str, float],
        weight_floor: float = None,
        weight_cap: float = None,
    ) -> dict[str, float]:
        """
        Compute inverse-volatility normalized weights.

        Args:
            vols: Dict of {strategy_name: volatility}
            weight_floor: Min weight per strategy (e.g., 0.05)
            weight_cap: Max weight per strategy (e.g., 0.50)

        Returns:
            Dict of {strategy_name: normalized_weight}, summing to 1.0
        """
        if not vols:
            return {}

        # Compute inverse vols
        inv_vols = {name: 1.0 / vol if vol > 0 else 1.0 for name, vol in vols.items()}

        # Sum for normalization
        total_inv_vol = sum(inv_vols.values())
        if total_inv_vol <= 0:
            # Fallback to equal weight
            return {name: 1.0 / len(inv_vols) for name in inv_vols}

        # Normalize to sum 1.0
        weights = {name: inv_vol / total_inv_vol for name, inv_vol in inv_vols.items()}

        # Apply floor/cap
        if weight_floor is not None or weight_cap is not None:
            weights = self._apply_weight_constraints(weights, weight_floor, weight_cap)

        return weights

    def _apply_weight_constraints(
        self,
        weights: dict[str, float],
        weight_floor: float = None,
        weight_cap: float = None,
    ) -> dict[str, float]:
        """
        Apply min/max weight constraints and re-normalize.

        Args:
            weights: Initial weights {name: weight}
            weight_floor: Min weight per strategy
            weight_cap: Max weight per strategy

        Returns:
            Constrained weights re-normalized to sum 1.0
        """
        if not weights:
            return weights

        result = dict(weights)

        # Clip to floor/cap
        if weight_floor is not None:
            for name in result:
                if result[name] < weight_floor:
                    result[name] = weight_floor

        if weight_cap is not None:
            for name in result:
                if result[name] > weight_cap:
                    result[name] = weight_cap

        # Re-normalize
        total = sum(result.values())
        if total > 0:
            result = {name: w / total for name, w in result.items()}

        return result
