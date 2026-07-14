"""
National-Market Mean Reversion strategy (Balvers, Wu & Gilliland 2000).

Cross-sectional relative-value reversion of regional/country equity indices
toward a world benchmark. Ranks each equity ETF by its log-price deviation
from the benchmark (z-score over a long lookback), identifying those trading
cheap relative to their long-run mean. Overweights the cheapest subset,
zeros the most expensive. Exploits slow mean reversion toward fundamentals.

Implementation
--------------
1. Build a world benchmark as equal-weight of all equity holdings.
2. For each equity ETF, compute log price ratio to benchmark.
3. Z-score the ratio over a long lookback (default 756 trading days ≈ 36m).
4. Rank by z-score: most negative (cheapest) = strongest buy signal.
5. Select and equal-weight the bottom held_frac (default 0.5) of equities.
6. Zero the most expensive; place remaining weight on neutral/selected.

Parameters
----------
lookback_days : int
    Lookback for z-score of relative price ratio (default 756 ≈ 36 months).
held_frac : float
    Fraction of cheapest equity assets to hold (default 0.5).
equity_symbols : list of str
    Symbols classified as equity (e.g. VUSA, EQQQ, IMEU, IIND).
benchmark_symbol : str, optional
    Explicit benchmark symbol. If None, use equal-weight of all equity_symbols.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class NationalMarketMeanReversionStrategy(AllocationStrategy):
    """
    National-market mean reversion: exploit cross-sectional relative-value
    reversion of regional equity indices toward a world benchmark.

    Identifies countries/regions trading cheap relative to their long-run
    relationship with the global index and overweights them.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 756,
        held_frac: float = 0.5,
        equity_symbols: Optional[List[str]] = None,
        benchmark_symbol: Optional[str] = None,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
            lookback_days: Lookback for z-score calculation (default 756 ≈ 36m).
            held_frac: Fraction of cheapest equities to hold (default 0.5).
            equity_symbols: Symbols to include as equity (e.g. VUSA, EQQQ, IMEU, IIND).
                           If None, infer from underlying.
            benchmark_symbol: Explicit benchmark (e.g. IWRD). If None, use
                             equal-weight of equity_symbols.
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"National-Market Mean Reversion ({lookback_days}d)",
        )
        self.lookback_days = lookback_days
        self.held_frac = max(0.0, min(1.0, held_frac))
        self.equity_symbols = equity_symbols or []
        self.benchmark_symbol = benchmark_symbol

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        # Require sufficient history
        min_required = max(30, self.lookback_days + 5)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < self.lookback_days:
            return self._equal_weight(prices)

        # Identify equity symbols available in prices
        available_equity = [s for s in self.equity_symbols if s in prices.columns]
        if not available_equity:
            # If no explicit equity_symbols given, treat all non-benchmark as equity
            available_equity = [s for s in prices.columns if s != self.benchmark_symbol]

        if len(available_equity) < 2:
            return self._equal_weight(prices)

        # Build or identify benchmark
        if self.benchmark_symbol and self.benchmark_symbol in prices.columns:
            benchmark_price = prices[self.benchmark_symbol]
        else:
            # Equal-weight composite benchmark
            equity_prices = prices[[s for s in available_equity if s in prices.columns]]
            benchmark_price = equity_prices.mean(axis=1)

        # Compute log price ratios (relative price)
        lookback_prices = prices.iloc[-self.lookback_days :].copy()
        lookback_prices = lookback_prices.ffill(limit=3).dropna()

        if len(lookback_prices) < 30:
            return self._equal_weight(prices)

        # Get benchmark prices for the lookback window
        if self.benchmark_symbol and self.benchmark_symbol in prices.columns:
            lookback_benchmark = prices[self.benchmark_symbol].iloc[-self.lookback_days :]
        else:
            equity_prices = prices[
                [s for s in available_equity if s in prices.columns]
            ].iloc[-self.lookback_days :]
            lookback_benchmark = equity_prices.mean(axis=1)

        lookback_benchmark = lookback_benchmark.ffill(limit=3).dropna()

        # Compute z-scores of relative price ratio for each equity
        z_scores = {}
        for equity_sym in available_equity:
            if equity_sym not in lookback_prices.columns:
                continue

            equity_prices = lookback_prices[equity_sym]
            if len(equity_prices) < 2 or len(lookback_benchmark) < 2:
                continue

            # Align indices
            common_idx = equity_prices.index.intersection(lookback_benchmark.index)
            if len(common_idx) < 2:
                continue

            equity_aligned = equity_prices[common_idx]
            benchmark_aligned = lookback_benchmark[common_idx]

            # Log ratio
            ratio = np.log(equity_aligned / benchmark_aligned)

            # Z-score
            ratio_mean = ratio.mean()
            ratio_std = ratio.std()
            if ratio_std < 1e-8:
                z_score = 0.0
            else:
                z_score = (ratio.iloc[-1] - ratio_mean) / ratio_std

            z_scores[equity_sym] = z_score

        logger.debug(
            f"NMMR: z-scores {dict(sorted(z_scores.items(), key=lambda x: x[1])[:5])}"
        )

        if not z_scores:
            return self._equal_weight(prices)

        # Rank by z-score (most negative = cheapest first)
        ranked = sorted(z_scores.items(), key=lambda x: x[1])

        # Select bottom held_frac
        n_to_hold = max(1, int(len(ranked) * self.held_frac))
        selected = [sym for sym, _ in ranked[:n_to_hold]]

        logger.debug(f"NMMR: holding {n_to_hold}/{len(ranked)} equities: {selected}")

        # Build weight vector: equal-weight selected, zero others
        symbol_to_name = self._build_name_map()
        all_symbols = list(prices.columns)
        index = [symbol_to_name.get(s, s) for s in all_symbols]

        weights = pd.Series(0.0, index=index)
        if selected:
            per_asset = 1.0 / len(selected)
            for sym in selected:
                name = symbol_to_name.get(sym, sym)
                weights[name] = per_asset

        return weights

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for sym in strategy.get_symbols():
                symbol_to_name[sym] = strategy.name
        return symbol_to_name

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
