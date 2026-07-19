"""
Momentum Crash Management — bear-state exposure scaling for momentum.

Based on Daniel & Moskowitz (2016), "Momentum Crashes", Journal of
Financial Economics 122(2): momentum crashes are forecastable, occurring
in panic states (multi-year market decline + high ex-ante volatility)
when the momentum portfolio is implicitly short the market rebound.
Long-only adaptation: scale a top-N fast momentum sleeve down in bear
states (to 0 in bear+panic), diverting the freed weight to equal weight
across the universe for rebound participation.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class MomentumCrashManagedStrategy(AllocationStrategy):
    """
    Top-N momentum with panic-state de-scaling.

    1. Bear = mean trailing ``bear_days`` return of ``market_symbols`` < 0.
    2. Panic = trailing ``vol_days`` market vol > trailing ``vol_ref_days``
       median of that vol.
    3. Momentum sleeve exposure: 1.0 normal, 0.5 bear, 0.0 bear+panic;
       remainder equal-weighted across all assets.
    4. Momentum sleeve = top ``top_n`` by trailing ``signal_days`` return,
       inverse-vol weighted.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        signal_days: int = 21,
        top_n: int = 2,
        bear_days: int = 504,
        vol_days: int = 63,
        vol_ref_days: int = 252,
        vol_window_days: int = 63,
        market_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Momentum Crash Managed")
        self.signal_days = signal_days
        self.top_n = top_n
        self.bear_days = bear_days
        self.vol_days = vol_days
        self.vol_ref_days = vol_ref_days
        self.vol_window_days = vol_window_days
        self.market_symbols = market_symbols or ["VUSA", "IWRD", "EQQQ"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError("Momentum Crash Managed requires >= 2 assets.")

        min_required = self.bear_days + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for momentum crash managed: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        market = [s for s in self.market_symbols if s in prices.columns]
        if market:
            bear_window = prices[market].iloc[-self.bear_days :]
            bear = (bear_window.iloc[-1] / bear_window.iloc[0] - 1).mean() < 0
            mkt_ret = prices[market].mean(axis=1).pct_change().dropna()
            recent_vol = mkt_ret.iloc[-self.vol_days :].std()
            ref = mkt_ret.iloc[-self.vol_ref_days :].rolling(self.vol_days).std()
            panic = recent_vol > ref.median()
        else:
            bear = panic = False

        if bear and panic:
            momentum_share = 0.0
        elif bear:
            momentum_share = 0.5
        else:
            momentum_share = 1.0

        signal_window = prices.iloc[-self.signal_days :]
        signal = signal_window.iloc[-1] / signal_window.iloc[0] - 1
        winners = signal.nlargest(min(self.top_n, len(signal))).index

        vols = prices.iloc[-self.vol_window_days :].pct_change().dropna().std()
        vols[vols == 0] = 1e-10

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        if momentum_share > 0:
            inv_vol = 1.0 / vols[winners]
            alloc = inv_vol / inv_vol.sum() * momentum_share
            for symbol, w in alloc.items():
                weights[symbol_to_name.get(symbol, symbol)] += w

        ew_share = 1.0 - momentum_share
        if ew_share > 0:
            per = ew_share / len(prices.columns)
            for symbol in prices.columns:
                weights[symbol_to_name.get(symbol, symbol)] += per

        total = weights.sum()
        if total > 0:
            weights = weights / total
        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return self.bear_days + 10
