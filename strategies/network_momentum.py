"""
Network Momentum trend-following strategy.

Based on Li & Ferreira (2025), "Follow the Leader: Enhancing Systematic
Trend-Following Using Network Momentum" (arXiv 2501.07135). Momentum
spillover: trends propagate with a lag between correlated markets, so a
correlation-weighted average of neighbours' trailing returns carries
incremental signal beyond an asset's own trend. Exposure requires
agreement between the own-trend and network-trend signals.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class NetworkMomentumStrategy(AllocationStrategy):
    """
    Own-trend x network-trend allocation.

    1. Trailing ``lookback_days`` return per asset (own signal sign).
    2. Neighbours of asset i = assets with trailing correlation >
       ``corr_threshold``; network signal = sign of correlation-weighted
       mean of neighbours' trailing returns. No neighbours -> own signal
       decides alone.
    3. Exposure: both positive 1.0; exactly one 0.5; both non-positive 0.
    4. Weights proportional to exposure / trailing ``vol_window_days`` vol,
       normalised; all-zero fallback holds ``defensive_symbols`` present.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        vol_window_days: int = 63,
        corr_threshold: float = 0.4,
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Network Momentum")
        self.lookback_days = lookback_days
        self.vol_window_days = vol_window_days
        self.corr_threshold = corr_threshold
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError("Network Momentum requires at least 2 assets.")

        min_required = max(self.lookback_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for network momentum: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        window = prices.iloc[-self.lookback_days :]
        own_ret = window.iloc[-1] / window.iloc[0] - 1
        corr = window.pct_change().dropna().corr()

        exposure = pd.Series(0.0, index=prices.columns)
        for symbol in prices.columns:
            own_positive = own_ret[symbol] > 0
            neighbour_corr = corr[symbol].drop(symbol)
            neighbours = neighbour_corr[neighbour_corr > self.corr_threshold]
            if neighbours.empty:
                exposure[symbol] = 1.0 if own_positive else 0.0
                continue
            network_ret = (own_ret[neighbours.index] * neighbours).sum() / (
                neighbours.sum()
            )
            network_positive = network_ret > 0
            exposure[symbol] = (int(own_positive) + int(network_positive)) / 2.0

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]

        if exposure.sum() == 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            targets = defensive or list(prices.columns)
            logger.warning(
                "Network Momentum: no positive exposure, holding %s.", targets
            )
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
        return max(self.lookback_days, self.vol_window_days) + 10
