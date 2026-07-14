"""
Stock-Bond Correlation Regime Allocation (Brixton et al. 2023, AQR).

Conditional defensive-sleeve allocation based on rolling stock-bond correlation.
When correlation is low/negative, bonds hedge equity risk. When correlation turns
positive, substitute bonds with real assets (gold + commodities) to preserve
diversification in inflationary regimes.

Implementation
--------------
1. Compute rolling correlation of daily/monthly equity vs bond returns.
2. Estimate lookback window (default 504 trading days ≈ 24 months).
3. Determine regime: if correlation < threshold (default 0.05), use bonds (VUTY).
                     if correlation >= threshold, use gold + commodities (SGLN+COMM).
4. Defensive sleeve size fixed (def_frac, default 0.4).
5. Equity sleeve (1-def_frac) split equally among equity assets.
6. Optional hysteresis band (±hysteresis, default 0.05) to reduce flip turnover.

Parameters
----------
lookback_days : int
    Lookback for rolling correlation (default 504 ≈ 24 months).
def_frac : float
    Fixed defensive sleeve fraction (default 0.4).
correlation_threshold : float
    Threshold for regime switch (default 0.05).
hysteresis : float
    Hysteresis band halfwidth to reduce flip turnover (default 0.05).
equity_symbols : list of str
    Symbols for equity allocation (e.g. VUSA, IWRD).
bond_symbol : str
    Single bond symbol (e.g. VUTY).
gold_symbol : str
    Gold symbol (e.g. SGLN).
commodity_symbol : str
    Commodity symbol (e.g. COMM).
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class StockBondCorrelationRegimeStrategy(AllocationStrategy):
    """
    Stock-Bond Correlation Regime Allocation: conditionally switch defensive
    sleeve between bonds (low correlation) and real assets (high correlation).

    Preserves diversification benefits by adapting the defensive sleeve's
    composition based on whether stocks and bonds hedge each other.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 504,
        def_frac: float = 0.4,
        correlation_threshold: float = 0.05,
        hysteresis: float = 0.05,
        equity_symbols: Optional[List[str]] = None,
        bond_symbol: Optional[str] = None,
        gold_symbol: Optional[str] = None,
        commodity_symbol: Optional[str] = None,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
            lookback_days: Lookback for rolling correlation (default 504 ≈ 24m).
            def_frac: Defensive sleeve fraction (default 0.4).
            correlation_threshold: Regime switch threshold (default 0.05).
            hysteresis: Hysteresis band halfwidth (default 0.05).
            equity_symbols: Equity asset symbols (e.g. VUSA, IWRD).
            bond_symbol: Bond symbol (e.g. VUTY).
            gold_symbol: Gold symbol (e.g. SGLN).
            commodity_symbol: Commodity symbol (e.g. COMM).
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Stock-Bond Correlation Regime ({lookback_days}d)",
        )
        self.lookback_days = lookback_days
        self.def_frac = max(0.0, min(1.0, def_frac))
        self.correlation_threshold = correlation_threshold
        self.hysteresis = hysteresis
        self.equity_symbols = equity_symbols or []
        self.bond_symbol = bond_symbol
        self.gold_symbol = gold_symbol
        self.commodity_symbol = commodity_symbol
        # Track last regime to apply hysteresis
        self._last_regime = None  # 'bonds' or 'real_assets'

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        # Require sufficient history
        min_required = max(30, self.lookback_days + 5)
        if len(prices) < min_required:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < self.lookback_days:
            return self._equal_weight(prices)

        # Identify available equity and defensive assets
        available_equity = [s for s in self.equity_symbols if s in prices.columns]
        if not available_equity:
            available_equity = [s for s in prices.columns
                              if s not in [self.bond_symbol, self.gold_symbol, self.commodity_symbol]]

        if not available_equity or len(available_equity) < 1:
            return self._equal_weight(prices)

        # Extract lookback window for correlation
        lookback_prices = prices.iloc[-self.lookback_days :].copy()
        lookback_prices = lookback_prices.ffill(limit=3).dropna()

        if len(lookback_prices) < 30:
            return self._equal_weight(prices)

        # Compute correlation of equity vs bond
        correlation = self._compute_stock_bond_correlation(lookback_prices)

        logger.debug(
            f"SBCR: stock-bond correlation {correlation:.4f}, "
            f"threshold {self.correlation_threshold:.4f}, "
            f"hysteresis band [{self.correlation_threshold - self.hysteresis:.4f}, "
            f"{self.correlation_threshold + self.hysteresis:.4f}]"
        )

        # Determine regime with hysteresis
        regime = self._determine_regime(correlation)

        logger.debug(f"SBCR: regime = {regime}")

        # Build weight vector
        symbol_to_name = self._build_name_map()
        all_symbols = list(prices.columns)
        index = [symbol_to_name.get(s, s) for s in all_symbols]
        weights = pd.Series(0.0, index=index)

        # Allocate equity sleeve
        equity_frac = 1.0 - self.def_frac
        if available_equity:
            per_equity = equity_frac / len(available_equity)
            for sym in available_equity:
                name = symbol_to_name.get(sym, sym)
                weights[name] = per_equity

        # Allocate defensive sleeve based on regime
        if regime == "bonds" and self.bond_symbol:
            if self.bond_symbol in symbol_to_name:
                name = symbol_to_name[self.bond_symbol]
                weights[name] = self.def_frac
        elif regime == "real_assets":
            # Split gold + commodity 50/50 within defensive fraction
            if self.gold_symbol and self.gold_symbol in symbol_to_name:
                name = symbol_to_name[self.gold_symbol]
                weights[name] = self.def_frac * 0.5
            if self.commodity_symbol and self.commodity_symbol in symbol_to_name:
                name = symbol_to_name[self.commodity_symbol]
                weights[name] = self.def_frac * 0.5

        return weights

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    def _compute_stock_bond_correlation(self, prices: pd.DataFrame) -> float:
        """Compute correlation of equity (mean) vs bond returns."""
        # Equity = mean of equity symbols
        available_equity = [s for s in self.equity_symbols if s in prices.columns]
        if not available_equity:
            available_equity = [s for s in prices.columns
                              if s not in [self.bond_symbol, self.gold_symbol, self.commodity_symbol]]

        if not available_equity or self.bond_symbol not in prices.columns:
            return 0.0

        equity_prices = prices[[s for s in available_equity if s in prices.columns]]
        equity_price = equity_prices.mean(axis=1)
        bond_price = prices[self.bond_symbol]

        # Compute returns
        equity_ret = equity_price.pct_change().dropna()
        bond_ret = bond_price.pct_change().dropna()

        # Align and compute correlation
        common_idx = equity_ret.index.intersection(bond_ret.index)
        if len(common_idx) < 2:
            return 0.0

        equity_ret_aligned = equity_ret[common_idx]
        bond_ret_aligned = bond_ret[common_idx]

        corr = equity_ret_aligned.corr(bond_ret_aligned)
        if pd.isna(corr):
            return 0.0

        return float(corr)

    def _determine_regime(self, correlation: float) -> str:
        """Determine regime with hysteresis."""
        if self._last_regime is None:
            # First call: use simple threshold
            if correlation < self.correlation_threshold:
                self._last_regime = "bonds"
            else:
                self._last_regime = "real_assets"
        else:
            # Apply hysteresis band
            if self._last_regime == "bonds":
                if correlation > self.correlation_threshold + self.hysteresis:
                    self._last_regime = "real_assets"
            else:  # real_assets
                if correlation < self.correlation_threshold - self.hysteresis:
                    self._last_regime = "bonds"

        return self._last_regime

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
