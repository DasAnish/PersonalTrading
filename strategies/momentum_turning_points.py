"""
Momentum Turning Points strategy — blended slow/fast time-series momentum.

Based on Garg, Goulding, Harvey & Mazzoleni (2023), "Momentum Turning
Points", Journal of Financial Economics 149. The intersection of a slow
(12m) and a fast (1m) time-series momentum signal defines four cycle
states per asset — Bull (+/+), Correction (+/-), Rebound (-/+) and
Bear (-/-). An intermediate-speed portfolio holds full exposure in Bull,
half exposure in Correction/Rebound (equal blend of the two signals) and
zero in Bear, which the paper shows earns a higher Sharpe with shallower
drawdowns than either speed alone.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MomentumTurningPointsStrategy(AllocationStrategy):
    """
    Blended slow/fast TSM allocation.

    1. Per asset: slow signal = sign of trailing ``slow_days`` return,
       fast signal = sign of trailing ``fast_days`` return.
    2. Exposure: both positive 1.0; mixed 0.5; both negative 0.0.
    3. Weights proportional to exposure / trailing ``vol_window_days``
       volatility, normalised to sum 1.
    4. If every asset is in Bear, hold the defensive assets present
       (``defensive_symbols``) equal-weight; if none present, equal
       weight everything (long-only, always invested).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        slow_days: int = 252,
        fast_days: int = 21,
        vol_window_days: int = 63,
        correction_exposure: float = 0.5,
        rebound_exposure: float = 0.5,
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(
            underlying, name=name or "Momentum Turning Points"
        )
        self.slow_days = slow_days
        self.fast_days = fast_days
        self.vol_window_days = vol_window_days
        self.correction_exposure = correction_exposure
        self.rebound_exposure = rebound_exposure
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 1:
            raise ValueError("Momentum Turning Points requires at least 1 asset.")

        min_required = max(self.slow_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for momentum turning points: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        slow_window = prices.iloc[-self.slow_days :]
        fast_window = prices.iloc[-self.fast_days :]
        slow_ret = slow_window.iloc[-1] / slow_window.iloc[0] - 1
        fast_ret = fast_window.iloc[-1] / fast_window.iloc[0] - 1

        # Cycle exposure: Bull 1.0, Correction (slow+/fast-)
        # correction_exposure, Rebound (slow-/fast+) rebound_exposure,
        # Bear 0.0
        exposure = pd.Series(0.0, index=prices.columns)
        exposure[(slow_ret > 0) & (fast_ret > 0)] = 1.0
        exposure[(slow_ret > 0) & (fast_ret <= 0)] = self.correction_exposure
        exposure[(slow_ret <= 0) & (fast_ret > 0)] = self.rebound_exposure

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]

        if exposure.sum() == 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            logger.warning(
                "Momentum Turning Points: all assets in Bear state, "
                "holding defensive assets %s.",
                defensive or "none — equal weight fallback",
            )
            weights = pd.Series(0.0, index=index)
            targets = defensive or list(prices.columns)
            for symbol in targets:
                weights[symbol_to_name.get(symbol, symbol)] = 1.0 / len(targets)
            return weights

        vol_returns = prices.iloc[-self.vol_window_days :].pct_change().dropna()
        vols = vol_returns.std()
        vols[vols == 0] = 1e-10

        raw = exposure / vols
        raw = raw / raw.sum()

        weights = pd.Series(0.0, index=index)
        for symbol in prices.columns:
            weights[symbol_to_name.get(symbol, symbol)] = raw[symbol]
        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return max(self.slow_days, self.vol_window_days) + 10
