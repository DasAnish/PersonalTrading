"""
Risk-Adjusted (Sharpe-Ratio) Momentum.

Cross-sectional momentum that ranks assets by their trailing reward-to-risk
(Sharpe) ratio rather than raw past return (Rachev, Jasic, Stoyanov & Fabozzi,
2007, "Momentum strategies based on reward-risk stock selection criteria",
Journal of Banking & Finance 31(8)). Scaling past return by its own volatility
favours assets whose gains were steady rather than lucky, which the paper finds
improves the consistency of momentum profits. Long-only: hold the top_n assets
by trailing Sharpe, equal-weighted, with an absolute-momentum gate to a safe
asset when the best trailing Sharpe is non-positive.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class SharpeMomentumStrategy(AllocationStrategy):
    """
    Sharpe-ratio (risk-adjusted) momentum.

    Parameters:
        lookback_days: window for trailing Sharpe (default 126, ~6m).
        top_n: number of highest-Sharpe assets to hold (default 3).
        safe_symbol: absolute-momentum fallback asset (default VUTY).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 126,
        top_n: int = 3,
        safe_symbol: str = "VUTY",
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Sharpe Momentum")
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.safe_symbol = safe_symbol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"SharpeMomentum requires 2+ assets, got {len(prices.columns)}."
            )
        prices = prices.ffill(limit=3).dropna()
        symbols = list(prices.columns)
        symbol_to_name = {}
        for strat in self.underlying:
            for sym in strat.get_symbols():
                symbol_to_name[sym] = strat.name
        names = [symbol_to_name.get(s, s) for s in symbols]

        returns = prices.pct_change().dropna().tail(self.lookback_days)
        if len(returns) < 20:
            return pd.Series(1.0 / len(symbols), index=names)

        mean = returns.mean()
        std = returns.std().replace(0, np.nan)
        sharpe = (mean / std).dropna()  # per-asset trailing Sharpe

        if sharpe.empty:
            return pd.Series(1.0 / len(symbols), index=names)

        ranked = sharpe.sort_values(ascending=False)
        n = min(self.top_n, len(ranked))
        selected = list(ranked.index[:n])
        # Absolute-momentum gate: keep only positive-Sharpe picks; freed weight
        # goes to the safe asset.
        positive = [s for s in selected if sharpe[s] > 0]

        w = {s: 0.0 for s in symbols}
        if positive:
            for s in positive:
                w[s] = 1.0 / n  # equal weight over the top_n slots
            freed = (n - len(positive)) / n
        else:
            freed = 1.0
        if freed > 0:
            safe = self.safe_symbol if self.safe_symbol in symbols else None
            if safe is not None:
                w[safe] = w.get(safe, 0.0) + freed
            else:
                # No safe asset: re-normalize whatever is held, else equal weight.
                total = sum(w.values())
                if total > 0:
                    w = {s: v / total for s, v in w.items()}
                else:
                    w = {s: 1.0 / len(symbols) for s in symbols}

        return pd.Series([w.get(s, 0.0) for s in symbols], index=names)

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
