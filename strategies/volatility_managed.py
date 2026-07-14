"""
Volatility-Managed Portfolio (Moreira & Muir, 2017).

Scales exposure to a risky base sleeve inversely with its recent realized
*variance* (not its volatility, and not toward a constant target as a plain
vol-target overlay does): exposure_t = clip(target_var / realized_var_{t-1}, 0, 1).
Moreira & Muir (2017, Journal of Finance 72(4)) show that reducing risk when
volatility is high — because expected returns do not rise proportionally with
volatility — raises Sharpe ratios and produces positive alpha across many
factors. This is a long-only, no-leverage version: exposure is capped at 1 and
the un-invested remainder is parked in the safe asset (bonds).

The risky base is an equal-weight blend of all non-safe assets in the universe;
the safe asset is designated by `safe_symbol` (default VUTY).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class VolatilityManagedStrategy(AllocationStrategy):
    """
    Volatility-managed long-only allocation.

    Parameters:
        lookback_days: window for realized-variance estimate (default 63, ~3m).
        target_vol: annualized volatility whose square is the target variance
            (default 0.10). exposure = clip(target_vol**2 / realized_var, 0, 1).
        safe_symbol: asset that absorbs the un-invested remainder (default VUTY).
    """

    TRADING_DAYS = 252

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 63,
        target_vol: float = 0.10,
        safe_symbol: str = "VUTY",
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Volatility-Managed")
        self.lookback_days = lookback_days
        self.target_vol = target_vol
        self.safe_symbol = safe_symbol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"VolatilityManaged requires at least 2 assets, got {len(prices.columns)}."
            )

        prices = prices.ffill(limit=3).dropna()
        symbols = list(prices.columns)

        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        names = [symbol_to_name.get(s, s) for s in symbols]

        # Risky base = equal weight of all non-safe assets present.
        safe = self.safe_symbol if self.safe_symbol in symbols else None
        risky = [s for s in symbols if s != safe]
        if not risky:
            return pd.Series(1.0 / len(symbols), index=names)

        returns = prices[risky].pct_change().dropna()
        if len(returns) < 20:
            # Not enough history: hold the risky base equal-weight.
            base = {s: 1.0 / len(risky) for s in risky}
            return pd.Series([base.get(s, 0.0) for s in symbols], index=names)

        base_ret = returns.tail(self.lookback_days).mean(axis=1)  # equal-weight base
        realized_var = base_ret.var() * self.TRADING_DAYS
        target_var = self.target_vol ** 2
        if realized_var <= 0:
            exposure = 1.0
        else:
            exposure = float(np.clip(target_var / realized_var, 0.0, 1.0))

        w = {s: exposure / len(risky) for s in risky}
        if safe is not None:
            w[safe] = w.get(safe, 0.0) + (1.0 - exposure)
        else:
            # No safe asset in universe: re-normalize risky (no cash equivalent).
            total = sum(w.values())
            if total > 0:
                w = {s: v / total for s, v in w.items()}

        return pd.Series([w.get(s, 0.0) for s in symbols], index=names)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
