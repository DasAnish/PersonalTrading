"""
Canary-Gated Momentum Turning Points — signal-level DAA x MTP combination.

Combines the breadth-momentum canary gate of Defensive Asset Allocation
(Keller & Keuning 2018) with the cycle exposure of Momentum Turning Points
(Garg, Goulding, Harvey & Mazzoleni, JFE 2023) inside one signal stack.
The canary breadth b (fraction of canary assets with positive 13612W-style
fast momentum) scales the invested fraction of the MTP allocation; the
remainder goes to the safe asset. Signal-level combination, per the
2026-07-19 finding that blending finished portfolios dilutes returns
while combining signals preserves them.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


def _fast_momentum(prices: pd.DataFrame, symbol: str) -> float:
    """Keller 13612W-style fast momentum: weighted 1/3/6/12m returns."""
    out = 0.0
    for months, weight in ((1, 12.0), (3, 4.0), (6, 2.0), (12, 1.0)):
        days = min(len(prices) - 1, months * 21)
        if days < 1:
            continue
        out += weight * (prices[symbol].iloc[-1] / prices[symbol].iloc[-days - 1] - 1)
    return out


class CanaryGatedMTPStrategy(AllocationStrategy):
    """
    MTP allocation scaled by canary breadth.

    1. Canary breadth b = fraction of ``canary_symbols`` (present in the
       price frame) with positive fast momentum.
    2. MTP cycle exposure per risky asset (slow 252d x fast 21d signals,
       inverse-vol weighted) forms the risky allocation.
    3. Final weights = b * risky allocation + (1 - b) * safe asset.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        slow_days: int = 252,
        fast_days: int = 21,
        vol_window_days: int = 63,
        correction_exposure: float = 0.5,
        rebound_exposure: float = 0.5,
        canary_symbols: List[str] = None,
        safe_symbol: str = "VUTY",
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Canary-Gated MTP")
        self.slow_days = slow_days
        self.fast_days = fast_days
        self.vol_window_days = vol_window_days
        self.correction_exposure = correction_exposure
        self.rebound_exposure = rebound_exposure
        self.canary_symbols = canary_symbols or ["IIND", "AGGU"]
        self.safe_symbol = safe_symbol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError("Canary-Gated MTP requires at least 2 assets.")

        min_required = max(self.slow_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for canary-gated MTP: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        canaries = [s for s in self.canary_symbols if s in prices.columns]
        if canaries:
            breadth = sum(
                1 for s in canaries if _fast_momentum(prices, s) > 0
            ) / len(canaries)
        else:
            logger.warning("Canary-Gated MTP: no canary symbols present, b=1.")
            breadth = 1.0

        risky_cols = [
            c
            for c in prices.columns
            if c != self.safe_symbol and c not in canaries
        ] or list(prices.columns)

        slow_window = prices.iloc[-self.slow_days :]
        fast_window = prices.iloc[-self.fast_days :]
        slow_ret = slow_window.iloc[-1] / slow_window.iloc[0] - 1
        fast_ret = fast_window.iloc[-1] / fast_window.iloc[0] - 1

        exposure = pd.Series(0.0, index=risky_cols)
        for symbol in risky_cols:
            sp, fp = slow_ret[symbol] > 0, fast_ret[symbol] > 0
            if sp and fp:
                exposure[symbol] = 1.0
            elif sp:
                exposure[symbol] = self.correction_exposure
            elif fp:
                exposure[symbol] = self.rebound_exposure

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        if exposure.sum() > 0 and breadth > 0:
            vol_returns = (
                prices[risky_cols]
                .iloc[-self.vol_window_days :]
                .pct_change()
                .dropna()
            )
            vols = vol_returns.std()
            vols[vols == 0] = 1e-10
            raw = exposure / vols
            raw = raw / raw.sum() * breadth
            for symbol, w in raw.items():
                weights[symbol_to_name.get(symbol, symbol)] += w

        safe_share = 1.0 - weights.sum()
        if safe_share > 0:
            safe = (
                self.safe_symbol
                if self.safe_symbol in prices.columns
                else prices.columns[0]
            )
            weights[symbol_to_name.get(safe, safe)] += safe_share

        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return max(self.slow_days, self.vol_window_days) + 10
