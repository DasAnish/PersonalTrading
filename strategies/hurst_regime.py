"""
Hurst-Exponent Regime Filter — per-asset trend vs mean-reversion switching.

Grounded in Lo (1991), "Long-Term Memory in Stock Market Prices",
Econometrica 59(5) (rescaled-range analysis of long-range dependence).
The Hurst exponent H is estimated per asset from the scaling of aggregated
return volatility; persistent assets (H high) get a trend rule, and
anti-persistent assets (H low) get a short-horizon reversion rule, with a
neutral band absorbing estimation noise.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

_SCALES = (1, 2, 4, 8, 16)


def _hurst(returns: pd.Series) -> float:
    """Slope of log(std of k-day aggregated returns) vs log(k)."""
    stds = []
    for k in _SCALES:
        agg = returns.rolling(k).sum().dropna().iloc[::k]
        if len(agg) < 8 or agg.std() == 0:
            return 0.5
        stds.append(agg.std())
    slope, _ = np.polyfit(np.log(_SCALES), np.log(stds), 1)
    return float(slope)


class HurstRegimeStrategy(AllocationStrategy):
    """
    Per-asset rule switching on the Hurst exponent.

    H > ``trend_threshold``: trend rule (long iff trailing ``slow_days``
    return > 0). H < ``reversion_threshold``: reversion rule (full weight
    iff trailing ``fast_days`` return < 0, else half). Between: 0.5.
    Weights inverse-vol scaled; all-zero fallback holds defensives.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        slow_days: int = 252,
        fast_days: int = 21,
        vol_window_days: int = 63,
        trend_threshold: float = 0.55,
        reversion_threshold: float = 0.45,
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Hurst Regime Filter")
        self.lookback_days = lookback_days
        self.slow_days = slow_days
        self.fast_days = fast_days
        self.vol_window_days = vol_window_days
        self.trend_threshold = trend_threshold
        self.reversion_threshold = reversion_threshold
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 1:
            raise ValueError("Hurst Regime requires at least 1 asset.")

        min_required = max(self.lookback_days, self.slow_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for Hurst regime: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()
        daily = prices.iloc[-self.lookback_days :].pct_change().dropna()

        slow_window = prices.iloc[-self.slow_days :]
        fast_window = prices.iloc[-self.fast_days :]
        slow_ret = slow_window.iloc[-1] / slow_window.iloc[0] - 1
        fast_ret = fast_window.iloc[-1] / fast_window.iloc[0] - 1

        exposure = pd.Series(0.5, index=prices.columns)
        for symbol in prices.columns:
            h = _hurst(daily[symbol])
            if h > self.trend_threshold:
                exposure[symbol] = 1.0 if slow_ret[symbol] > 0 else 0.0
            elif h < self.reversion_threshold:
                exposure[symbol] = 1.0 if fast_ret[symbol] < 0 else 0.5

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]

        if exposure.sum() == 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            targets = defensive or list(prices.columns)
            weights = pd.Series(0.0, index=index)
            for symbol in targets:
                weights[symbol_to_name.get(symbol, symbol)] = 1.0 / len(targets)
            return weights

        vols = prices.iloc[-self.vol_window_days :].pct_change().dropna().std()
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
        return max(self.lookback_days, self.slow_days) + 10
