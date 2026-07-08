"""
Volatility / Reward-to-Risk Timing portfolio allocation strategy.

Cross-sectionally reweights assets inversely to trailing realised variance
(or by mean return / variance for the reward-to-risk variant), exploiting
volatility clustering rather than any price trend signal.

Example:
    from strategies.core import AssetStrategy
    from strategies.volatility_timing import VolatilityTimingStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
    ]
    vol_timing = VolatilityTimingStrategy(underlying=assets, lookback_days=63, mode='vol_timing')
"""

import pandas as pd
import numpy as np
from typing import List, Literal
import logging

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class VolatilityTimingStrategy(AllocationStrategy):
    """
    Volatility / Reward-to-Risk Timing allocation strategy.

    Two modes:
    1. "vol_timing": Weights inversely to trailing realised variance.
       weight_i ∝ 1 / variance_i (vol clustering exploitation)
    2. "reward_to_risk": Weights by trailing mean return / variance ratio,
       floored at zero (long-only). Falls back to equal weight if all floor to zero.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 63,
        mode: Literal["vol_timing", "reward_to_risk"] = "vol_timing",
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookback_days: Lookback for variance/return calculation (default 63)
            mode: "vol_timing" or "reward_to_risk" (default "vol_timing")
            name: Display name
        """
        super().__init__(underlying, name=name or f"Volatility Timing ({mode})")
        self.lookback_days = lookback_days
        self.mode = mode
        if mode not in ("vol_timing", "reward_to_risk"):
            raise ValueError(f"mode must be 'vol_timing' or 'reward_to_risk', got {mode}")

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Volatility Timing requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, self.lookback_days)
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for volatility timing: {len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        # Use trailing lookback window
        lookback_prices = prices.iloc[-self.lookback_days :]
        returns = lookback_prices.pct_change().dropna()

        if len(returns) < 5:
            raise ValueError(
                f"Insufficient returns for volatility timing: {len(returns)} < 5"
            )

        symbols = list(prices.columns)
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in symbols]

        if self.mode == "vol_timing":
            weights = self._calculate_vol_timing_weights(returns, symbols, index)
        else:  # reward_to_risk
            weights = self._calculate_reward_to_risk_weights(returns, symbols, index)

        return weights

    def _calculate_vol_timing_weights(
        self, returns: pd.DataFrame, symbols: list, index: list
    ) -> pd.Series:
        """Weight inversely to trailing variance."""
        variances = returns.var()
        variances[variances == 0] = 1e-10

        inv_var = 1.0 / variances
        weights_dict = (inv_var / inv_var.sum()).to_dict()

        weights = pd.Series(
            [weights_dict.get(s, 0.0) for s in symbols],
            index=index
        )

        logger.debug(
            f"Vol Timing (variances): {dict(variances.round(6))}. "
            f"Weights: {dict(weights.round(4))}"
        )

        return weights

    def _calculate_reward_to_risk_weights(
        self, returns: pd.DataFrame, symbols: list, index: list
    ) -> pd.Series:
        """Weight by max(0, mean_return / variance), floored at zero."""
        mean_returns = returns.mean()
        variances = returns.var()
        variances[variances == 0] = 1e-10

        # Reward-to-risk ratio, floored at zero (long-only)
        rtr_ratio = (mean_returns / variances).clip(lower=0.0)

        # If all floor to zero, fall back to equal weight
        if rtr_ratio.sum() == 0:
            logger.warning(
                "All reward-to-risk ratios floored to zero. Falling back to equal weight."
            )
            weights_dict = {s: 1.0 / len(symbols) for s in symbols}
        else:
            weights_dict = (rtr_ratio / rtr_ratio.sum()).to_dict()

        weights = pd.Series(
            [weights_dict.get(s, 0.0) for s in symbols],
            index=index
        )

        logger.debug(
            f"Reward-to-Risk (ratios): {dict(rtr_ratio.round(6))}. "
            f"Weights: {dict(weights.round(4))}"
        )

        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
