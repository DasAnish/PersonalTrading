"""
Inflation-Regime Quadrant Allocation (price-proxied).

Based on Baltussen, Swinkels, van Vliet & van Vliet (2023), "Investing in
Deflation, Inflation, and Stagflation Regimes", Financial Analysts Journal
79(3): asset premiums differ sharply across inflation/growth regimes.
Without CPI data, trailing commodity-sleeve trend proxies inflation and
trailing equity-sleeve trend proxies growth; each of the four quadrants
maps to a sleeve allocation (inverse-vol within sleeve, long-only).
"""

import logging
from typing import Dict, List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class InflationRegimeStrategy(AllocationStrategy):
    """
    Quadrant allocation from price-proxied growth x inflation signals.

    Quadrants (sleeve weights):
    - goldilocks (growth+, inflation-): equities 1.0
    - inflationary expansion (growth+, inflation+): equities 0.5,
      commodities+gold 0.5
    - stagflation (growth-, inflation+): commodities+gold 0.6, bonds 0.4
    - deflation (growth-, inflation-): bonds 0.7, gold 0.3
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        vol_window_days: int = 63,
        equity_symbols: List[str] = None,
        commodity_symbols: List[str] = None,
        bond_symbols: List[str] = None,
        gold_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Inflation Regime Quadrants")
        self.lookback_days = lookback_days
        self.vol_window_days = vol_window_days
        self.equity_symbols = equity_symbols or ["VUSA", "IWRD", "EQQQ", "IMEU"]
        self.commodity_symbols = commodity_symbols or ["COMM", "BRNT", "CRUD", "WCOA"]
        self.bond_symbols = bond_symbols or ["VUTY", "AGGU", "SEGA"]
        self.gold_symbols = gold_symbols or ["SGLN"]

    def _sleeves(self, columns) -> Dict[str, List[str]]:
        return {
            "equity": [s for s in self.equity_symbols if s in columns],
            "commodity": [s for s in self.commodity_symbols if s in columns],
            "bond": [s for s in self.bond_symbols if s in columns],
            "gold": [s for s in self.gold_symbols if s in columns],
        }

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 3:
            raise ValueError("Inflation Regime requires at least 3 assets.")

        min_required = max(self.lookback_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for inflation regime: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()
        sleeves = self._sleeves(prices.columns)

        window = prices.iloc[-self.lookback_days :]
        trailing = window.iloc[-1] / window.iloc[0] - 1

        infl_pool = sleeves["commodity"] + sleeves["gold"]
        growth = (
            trailing[sleeves["equity"]].mean() > 0 if sleeves["equity"] else True
        )
        inflation = trailing[infl_pool].mean() > 0 if infl_pool else False

        if growth and not inflation:
            sleeve_weights = {"equity": 1.0}
        elif growth and inflation:
            sleeve_weights = {"equity": 0.5, "commodity": 0.25, "gold": 0.25}
        elif not growth and inflation:
            sleeve_weights = {"commodity": 0.3, "gold": 0.3, "bond": 0.4}
        else:
            sleeve_weights = {"bond": 0.7, "gold": 0.3}

        vol_returns = prices.iloc[-self.vol_window_days :].pct_change().dropna()
        vols = vol_returns.std()
        vols[vols == 0] = 1e-10

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        weights = pd.Series(0.0, index=index)

        unassigned = 0.0
        for sleeve, share in sleeve_weights.items():
            members = sleeves.get(sleeve, [])
            if not members:
                unassigned += share
                continue
            inv_vol = 1.0 / vols[members]
            alloc = inv_vol / inv_vol.sum() * share
            for symbol, w in alloc.items():
                weights[symbol_to_name.get(symbol, symbol)] += w

        if unassigned > 0:
            fallback = sleeves["bond"] or list(prices.columns)
            for symbol in fallback:
                weights[symbol_to_name.get(symbol, symbol)] += unassigned / len(
                    fallback
                )

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
        return max(self.lookback_days, self.vol_window_days) + 10
