"""
Momentum Turning Points x Network confirmation — signal-level combination.

Combines the cycle exposure of MomentumTurningPointsStrategy (Garg,
Goulding, Harvey & Mazzoleni, JFE 2023) with the peer-spillover network
signal of Li & Ferreira (arXiv 2501.07135) inside one signal stack,
instead of blending the two finished portfolios (which dilutes toward the
mean). Two combination modes:

- ``combine="gate"``: exposure = cycle exposure * (0.5 + 0.5 * network
  agreement) — network disagreement halves exposure, never zeroes it.
- ``combine="average"``: exposure = mean of cycle exposure and network
  agreement (agreement in {0, 1}).
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MTPNetworkStrategy(AllocationStrategy):
    """Blended slow/fast cycle exposure with network-momentum confirmation."""

    def __init__(
        self,
        underlying: List[Strategy],
        slow_days: int = 252,
        fast_days: int = 21,
        vol_window_days: int = 63,
        corr_threshold: float = 0.4,
        correction_exposure: float = 0.5,
        rebound_exposure: float = 0.5,
        combine: str = "gate",
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "MTP x Network")
        self.slow_days = slow_days
        self.fast_days = fast_days
        self.vol_window_days = vol_window_days
        self.corr_threshold = corr_threshold
        self.correction_exposure = correction_exposure
        self.rebound_exposure = rebound_exposure
        if combine not in ("gate", "average"):
            raise ValueError(f"combine must be 'gate' or 'average', got {combine!r}")
        self.combine = combine
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError("MTP x Network requires at least 2 assets.")

        min_required = max(self.slow_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for MTP x Network: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        slow_window = prices.iloc[-self.slow_days :]
        fast_window = prices.iloc[-self.fast_days :]
        slow_ret = slow_window.iloc[-1] / slow_window.iloc[0] - 1
        fast_ret = fast_window.iloc[-1] / fast_window.iloc[0] - 1
        corr = slow_window.pct_change().dropna().corr()

        cycle = pd.Series(0.0, index=prices.columns)
        cycle[(slow_ret > 0) & (fast_ret > 0)] = 1.0
        cycle[(slow_ret > 0) & (fast_ret <= 0)] = self.correction_exposure
        cycle[(slow_ret <= 0) & (fast_ret > 0)] = self.rebound_exposure

        exposure = pd.Series(0.0, index=prices.columns)
        for symbol in prices.columns:
            neighbour_corr = corr[symbol].drop(symbol)
            neighbours = neighbour_corr[neighbour_corr > self.corr_threshold]
            if neighbours.empty:
                network_agree = 1.0  # no network info — cycle signal decides
            else:
                network_ret = (slow_ret[neighbours.index] * neighbours).sum() / (
                    neighbours.sum()
                )
                network_agree = 1.0 if network_ret > 0 else 0.0
            if self.combine == "gate":
                exposure[symbol] = cycle[symbol] * (0.5 + 0.5 * network_agree)
            else:
                exposure[symbol] = (cycle[symbol] + network_agree) / 2.0

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]

        if exposure.sum() == 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            targets = defensive or list(prices.columns)
            weights = pd.Series(0.0, index=index)
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
