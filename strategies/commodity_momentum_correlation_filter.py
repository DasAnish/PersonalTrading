"""
Commodity Momentum with Correlation Filter strategy.

Based on Fuertes/Miffre/Rallis momentum work + correlation filtering.
Monthly rebalance.

Ranks commodities cross-sectionally by trailing return over lookback window.
Then applies a correlation filter: down-weight or exclude high-correlation names
so the held basket favours low-correlation winners.

Approach: rank by momentum, keep top-k by momentum, then from those k, select the
top_n with lowest average pairwise correlation to the rest of the universe.
Equal-weight held names. If all trailing returns negative, hold equal-weight fallback.

Parameters
----------
lookback_days : int
    Lookback period for trailing return and correlation (default 126 = ~6 months).
top_k : int
    Initial momentum ranking cutoff before correlation filter (default 4).
top_n : int
    Final number of assets to hold after correlation filter (default 2).
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class CommodityMomentumCorrelationStrategy(AllocationStrategy):
    """
    Commodity Momentum + Correlation Filter: rank by momentum, filter by correlation.

    Selects high-momentum assets with low correlation to the broader basket,
    favoring diversification within momentum winners.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 126,
        top_k: int = 4,
        top_n: int = 2,
        name: str = None,
    ):
        super().__init__(
            underlying=underlying,
            name=name or f"Commodity Momentum Correlation Filter (top_{top_n})",
        )
        self.lookback_days = lookback_days
        self.top_k = top_k
        self.top_n = min(top_n, len(underlying))

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

        # Step 1: Rank by trailing return
        trailing_returns = (
            lookback_prices.iloc[-1] / lookback_prices.iloc[0] - 1
        )
        ranked_momentum = trailing_returns.sort_values(ascending=False)

        # Step 2: Clip to top_k momentum candidates
        candidates = ranked_momentum.index[: self.top_k].tolist()

        logger.debug(
            f"CMF: momentum_rankings={dict(ranked_momentum.round(4))}, "
            f"top_k_candidates={candidates}"
        )

        # Step 3: Compute pairwise correlations over entire universe
        returns = lookback_prices.pct_change().dropna()
        corr = returns.corr().values  # n x n correlation matrix

        # For each candidate, compute average absolute correlation to all assets
        candidate_indices = [symbols.index(c) for c in candidates]
        avg_corrs = {}
        for c_idx, c_sym in zip(candidate_indices, candidates):
            # Average absolute correlation to all other assets
            row_corr = np.abs(corr[c_idx, :])
            # Exclude self-correlation
            row_corr[c_idx] = np.nan
            avg_corr = np.nanmean(row_corr)
            avg_corrs[c_sym] = avg_corr

        # Step 4: From candidates, select top_n with lowest correlation
        sorted_by_corr = sorted(avg_corrs.items(), key=lambda x: x[1])
        selected = [sym for sym, _ in sorted_by_corr[: self.top_n]]

        logger.debug(
            f"CMF: avg_correlations={{{', '.join(f'{s}:{c:.4f}' for s,c in sorted_by_corr)}}}, "
            f"selected_by_low_correlation={selected}"
        )

        # Step 5: Check if all selected assets have negative momentum
        selected_returns = trailing_returns[selected]
        if (selected_returns < 0).all():
            # All negative: fall back to equal weight
            logger.debug(
                f"CMF: all selected have negative returns {dict(selected_returns.round(4))}, "
                f"falling back to equal weight"
            )
            return self._equal_weight(prices)

        # Step 6: Build equal-weight portfolio for selected assets
        weights = pd.Series(0.0, index=all_index)
        per_asset_weight = 1.0 / len(selected)
        for sym in selected:
            name = symbol_to_name.get(sym, sym)
            weights[name] = per_asset_weight

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
