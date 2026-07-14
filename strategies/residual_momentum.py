"""
Residual (Idiosyncratic) Momentum allocation strategy.

Based on Blitz, Huij & Martens (2011). Ranks assets on residual return
(after stripping beta against a market benchmark) rather than total return.

Signal: For each asset, regress trailing returns on a broad-market benchmark
(IWRD as the market proxy) over a residual_window (e.g. 24 months) to obtain
beta-adjusted residuals. Compute momentum score = mean residual over formation
window (e.g. 12 months, skipping last 1 month) / std(residuals) — a t-stat-like
information-ratio scaling.

Rebalance: Monthly. Portfolio construction: long-only — rank all assets by
residual momentum score, overweight top fraction (default 0.4), zero-weight
the rest. Equal-weight within held set.

Key parameters:
- residual_window: days for market-model regression (default 504 = ~24m)
- formation_window: days for momentum score calculation (default 252 = ~12m)
- skip_days: days to skip from current date (default 21 = ~1m)
- top_frac: fraction of assets to hold (default 0.4)
- market_benchmark: 'IWRD' or 'equal_weight' composite of equity ETFs
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class ResidualMomentumStrategy(AllocationStrategy):
    """
    Residual (Idiosyncratic) Momentum allocation strategy.

    Ranks assets by beta-adjusted residuals from a market-model regression,
    rather than raw total returns. The residual signal isolates behavioural
    underreaction while neutralising incidental factor exposure.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        residual_window: int = 504,
        formation_window: int = 252,
        skip_days: int = 21,
        top_frac: float = 0.4,
        market_benchmark: str = "IWRD",
        name: Optional[str] = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            residual_window: Days for market-model regression (default 504 = ~24m)
            formation_window: Days for momentum score calc (default 252 = ~12m)
            skip_days: Days to skip from current (default 21 = ~1m)
            top_frac: Fraction of assets to hold (default 0.4)
            market_benchmark: Benchmark symbol for residuals (default 'IWRD')
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Residual Momentum (top {int(top_frac*100)}%)",
        )
        self.residual_window = residual_window
        self.formation_window = formation_window
        self.skip_days = skip_days
        self.top_frac = top_frac
        self.market_benchmark = market_benchmark

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Residual Momentum requires at least 2 assets, received {len(prices.columns)}."
            )

        min_required = max(30, self.residual_window + self.skip_days)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()

        # Get market benchmark (IWRD if available, else equal-weight composite)
        benchmark_prices = self._get_benchmark(prices)
        if benchmark_prices is None:
            logger.warning("Could not compute market benchmark; using equal-weight fallback")
            return self._equal_weight(prices)

        # Calculate residual momentum scores for each asset
        scores = {}
        for symbol in prices.columns:
            try:
                score = self._residual_momentum_score(
                    prices[symbol], benchmark_prices
                )
                scores[symbol] = score
            except Exception as e:
                logger.debug(f"Could not compute residual momentum for {symbol}: {e}")
                scores[symbol] = np.nan

        # Filter valid scores
        valid_scores = {k: v for k, v in scores.items() if not np.isnan(v)}

        if not valid_scores:
            logger.warning("No valid residual momentum scores; using equal-weight fallback")
            return self._equal_weight(prices)

        # Rank and select top fraction
        ranked = sorted(valid_scores.items(), key=lambda x: x[1], reverse=True)
        num_hold = max(1, int(len(ranked) * self.top_frac))
        selected_symbols = [symbol for symbol, _ in ranked[:num_hold]]

        logger.debug(
            f"Residual Momentum scores: {dict((k, v) for k, v in ranked)}. "
            f"Selected {num_hold}/{len(ranked)}: {selected_symbols}"
        )

        # Equal-weight among held assets
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        equal_weight_value = 1.0 / len(selected_symbols)
        for symbol in selected_symbols:
            name = symbol_to_name.get(symbol, symbol)
            weights[name] = equal_weight_value

        return weights

    def _get_benchmark(self, prices: pd.DataFrame) -> Optional[pd.Series]:
        """Get market benchmark timeseries (IWRD if available, else equal-weight)."""
        if self.market_benchmark in prices.columns:
            return prices[self.market_benchmark]

        # Fall back to equal-weight composite of available assets
        # (prefer VUSA, EQQQ, IWRD if present)
        equity_symbols = [s for s in prices.columns if s in ["VUSA", "EQQQ", "IWRD"]]
        if not equity_symbols:
            return None

        return prices[equity_symbols].mean(axis=1)

    def _residual_momentum_score(
        self, asset_prices: pd.Series, benchmark_prices: pd.Series
    ) -> float:
        """
        Calculate residual momentum score for a single asset.

        Steps:
        1. Regress asset returns on benchmark returns over residual_window
        2. Extract residuals
        3. Calculate mean residual / std(residuals) over formation_window with skip
        """
        # Ensure aligned dates
        common_dates = asset_prices.index.intersection(benchmark_prices.index)
        if len(common_dates) < max(30, self.residual_window):
            return np.nan

        asset_ret = asset_prices[common_dates].pct_change().dropna()
        bench_ret = benchmark_prices[common_dates].pct_change().dropna()

        # Align on common dates
        common_ret_dates = asset_ret.index.intersection(bench_ret.index)
        asset_ret = asset_ret[common_ret_dates]
        bench_ret = bench_ret[common_ret_dates]

        if len(asset_ret) < max(30, self.residual_window):
            return np.nan

        # Regression over residual_window
        regr_prices = len(asset_ret) - self.residual_window
        if regr_prices < 1:
            return np.nan

        regr_slice = slice(regr_prices, None)
        asset_regr = asset_ret.iloc[regr_slice]
        bench_regr = bench_ret.iloc[regr_slice]

        # Market-model regression: y ~ x
        slope, _, _, _, _ = stats.linregress(bench_regr, asset_regr)

        # Residuals: actual return - expected return
        fitted = slope * bench_regr
        residuals = asset_regr - fitted

        # Score over formation_window with skip_days
        form_start = max(0, len(residuals) - self.formation_window)
        form_end = max(0, len(residuals) - self.skip_days)

        if form_end <= form_start:
            return np.nan

        formation_residuals = residuals.iloc[form_start:form_end]

        if len(formation_residuals) < 20:
            return np.nan

        mean_residual = formation_residuals.mean()
        std_residual = formation_residuals.std()

        if std_residual == 0:
            return np.nan

        # Information-ratio like score
        score = mean_residual / std_residual

        return score

    def get_strategy_lookback(self) -> int:
        return self.residual_window + self.skip_days

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
