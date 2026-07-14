"""
Flexible Asset Allocation strategy (Keller & van Putten, 2012).

Monthly rebalance. Ranks each asset cross-sectionally on three factors:
1. Trailing total return (6-month lookback)
2. Realized volatility
3. Average pairwise correlation to other assets (lower is better for diversification)

Combined score via weighted ranking: score = w_R*rank_R + w_V*rank_V + w_C*rank_C.
Selects top N assets. Applies absolute-momentum gate: drop any selected asset with
negative trailing return; shift its weight to the safe asset (last asset in underlying).

Parameters
----------
lookback_days : int
    Lookback period for trailing return and correlation (default 84 = ~4 months).
top_n : int
    Number of top-ranked assets to select (default 3).
w_r : float
    Weight on return ranking (default 1.0).
w_v : float
    Weight on volatility ranking (default 0.5, inverted so low vol = high rank).
w_c : float
    Weight on correlation ranking (default 0.5, inverted so low corr = high rank).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class FlexibleAssetAllocationStrategy(AllocationStrategy):
    """
    Flexible Asset Allocation: multi-factor momentum + absolute momentum gate.

    Ranks assets by trailing return, realized volatility, and pairwise correlation.
    Selects top N, applies negative-return filter (drop to safe asset), equal-weights.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 84,
        top_n: int = 3,
        w_r: float = 1.0,
        w_v: float = 0.5,
        w_c: float = 0.5,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Flexible Asset Allocation (top_{top_n})",
        )
        self.lookback_days = lookback_days
        self.top_n = min(top_n, len(underlying))
        self.w_r = w_r
        self.w_v = w_v
        self.w_c = w_c

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        min_required = max(self.lookback_days + 10, 40)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        symbol_to_name = self._build_name_map()
        all_index = [symbol_to_name.get(s, s) for s in prices.columns]
        symbols = list(prices.columns)
        n = len(symbols)

        if n < 2:
            return self._equal_weight(prices)

        lookback_prices = prices.iloc[-self.lookback_days :]

        # Step 1: Trailing return ranking
        trailing_returns = (
            lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1
        )
        rank_r = trailing_returns.rank()

        # Step 2: Realized volatility ranking (inverse: low vol = high score)
        returns = lookback_prices.pct_change().dropna()
        realized_vols = returns.std()
        realized_vols[realized_vols == 0] = 1e-10
        rank_v = (-realized_vols).rank()  # Negative so low vol gets high rank

        # Step 3: Average pairwise correlation ranking (inverse: low corr = high score)
        corr = np.array(returns.corr().values, dtype=float)  # writable copy
        # Set diagonal to nan to exclude self-correlation
        np.fill_diagonal(corr, np.nan)
        avg_corr = np.nanmean(np.abs(corr), axis=1)  # Average absolute correlation
        avg_corr_series = pd.Series(avg_corr, index=symbols)
        rank_c = (-avg_corr_series).rank()  # Negative so low corr gets high rank

        # Step 4: Combined score
        combined_score = (
            self.w_r * rank_r + self.w_v * rank_v + self.w_c * rank_c
        )
        ranked = combined_score.sort_values(ascending=False)
        selected = ranked.index[: self.top_n].tolist()

        logger.debug(
            f"FAA: return_ranks={dict(rank_r.round(2))}, "
            f"vol_ranks={dict(rank_v.round(2))}, "
            f"corr_ranks={dict(rank_c.round(2))}, "
            f"combined={dict(ranked.round(2))}, selected={selected}"
        )

        # Step 5: Absolute momentum gate — drop negative performers
        safe_symbol = symbols[-1]  # Last asset is safe asset (bond)
        safe_name = symbol_to_name.get(safe_symbol, safe_symbol)

        passed = []
        dropped_weight = 0.0
        for sym in selected:
            if trailing_returns[sym] >= 0:
                passed.append(sym)
            else:
                dropped_weight += 1.0 / len(selected)

        logger.debug(
            f"FAA: selected={selected}, trailing_returns={dict(trailing_returns[selected].round(4))}, "
            f"passed (positive momentum)={passed}, dropped_weight_to_safe={dropped_weight:.4f}"
        )

        # Step 6: Build weights
        weights = pd.Series(0.0, index=all_index)

        if passed:
            # Equal-weight among survivors
            per_asset_weight = (1.0 - dropped_weight) / len(passed)
            for sym in passed:
                name = symbol_to_name.get(sym, sym)
                weights[name] = per_asset_weight

        # Allocate dropped weight to safe asset
        weights[safe_name] += dropped_weight

        # If all were filtered, hold 100% safe asset
        if weights.sum() == 0:
            weights[safe_name] = 1.0

        return weights

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    # ------------------------------------------------------------------

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
