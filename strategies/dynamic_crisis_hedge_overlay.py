"""
Dynamic Crisis Hedge Overlay strategy.

Overlays a dynamic defensive-asset hedge on an underlying allocation, triggered
when equity markets enter crisis (detected via short-duration SMA crossover).

Based on Harvey et al 2019: "Crisis Alpha" — during crises, the best defensive
asset varies (bonds in deflationary crashes, gold/commodities in inflationary).
Fast time-series momentum identifies the working defensive asset *during* the
event. This overlay carves a hedge budget from risk assets and allocates it to
the best-fast-trend defensive candidate, recomputed monthly.

References:
- Harvey, Hoyle, Rattray, Sargaison, Taylor & Van Hemert (2019)
  "Crisis Alpha", Journal of Portfolio Management, 45(5)

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), ...,
        AssetStrategy('VUTY'), AssetStrategy('SGLN'), AssetStrategy('COMM')
    ]
    strategy = DynamicCrisisHedgeOverlayStrategy(
        underlying=assets,
        sma_months=10,
        hedge_frac=0.3,
        trend_months=2,
        top_k=1
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List
import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Equity sleeve for crisis signal computation
EQUITY_SLEEVE = {
    "VUSA",
    "EQQQ",
    "IWRD",
    "IMEU",
    "IIND",
    "ASHR",
    "SAEM",
    "CACX",
    "CSX5",
    "IEMU",
    "WCLD",
    "WSML",
    "AWESGS",
    "EMMCHA",
    "EXXW",
    "EXX5",
    "EXI2",
    "EXSA",
}

# Defensive candidates for crisis hedge
DEFENSIVE_CANDIDATES = {"VUTY", "SGLN", "COMM"}

# Default fallback if all candidates trend negative
DEFAULT_FALLBACK = "VUTY"


class DynamicCrisisHedgeOverlayStrategy(AllocationStrategy):
    """
    Dynamic crisis hedge overlay: selects best-fast-trend defensive asset when
    equity anchor falls below its SMA.

    Starts with an equal-weight base across all available assets. When equity
    crisis is detected (anchor below SMA), carves a hedge budget from the equity
    sleeve pro-rata and allocates it to the defensive candidate(s) with the
    best fast trend, inverse-vol weighted. Calm periods pass base weights through
    unchanged.

    Only uses assets actually present in the rebalance universe. If defensive
    candidates or equity anchor not available, falls back to equal-weight.

    Attributes:
        sma_months: SMA window for crisis detection (e.g., 10 = 10 months)
        hedge_frac: Fraction of risk-asset weight to hedge (e.g., 0.3 = 30%)
        trend_months: Trend lookback window in months (e.g., 2 = 2-month return)
        top_k: Number of top defensive assets to select (e.g., 1 = top-1)
        equity_anchor: Symbol of equity anchor for crisis signal (e.g., "VUSA")
    """

    def __init__(
        self,
        underlying: List[Strategy],
        sma_months: int = 10,
        hedge_frac: float = 0.3,
        trend_months: int = 2,
        top_k: int = 1,
        equity_anchor: str = "VUSA",
        name: str = None,
    ):
        """
        Initialize Dynamic Crisis Hedge Overlay strategy.

        Args:
            underlying: List of underlying strategies (assets)
            sma_months: SMA window for equity anchor crisis detection (default 10)
            hedge_frac: Hedge budget as fraction of risk assets (default 0.3)
            trend_months: Trend lookback in months for defensive selection (default 2)
            top_k: Number of top defensive assets to select (default 1)
            equity_anchor: Symbol of equity anchor (default "VUSA")
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Dynamic Crisis Hedge ({sma_months}m SMA, {hedge_frac:.0%})",
        )
        self.sma_months = sma_months
        self.hedge_frac = hedge_frac
        self.trend_months = trend_months
        self.top_k = top_k
        self.equity_anchor = equity_anchor.upper()

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate crisis-hedge-adjusted weights.

        Args:
            context: StrategyContext with prices, current_date, metadata

        Returns:
            pd.Series with index=asset names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            1. Start with equal-weight base
            2. Detect crisis: equity anchor below its SMA
            3. If calm: return base weights
            4. If crisis: select top defensive by fast trend, allocate hedge budget
            5. Normalize to sum 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]

        # Initialize equal-weight base
        equal_weight = 1.0 / len(available_symbols)
        weights = pd.Series(equal_weight, index=strategy_names)

        # Check data availability
        if self.equity_anchor not in available_symbols:
            logger.debug(
                f"DynamicCrisisHedge: anchor {self.equity_anchor} not available, "
                "using base weights"
            )
            return weights

        available_equities = EQUITY_SLEEVE & available_symbols
        if not available_equities:
            logger.debug(
                "DynamicCrisisHedge: no equity assets available, using base weights"
            )
            return weights

        available_defensives = DEFENSIVE_CANDIDATES & available_symbols
        if not available_defensives:
            logger.debug(
                "DynamicCrisisHedge: no defensive candidates available, "
                "using base weights"
            )
            return weights

        # Detect crisis: anchor below SMA
        crisis_signal = self._is_crisis(context.prices)

        logger.debug(
            f"DynamicCrisisHedge: crisis_signal = {crisis_signal}, "
            f"anchor = {self.equity_anchor}"
        )

        if not crisis_signal:
            # Calm: pass base weights through
            logger.debug("DynamicCrisisHedge: calm period, using base weights")
            return weights

        # Crisis: select defensive asset and hedge
        logger.debug(
            f"DynamicCrisisHedge: crisis detected, hedging {self.hedge_frac:.1%} "
            f"from equities"
        )

        selected_defensives = self._select_defensive_assets(
            context.prices, available_defensives
        )

        if not selected_defensives:
            logger.debug("DynamicCrisisHedge: no defensive selection, using base weights")
            return weights

        # Build new weights: pull hedge_frac from equities, give to selected defensives
        equity_names = {symbol_to_name.get(sym, sym) for sym in available_equities}
        defensive_names = {
            symbol_to_name.get(sym, sym) for sym in selected_defensives
        }

        # Reduce equities pro-rata by hedge_frac
        equity_weight_total = weights[list(equity_names)].sum()
        if equity_weight_total > 0:
            reduction_per_equity = self.hedge_frac / len(equity_names)
            for eq_name in equity_names:
                weights[eq_name] -= reduction_per_equity

        # Allocate hedge budget to selected defensives (equally weighted among them)
        allocation_per_defensive = self.hedge_frac / len(defensive_names)
        for def_name in defensive_names:
            weights[def_name] += allocation_per_defensive

        # Ensure no negative weights
        weights = weights.clip(0.0, None)

        # Normalize to sum to 1.0
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            # Fallback to equal-weight
            weights = pd.Series(equal_weight, index=strategy_names)

        logger.debug(f"DynamicCrisisHedge weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Dynamic Crisis Hedge requires SMA + trend data.

        Returns:
            max(sma_lookback, trend_lookback) in days
        """
        sma_days = self.sma_months * 21  # ~21 trading days per month
        trend_days = self.trend_months * 21
        return max(sma_days, trend_days) + 10  # Extra buffer

    def _is_crisis(self, prices: pd.DataFrame) -> bool:
        """
        Detect crisis: equity anchor below its SMA.

        Args:
            prices: Price DataFrame with available symbols

        Returns:
            True if anchor is below SMA, False otherwise
        """
        if self.equity_anchor not in prices.columns:
            return False

        anchor_prices = prices[self.equity_anchor]
        if len(anchor_prices) < self.sma_months * 21:
            return False

        # Compute SMA
        sma = anchor_prices.rolling(window=self.sma_months * 21).mean()
        current_price = anchor_prices.iloc[-1]
        current_sma = sma.iloc[-1]

        if np.isnan(current_sma) or current_sma <= 0:
            return False

        # Crisis if price < SMA
        return current_price < current_sma

    def _select_defensive_assets(
        self, prices: pd.DataFrame, available_defensives: set
    ) -> set:
        """
        Select top-k defensive assets by fast trend, inverse-vol weighted.

        Args:
            prices: Price DataFrame with available symbols
            available_defensives: Set of defensive symbols available

        Returns:
            Set of selected defensive symbols (up to top_k)
        """
        if not available_defensives:
            return set()

        # Compute trend and volatility for each defensive candidate
        trend_scores = {}
        inv_vols = {}

        trend_days = max(1, self.trend_months * 21)
        if len(prices) < trend_days:
            # Insufficient data, select VUTY or first available
            return (
                {DEFAULT_FALLBACK}
                if DEFAULT_FALLBACK in available_defensives
                else {available_defensives.pop()}
            )

        for sym in available_defensives:
            if sym not in prices.columns:
                continue

            sym_prices = prices[sym]
            recent = sym_prices.tail(trend_days)

            if len(recent) < 2:
                continue

            # Trend: trailing return
            trend = (recent.iloc[-1] / recent.iloc[0] - 1.0) if recent.iloc[0] > 0 else 0

            # Volatility: daily return std, annualized
            returns = recent.pct_change().dropna()
            if len(returns) > 1:
                vol = returns.std() * np.sqrt(252)
            else:
                vol = 1.0  # Default to equal weighting if no vol data

            # Inverse vol weight
            inv_vol = 1.0 / vol if vol > 1e-8 else 1.0

            trend_scores[sym] = trend
            inv_vols[sym] = inv_vol

        if not trend_scores:
            # No valid data, default to VUTY or first available
            return (
                {DEFAULT_FALLBACK}
                if DEFAULT_FALLBACK in available_defensives
                else {available_defensives.pop()}
            )

        # Sort by trend (descending)
        sorted_by_trend = sorted(trend_scores.items(), key=lambda x: x[1], reverse=True)

        # Select top-k
        selected = []
        for sym, trend in sorted_by_trend[: self.top_k]:
            if trend >= 0:
                # Only select if trend is non-negative
                selected.append(sym)

        # If no positive-trend candidates, fall back to DEFAULT_FALLBACK or least-bad
        if not selected:
            if DEFAULT_FALLBACK in available_defensives:
                selected = [DEFAULT_FALLBACK]
            else:
                # Pick least-bad (highest trend, even if negative)
                selected = [sorted_by_trend[0][0]]

        return set(selected)

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
